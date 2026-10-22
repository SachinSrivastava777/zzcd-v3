"""Render deployment integration for Zero-Click Deploy Doctor.

Required environment variables:
  RENDER_API_KEY, RENDER_OWNER_ID, GITHUB_TOKEN

Creates a temporary public GitHub repository containing the generated Dockerfile
and application source, then asks Render to build/deploy it. The user's original
repository is never modified. Temporary repos are intentionally not auto-deleted
because deleting them before Render finishes building can break deployments.
"""
from __future__ import annotations
import base64
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

GITHUB_API = "https://api.github.com"
RENDER_API = "https://api.render.com/v1"

@dataclass
class DeployResult:
    success: bool
    url: Optional[str] = None
    error: Optional[str] = None
    service_id: Optional[str] = None
    repo_url: Optional[str] = None


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9-]+", "-", value).strip("-").lower()
    return (value[:35].strip("-") or "zcdd-app")


def _gh_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _create_github_repo(token: str, name: str) -> dict:
    response = requests.post(f"{GITHUB_API}/user/repos", headers=_gh_headers(token),
        json={"name": name, "description": "Temporary deployment artifact created by Zero-Click Deploy Doctor",
              "private": False, "auto_init": True}, timeout=30)
    if response.status_code == 422:
        # Avoid overwriting a pre-existing repository; choose a unique name instead.
        name = f"{name}-{int(time.time()) % 100000}"
        response = requests.post(f"{GITHUB_API}/user/repos", headers=_gh_headers(token),
            json={"name": name, "description": "Temporary deployment artifact created by Zero-Click Deploy Doctor",
                  "private": False, "auto_init": True}, timeout=30)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"GitHub repository creation failed ({response.status_code}): {response.text[:700]}. "
                           "Token needs permission to create repositories.")
    return response.json()


