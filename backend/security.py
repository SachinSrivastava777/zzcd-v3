"""Defensive checks before publishing cloned source to a public deployment repo."""
from __future__ import annotations

import os, re
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*["\'][^"\']{8,}["\']'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?i)gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'(?i)sk-[A-Za-z0-9_-]{20,}'),
]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", "workspace"}
SKIP_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json"}

def scan_secrets(root: str, max_files: int = 5000, max_bytes: int = 1_000_000) -> list[str]:
    findings = []
    root_path = Path(root)
    seen = 0
    for path in root_path.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root_path).parts):
            continue
        if path.name in SKIP_NAMES or path.name.endswith((".pem", ".key")):
            findings.append(f"{path.relative_to(root_path).as_posix()}: sensitive filename")
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            findings.append(f"{path.relative_to(root_path).as_posix()}: environment file")
            continue
        seen += 1
        if seen > max_files:
            findings.append("Scan stopped at file limit; review repository manually.")
            break
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{path.relative_to(root_path).as_posix()}: possible secret")
                break
    return findings
