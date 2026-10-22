# Integration / demo checklist

1. Start Docker Desktop / Docker Engine.
2. Start the API from `backend` using `uvicorn main:app --reload --host 127.0.0.1 --port 8000`.
3. Serve `frontend` over HTTP (`python -m http.server 5500`) if opening the HTML file directly blocks API requests.
4. Open `http://127.0.0.1:5500`, paste a public repository URL, and watch real SSE events.
5. For cloud deployment, set `RENDER_API_KEY`, `RENDER_OWNER_ID`, and `GITHUB_TOKEN` in the backend terminal before launching uvicorn.
6. Check `/health` for backend liveness. `/jobs` creates async jobs, `/jobs/{id}` returns the state, and `/jobs/{id}/events` streams progress.
7. Run tests from `backend`: `python -m unittest discover -s tests -v`.

## Important constraints
- The local Docker daemon and outbound internet access are needed to clone/build.
- Cloud API integration has not been verified against live credentials in this environment.
- The secret scanner can produce false positives. Review findings; never publish secrets to a public repo.
- The in-memory queue is suitable for a demo only and resets on restart.
- Java template assumes a runnable Spring Boot/Java web JAR. CMake template assumes an HTTP-serving executable named `app`; adjust the template if your target differs.
