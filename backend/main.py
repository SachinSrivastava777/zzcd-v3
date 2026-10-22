"""Zero-Click Deploy Doctor API, with SSE progress and bounded concurrent jobs."""
import os, shutil, uuid, time, json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
import docker, git

from detectors.stack_detector import detect_stack
from dockerfile_builder import build_dockerfile, STACK_TO_TEMPLATE
from env_detector import extract_required_env_vars
from patcher import patch_dockerfile
from source_patcher import patch_source_host_binding
from security import scan_secrets
from sandbox.docker_runner import build_image, run_and_health_check, cleanup_container, cleanup_image
from deploy_render import deploy_to_render
from job_manager import create_job, emit, get_job, submit, wait_events

WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
MAX_RETRIES = max(1, min(int(os.getenv("MAX_DEPLOY_ATTEMPTS", "6")), 10))
app = FastAPI(title="Zero-Click Deploy Doctor", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class DeployRequest(BaseModel):
    repo_url: str
    env_vars: Optional[dict] = None

class DeployResponse(BaseModel):
    status: str
    live_url: Optional[str] = None
    required_env_vars: Optional[list] = None
    stack_detected: Optional[str] = None
    attempts: Optional[int] = None
    report: Optional[str] = None
    build_logs_tail: Optional[str] = None

def _progress(job_id, stage, message, **data):
    if job_id: emit(job_id, stage, message, **data)

def _clone_repo(repo_url: str) -> str:
    # Restrict URL schemes to avoid local-file or arbitrary protocol clones.
    from urllib.parse import urlparse
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Enter a valid public Git repository URL (https:// recommended).")
    job_id = uuid.uuid4().hex[:10]
    dest = os.path.join(WORKSPACE_ROOT, job_id)
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    try:
        git.Repo.clone_from(repo_url, dest, depth=1, multi_options=["--filter=blob:none"])
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to clone repository: {exc}")
    return dest

def _write_dockerfile(repo_path, content):
    with open(os.path.join(repo_path, "Dockerfile"), "w", encoding="utf-8") as f: f.write(content)

def _run_pipeline(req: DeployRequest, job_id: Optional[str] = None) -> dict:
    repo_path = None
    client = None
    image_tag = None
    last_logs = ""
    attempts = 0
    try:
        _progress(job_id, "clone", "Cloning repository…")
        repo_path = _clone_repo(req.repo_url)
        _progress(job_id, "detect", "Detecting framework, entry point, and port…")
        stack_info = detect_stack(repo_path)
        _progress(job_id, "detect", f"Detected {stack_info.stack} on port {stack_info.port}.", stack=stack_info.stack, port=stack_info.port)
        if stack_info.stack not in STACK_TO_TEMPLATE:
            return {"status":"failed","stack_detected":stack_info.stack,
                    "report":f"Stack '{stack_info.stack}' has no supported template. Notes: {'; '.join(stack_info.notes)}"}
        provided = req.env_vars or {}
        required = extract_required_env_vars(stack_info.env_example_path) if stack_info.env_example_path else []
        missing = [name for name in required if name not in provided or provided[name] in (None, "")]
        if missing:
            _progress(job_id, "env", "Waiting for required environment variables.", required_env_vars=missing)
            return {"status":"needs_env_vars","stack_detected":stack_info.stack,"required_env_vars":missing,
                    "report":f"This app needs {len(missing)} environment variable(s)."}
        _progress(job_id, "patch", "Applying safe source-level host-binding checks…")
        source_patch = patch_source_host_binding(repo_path, stack_info.stack, stack_info.port)
        if source_patch.changed:
            _progress(job_id, "patch", "Patched source host binding.", files=source_patch.files)
        dockerfile_content = build_dockerfile(stack_info)
        _write_dockerfile(repo_path, dockerfile_content)
        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:
            return {"status":"failed","stack_detected":stack_info.stack,
                    "report":f"Docker is not reachable. Start Docker Desktop/Engine and retry. Details: {exc}"}
        last_logs = ""
        for attempt in range(1, MAX_RETRIES + 1):
            attempts = attempt
            _progress(job_id, "build", f"Building Docker image (attempt {attempt}/{MAX_RETRIES})…", attempt=attempt, max_attempts=MAX_RETRIES)
            build_result = build_image(client, repo_path)
            last_logs = build_result.logs or build_result.error or ""
            if not build_result.success:
                _progress(job_id, "logs", "Docker build failed; examining logs for a targeted fix.", logs=last_logs[-5000:])
                patch = patch_dockerfile(dockerfile_content, last_logs, stack_info.stack)
                if patch:
                    dockerfile_content = patch.patched_dockerfile
                    _write_dockerfile(repo_path, dockerfile_content)
                    _progress(job_id, "patch", patch.explanation, used_llm=patch.used_llm)
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                break
            image_tag = build_result.image_tag
            _progress(job_id, "health", "Image built. Starting sandbox and checking HTTP health…")
            run_result = run_and_health_check(client, image_tag, stack_info.port, env_vars=provided)
            last_logs = run_result.logs or run_result.error or ""
            if run_result.success and run_result.health_check_passed:
                cleanup_container(client, run_result.container_id)
                cleanup_image(client, image_tag)
                image_tag = None
                _progress(job_id, "security", "Scanning source before publishing deployment artifact…")
                findings = scan_secrets(repo_path)
                if findings and os.getenv("ALLOW_PUBLIC_DEPLOY_WITH_FINDINGS", "false").lower() != "true":
                    return {"status":"failed","stack_detected":stack_info.stack,"attempts":attempts,
                            "report":"Local build and health check passed, but public deployment was blocked because potential secrets/sensitive files were found. Review: " + "; ".join(findings[:12]) +
                                     ". Remove secrets from source; use environment variables. Override only after review with ALLOW_PUBLIC_DEPLOY_WITH_FINDINGS=true."}
                repo_name = os.path.basename(req.repo_url.rstrip("/"))
                if repo_name.lower().endswith(".git"): repo_name = repo_name[:-4]
                _progress(job_id, "deploy", "Health check passed. Requesting Render deployment…")
                deploy_result = deploy_to_render(repo_path, repo_name, env_vars=provided, port=stack_info.port)
                if deploy_result.success:
                    return {"status":"success","live_url":deploy_result.url,"stack_detected":stack_info.stack,
                            "attempts":attempts,"report":"Local build and HTTP health check passed; Render deployment was requested.",
                            "temporary_repo_url":deploy_result.repo_url}
                return {"status":"failed","stack_detected":stack_info.stack,"attempts":attempts,
                        "report":f"Build and health check passed, but Render deployment failed: {deploy_result.error}",
                        "build_logs_tail":last_logs[-5000:]}
            if run_result.container_id: cleanup_container(client, run_result.container_id)
            _progress(job_id, "logs", "Health check failed; inspecting container logs.", logs=last_logs[-5000:])
            patch = patch_dockerfile(dockerfile_content, last_logs, stack_info.stack)
            cleanup_image(client, image_tag)
            image_tag = None
            if patch:
                dockerfile_content = patch.patched_dockerfile
                _write_dockerfile(repo_path, dockerfile_content)
                _progress(job_id, "patch", patch.explanation, used_llm=patch.used_llm)
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            break
        return {"status":"failed","stack_detected":stack_info.stack,"attempts":attempts,
                "report":f"Could not get a healthy app after {attempts} attempt(s). Last error/logs:\n{last_logs[-2500:]}\nCheck the detected entry point ({stack_info.entry_point}) and port ({stack_info.port}), then try building locally.",
                "build_logs_tail":last_logs[-5000:]}
    except HTTPException as exc:
        return {"status":"failed","report":exc.detail}
    except Exception as exc:
        return {"status":"failed","report":f"Unexpected deployment error: {type(exc).__name__}: {exc}","build_logs_tail":last_logs[-5000:]}
    finally:
        if client and image_tag:
            cleanup_image(client, image_tag)
        if repo_path:
            shutil.rmtree(repo_path, ignore_errors=True)

@app.get("/health")
def health():
    return {"ok": True, "service":"zero-click-deploy-doctor"}

@app.post("/deploy", response_model=DeployResponse)
def deploy(req: DeployRequest):
    return _run_pipeline(req)

@app.post("/jobs")
def create_deploy_job(req: DeployRequest):
    try:
        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        job_id = create_job(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    submit(job_id, _run_pipeline, req, job_id)
    return {"job_id":job_id,"status":"queued","events_url":f"/jobs/{job_id}/events","status_url":f"/jobs/{job_id}"}

@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Unknown job id")
    return job

@app.get("/jobs/{job_id}/events")
def job_events(job_id: str, after: int = 0):
    if not get_job(job_id): raise HTTPException(status_code=404, detail="Unknown job id")
    def stream():
        last = after
        while True:
            status, events = wait_events(job_id, last, timeout=12)
            if status is None: break
            if not events:
                yield ": keep-alive\n\n"
            for event in events:
                last = event["id"]
                yield f"id: {last}\nevent: progress\ndata: {json.dumps(event)}\n\n"
                if event["stage"] in {"complete","failed"}:
                    return
    return StreamingResponse(stream(), media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
