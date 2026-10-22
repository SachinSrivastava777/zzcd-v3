"""Compatibility ASGI entry point for running from the project root.

Run: python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
"""
import os
import sys

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from backend.main import app  # noqa: E402,F401
