"""
Hugging Face Spaces Deploy
--------------------------
On a passing health check, push the repo (with our generated/patched
Dockerfile) to a new HF Space using the Docker SDK, and return the live
Space URL.

Requires HF_TOKEN env var. We create the Space, then push files via the
huggingface_hub API (upload_folder), which also creates the repo if it
doesn't exist.
"""

import os
import re
import time
from dataclasses import dataclass
from typing import Optional

try:
    from huggingface_hub import HfApi, create_repo
except ImportError:
    HfApi = None
    create_repo = None


@dataclass
class DeployResult:
    success: bool
    url: Optional[str] = None
    error: Optional[str] = None


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-]", "-", name).strip("-").lower()
    return slug[:40] or "zcdd-app"


def deploy_to_hf_spaces(local_repo_path: str, repo_name: str, hf_username: Optional[str] = None) -> DeployResult:
    token = os.environ.get("HF_TOKEN")
    if not token:
        return DeployResult(success=False, error="HF_TOKEN not set in environment — cannot deploy to HF Spaces.")
    if HfApi is None:
        return DeployResult(success=False, error="huggingface_hub not installed — run `pip install huggingface_hub`.")

    api = HfApi(token=token)
    try:
        whoami = api.whoami()
        username = hf_username or whoami.get("name")
    except Exception as e:
        return DeployResult(success=False, error=f"HF auth failed — check HF_TOKEN. ({e})")

    space_id = f"{username}/{_slugify(repo_name)}-{int(time.time())}"

    try:
        create_repo(
            repo_id=space_id,
            repo_type="space",
            space_sdk="docker",
            token=token,
            private=False,
            exist_ok=True,
        )
        api.upload_folder(
            folder_path=local_repo_path,
            repo_id=space_id,
            repo_type="space",
            token=token,
            ignore_patterns=[".git", ".git/*", "__pycache__", "*.pyc"],
        )
        url = f"https://huggingface.co/spaces/{space_id}"
        return DeployResult(success=True, url=url)
    except Exception as e:
        return DeployResult(success=False, error=f"HF Spaces deploy failed: {e}")
