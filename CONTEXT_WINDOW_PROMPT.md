# Context-window prompt: Zero-Click Deploy Doctor

You are helping me maintain and debug **Zero-Click Deploy Doctor**, a local-first hackathon project that accepts a public Git repository URL, detects its application stack, generates a Dockerfile, builds/runs it in Docker, performs an HTTP health check, captures logs, applies conservative fixes, and can optionally request a Render deployment.

## Current project layout
- `frontend/index.html`: responsive single-page GUI; backend URL defaults to `http://127.0.0.1:8000`; submits `POST /jobs`, consumes SSE from `GET /jobs/{id}/events`, and reads `GET /jobs/{id}`.
- `backend/main.py`: FastAPI API and deployment pipeline.
- Root `main.py`: compatibility ASGI entry point so `python -m uvicorn main:app ...` can run from the project root.
- `backend/job_manager.py`: in-memory queue and SSE event history.
- `backend/detectors/stack_detector.py`, `backend/dockerfile_builder.py`, `backend/templates/`: stack detection and Dockerfile generation.
- `backend/sandbox/docker_runner.py`: Docker image build, container run, health check, and cleanup.
- `start_backend.bat`, `start_frontend.bat`: Windows launch helpers.

## Known issue and fixes already applied in this repaired bundle
- Previously, running `uvicorn main:app` from the project root failed because the actual FastAPI app was in `backend/main.py`. Root `main.py` now adds the backend directory to `sys.path` and imports `backend.main:app`.
- The frontend/backend default API port is aligned to **8000**.
- Pydantic v1/v2 request serialization is handled with `model_dump()` when available and `.dict()` otherwise.
- Python 3.8 compatibility fixes replace `str.removesuffix()` and defer modern type annotations in affected modules. Python 3.11 is still recommended.
- The existing backend uses `POST /jobs`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/events`, and `GET /health`. The SSE event name is `progress`.

## How to run on Windows
1. Start Docker Desktop and wait until its engine is ready.
2. Run `start_backend.bat` from the project root, or use:
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r backend\requirements.txt
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
3. Confirm `http://127.0.0.1:8000/health` returns a JSON response with `ok: true`.
4. Run `start_frontend.bat`, then open `http://127.0.0.1:5500`.
5. The app needs a working Docker daemon to build/health-check a project. A real cloud deployment also needs the appropriate Render/GitHub environment variables.

## Debugging requirements
- Do not guess the root cause. Ask for or inspect the actual traceback, `/health` response, job JSON, SSE events, Docker build output, and `docker info` as needed.
- Separate API connectivity from job state and from Docker/cloud deployment success. HTTP `200 OK` only means the request succeeded, not that the deployment succeeded.
- When fixing code, preserve the generic multi-stack design; do not hardcode behavior for only one repository.
- Make the smallest reliable change, include a regression test where practical, run `python -m compileall -q .` and `python -m unittest discover -s tests -v` from the `backend` directory, and report exactly what was and was not verified.
- Never claim a real Docker build or cloud deployment passed unless it was actually executed against a running Docker daemon / configured provider.
- Never commit or print real API tokens.

## Current debugging trail
A job successfully cloned a repository, detected `python-generic` on port 8000, then reached `Building Docker image (attempt 1/6)`. The user interrupted Uvicorn and saw `KeyboardInterrupt` / `CancelledError`, which are consistent with shutdown of the server/SSE request and do not alone prove the original Docker build failure. Need inspect actual Docker build logs to diagnose that separate issue.
