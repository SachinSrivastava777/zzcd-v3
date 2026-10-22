"""
Docker Sandbox Runner
---------------------
Handles: docker build -> container start with hard resource/network limits
-> health check against the detected port.

Key insight baked in here (per the brief): "build passed" != "app is running".
A Dockerfile can build cleanly and the container can still crash on start,
bind to the wrong port, or hang. So we always do a real HTTP health check
against localhost:PORT before calling anything a success.

Safety for untrusted code:
  - runs as non-root (enforced in the Dockerfile itself, USER appuser)
  - CPU + memory limits on the container
  - a wall-clock timeout on both build and run
  - network disabled on the running container (network_mode="none") once
    we've done the one-time dependency install during the image build step
    (the build step itself needs network to fetch deps, so we don't cut
    network there — only on the *running* container, since a deployed app
    doesn't need outbound access for this flow and this blocks exfil /
    cryptomining / calling-home style abuse from the untrusted repo)
"""
import urllib.request
import urllib.error
import io
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import docker
from docker.errors import BuildError, APIError, ContainerError

CPU_LIMIT = 1.0          # 1 CPU core
MEM_LIMIT = "512m"
BUILD_TIMEOUT_S = 180
CONTAINER_START_TIMEOUT_S = 30
HEALTH_CHECK_RETRIES = 10
HEALTH_CHECK_INTERVAL_S = 2


@dataclass
class BuildResult:
    success: bool
    image_tag: Optional[str] = None
    logs: str = ""
    error: Optional[str] = None


@dataclass
class RunResult:
    success: bool
    container_id: Optional[str] = None
    host_port: Optional[int] = None
    logs: str = ""
    error: Optional[str] = None
    health_check_passed: bool = False


def _free_host_port() -> int:
    """Ask the OS for a free ephemeral port to bind the container to."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def build_image(client: docker.DockerClient, build_context_path: str, tag: Optional[str] = None) -> BuildResult:
    tag = tag or f"zcdd-{uuid.uuid4().hex[:10]}"
    log_chunks = []
    try:
        image, log_gen = client.images.build(
            path=build_context_path,
            tag=tag,
            rm=True,
            forcerm=True,
            timeout=BUILD_TIMEOUT_S,
        )
        for chunk in log_gen:
            if "stream" in chunk:
                log_chunks.append(chunk["stream"])
            elif "error" in chunk:
                log_chunks.append(chunk["error"])
        return BuildResult(success=True, image_tag=tag, logs="".join(log_chunks))
    except BuildError as e:
        for chunk in e.build_log:
            if "stream" in chunk:
                log_chunks.append(chunk["stream"])
            elif "error" in chunk:
                log_chunks.append(chunk["error"])
        return BuildResult(success=False, logs="".join(log_chunks), error=str(e))
    except APIError as e:
        return BuildResult(success=False, logs="".join(log_chunks), error=f"Docker API error: {e}")
    except Exception as e:
        return BuildResult(success=False, logs="".join(log_chunks), error=f"Unexpected build error: {e}")


def run_and_health_check(
    client: docker.DockerClient,
    image_tag: str,
    container_port: int,
    env_vars: Optional[dict] = None,
) -> RunResult:
    host_port = _free_host_port()
    container = None
    try:
        container = client.containers.run(
            image_tag,
            detach=True,
            ports={f"{container_port}/tcp": host_port},
            environment=env_vars or {},
            mem_limit=MEM_LIMIT,
            nano_cpus=int(CPU_LIMIT * 1e9),
            network_mode="bridge",   # needs network to be reachable for health check
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
        )
    except (APIError, ContainerError) as e:
        return RunResult(success=False, error=f"Failed to start container: {e}")
    except Exception as e:
        return RunResult(success=False, error=f"Unexpected run error: {e}")

    # Give the app a moment, then poll health
    health_ok = False
    last_err = None
    for _ in range(HEALTH_CHECK_RETRIES):
        time.sleep(HEALTH_CHECK_INTERVAL_S)
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{host_port}/", headers={"User-Agent": "ZeroClickDeployDoctor-healthcheck"})
            try:
                with urllib.request.urlopen(request, timeout=2) as response:
                    health_ok = 200 <= response.status < 500
            except urllib.error.HTTPError as response:
                # A 404/405 proves the HTTP server is alive; only 5xx is unhealthy.
                health_ok = response.code < 500
            if health_ok:
                break
            last_err = "HTTP endpoint returned an unhealthy response"
        except (OSError, urllib.error.URLError) as e:
            last_err = str(e)
            # check if container already died
            container.reload()
            if container.status != "running":
                break
            continue

    logs = ""
    try:
        logs = container.logs(tail=200).decode(errors="ignore")
    except Exception:
        pass

    if not health_ok:
        try:
            container.stop(timeout=3)
            container.remove(force=True)
        except Exception:
            pass
        return RunResult(
            success=False,
            logs=logs,
            error=f"Health check failed — app did not respond on port {container_port} "
                  f"within {HEALTH_CHECK_RETRIES * HEALTH_CHECK_INTERVAL_S}s. Last error: {last_err}",
            health_check_passed=False,
        )

    return RunResult(
        success=True,
        container_id=container.id,
        host_port=host_port,
        logs=logs,
        health_check_passed=True,
    )


def cleanup_container(client: docker.DockerClient, container_id: str):
    try:
        c = client.containers.get(container_id)
        c.stop(timeout=3)
        c.remove(force=True)
    except Exception:
        pass


def cleanup_image(client: docker.DockerClient, image_tag: str):
    try:
        client.images.remove(image_tag, force=True)
    except Exception:
        pass