def _upload_tree(token: str, repo: dict, source_dir: str) -> None:
    owner, name = repo["owner"]["login"], repo["name"]
    headers = _gh_headers(token)
    base = requests.get(f"{GITHUB_API}/repos/{owner}/{name}/git/ref/heads/{repo.get('default_branch', 'main')}",
                        headers=headers, timeout=30)
    if base.status_code != 200:
        # GitHub commonly initializes the default branch as main, but respect metadata when available.
        branch = repo.get("default_branch") or "main"
        base = requests.get(f"{GITHUB_API}/repos/{owner}/{name}/git/ref/heads/{branch}", headers=headers, timeout=30)
    if base.status_code != 200:
        raise RuntimeError(f"Could not read temporary repository branch: {base.status_code} {base.text[:400]}")
    ref = base.json()["object"]["sha"]
    commit_resp = requests.get(f"{GITHUB_API}/repos/{owner}/{name}/git/commits/{ref}", headers=headers, timeout=30)
    if commit_resp.status_code != 200:
        raise RuntimeError(f"Could not read initial commit: {commit_resp.status_code} {commit_resp.text[:400]}")
    base_tree = commit_resp.json()["tree"]["sha"]

    excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
    excluded_names = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
    tree = []
    root = Path(source_dir).resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excluded_dirs for part in rel.parts):
            continue
        if path.name in excluded_names or path.name.endswith((".pem", ".key")):
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            continue
        if rel.parts and rel.parts[0] in {"workspace", "dist", "build"}:
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            continue  # GitHub's blob API has limits; omit oversized assets.
        content = path.read_bytes()
        blob = requests.post(f"{GITHUB_API}/repos/{owner}/{name}/git/blobs", headers=headers,
            json={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"}, timeout=30)
        if blob.status_code not in (200, 201):
            raise RuntimeError(f"GitHub upload failed for {rel.as_posix()}: {blob.status_code} {blob.text[:300]}")
        tree.append({"path": rel.as_posix(), "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})

    tree_resp = requests.post(f"{GITHUB_API}/repos/{owner}/{name}/git/trees", headers=headers,
        json={"base_tree": base_tree, "tree": tree}, timeout=60)
    if tree_resp.status_code not in (200, 201):
        raise RuntimeError(f"GitHub tree creation failed: {tree_resp.status_code} {tree_resp.text[:500]}")
    new_commit = requests.post(f"{GITHUB_API}/repos/{owner}/{name}/git/commits", headers=headers,
        json={"message": "Add generated Dockerfile and deployment source", "tree": tree_resp.json()["sha"], "parents": [ref]}, timeout=30)
    if new_commit.status_code not in (200, 201):
        raise RuntimeError(f"GitHub commit failed: {new_commit.status_code} {new_commit.text[:500]}")
    branch = repo.get("default_branch") or "main"
    update = requests.patch(f"{GITHUB_API}/repos/{owner}/{name}/git/refs/heads/{branch}", headers=headers,
        json={"sha": new_commit.json()["sha"], "force": True}, timeout=30)
    if update.status_code not in (200, 201):
        raise RuntimeError(f"GitHub branch update failed: {update.status_code} {update.text[:500]}")


def deploy_to_render(local_repo_path: str, repo_name: str, env_vars: Optional[dict] = None,
                     port: Optional[int] = None) -> DeployResult:
    render_key = os.getenv("RENDER_API_KEY")
    owner_id = os.getenv("RENDER_OWNER_ID")
    github_token = os.getenv("GITHUB_TOKEN")
    if not render_key or not owner_id or not github_token:
        missing = [name for name, val in [("RENDER_API_KEY", render_key), ("RENDER_OWNER_ID", owner_id), ("GITHUB_TOKEN", github_token)] if not val]
        return DeployResult(False, error="Missing environment variable(s): " + ", ".join(missing))
    render_headers = {"Authorization": f"Bearer {render_key}", "Accept": "application/json", "Content-Type": "application/json"}
    try:
        repo_slug = _slug(repo_name)
        gh_repo = _create_github_repo(github_token, f"zcdd-{repo_slug}-{int(time.time()) % 100000}")
        _upload_tree(github_token, gh_repo, local_repo_path)
        repo_url = gh_repo["html_url"]
        payload = {
            "type": "web_service",
            "name": _slug(f"zcdd-{repo_slug}-{int(time.time()) % 10000}"),
            "ownerId": owner_id,
            "repo": repo_url,
            "branch": gh_repo.get("default_branch") or "main",
            "autoDeployTrigger": "off",
            "serviceDetails": {
                "runtime": "docker",
                "plan": "free",
                "region": "singapore",
                "dockerfilePath": "./Dockerfile",
            },
        }
        # Forward only user-provided values; never infer secrets.
        if env_vars:
            payload["envVars"] = [{"key": str(k), "value": str(v)} for k, v in env_vars.items()]
        response = requests.post(f"{RENDER_API}/services", headers=render_headers, json=payload, timeout=45)
        if response.status_code not in (200, 201):
            return DeployResult(False, error=f"Render service creation failed ({response.status_code}): {response.text[:1200]}", repo_url=repo_url)
        body = response.json()
        service = body.get("service", body)
        service_id = service.get("id")
        url = (service.get("serviceDetails") or {}).get("url") or service.get("url")
        if not service_id:
            return DeployResult(False, error=f"Render accepted request but returned no service ID: {response.text[:700]}", repo_url=repo_url)
        # The create response may not contain the URL immediately; query service details.
        if not url:
            try:
                details = requests.get(f"{RENDER_API}/services/{service_id}", headers=render_headers, timeout=30)
                if details.ok:
                    obj = details.json().get("service", details.json())
                    url = (obj.get("serviceDetails") or {}).get("url") or obj.get("url")
            except requests.RequestException:
                pass
        if not url:
            url = f"https://{service.get('slug', payload['name'])}.onrender.com"
        return DeployResult(True, url=url, service_id=service_id, repo_url=repo_url)
    except (requests.RequestException, ValueError, OSError, RuntimeError, KeyError) as exc:
        return DeployResult(False, error=str(exc))
