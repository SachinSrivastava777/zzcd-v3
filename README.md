# Zero-Click Deploy Doctor

**Automated Repository Analysis, Docker Build, Health Checks, and Cloud Deployment**

Zero-Click Deploy Doctor is a full-stack deployment automation tool that simplifies the process of deploying applications from Git repositories.

Users provide a public Git repository URL, and the system automatically detects the technology stack, generates a suitable Dockerfile, builds a Docker image, runs the application in a resource-limited container, performs an HTTP health check, analyzes errors, and attempts supported fixes. Once local validation succeeds, the application can optionally publish the source to GitHub and request a deployment through Render.

The project combines repository analysis, containerization, automated diagnostics, and cloud deployment into a single workflow.

---

## Problem Statement

Deploying an application often requires developers to perform several repetitive tasks manually:

* Identify the framework and application entry point.
* Configure dependencies and runtime versions.
* Write and debug Dockerfiles.
* Resolve build and startup errors.
* Configure host binding and application ports.
* Verify that the application responds to HTTP requests.
* Inspect logs and troubleshoot failures.
* Configure cloud deployment.

These tasks can be time-consuming, especially when working with unfamiliar repositories.

Zero-Click Deploy Doctor aims to automate common deployment tasks, reduce manual configuration, and provide actionable diagnostic information when deployment problems occur.

---

## Solution

The application implements an automated pipeline that takes a public Git repository and attempts to prepare it for deployment.

The workflow includes:

1. Clone the repository into a temporary workspace.
2. Detect the framework, entry point, and application port.
3. Identify required environment variables from supported configuration files.
4. Apply supported source-level host-binding patches.
5. Generate a stack-specific Dockerfile.
6. Build the Docker image.
7. Run the application inside a resource-limited Docker container.
8. Perform an HTTP health check and collect logs.
9. Attempt supported corrections when a build or health check fails.
10. Scan the source for potential secrets before public publishing.
11. Optionally publish a copy of the source to GitHub and request a Render deployment.

The pipeline reports its progress and returns the final result through the backend API.

---

## Key Features

### Automated Stack Detection

Analyzes repository files to identify supported frameworks and relevant application configuration.

### Dockerfile Generation

Generates Dockerfiles using templates designed for the detected application stack.

### Docker Build and Execution

Builds a real Docker image and starts the application in a container instead of relying only on static configuration checks.

### HTTP Health Checks

Checks whether the containerized application responds to HTTP requests after startup.

### Automated Diagnostics

Captures Docker build output and runtime logs to help identify deployment failures.

### Conservative Automatic Fixes

Applies supported Dockerfile corrections and selected source-level host-binding patches. Optional LLM-assisted patching can be enabled using an Anthropic API key.

### Real-Time Progress

Uses Server-Sent Events (SSE) and job-status polling to display deployment progress in the frontend.

### Background Job Processing

Runs deployments through a job manager with bounded concurrency and a limited pending queue.

### Secret Scanning

Scans source files for potential secrets and sensitive files before publishing a public repository.

### Optional Cloud Deployment

Integrates GitHub and Render to publish the prepared source and request a cloud deployment.

### Responsive Web Interface

Provides a browser-based interface for submitting repository URLs, monitoring progress, and viewing deployment results.

---

## System Architecture

```text
                User
                 |
                 v
        +-------------------+
        |   Web Frontend    |
        | HTML, CSS, JS     |
        +---------+---------+
                  |
             HTTP / SSE
                  |
                  v
        +-------------------+
        |   FastAPI Backend |
        |   Job Manager     |
        +---------+---------+
                  |
                  v
        +-------------------+
        | Repository Clone  |
        | Stack Detection   |
        +---------+---------+
                  |
                  v
        +-------------------+
        | Dockerfile Builder|
        | Source Patching   |
        +---------+---------+
                  |
                  v
        +-------------------+
        |   Docker Engine   |
        | Image Build       |
        | Container Run     |
        +---------+---------+
                  |
                  v
        +-------------------+
        | HTTP Health Check |
        | Logs and Recovery |
        +---------+---------+
                  |
                  v
        +-------------------+
        | Security Scanning |
        +---------+---------+
                  |
                  v
        +-------------------+
        | GitHub + Render   |
        | Optional Deploy   |
        +-------------------+
```

### Frontend

The frontend is built using HTML, CSS, and JavaScript. It accepts deployment requests, communicates with the backend, displays progress, and presents the final result.

### Backend

The FastAPI backend coordinates repository cloning, framework detection, Dockerfile generation, image building, health checks, diagnostics, security scanning, and optional cloud deployment.

### Docker Engine

Docker builds the generated image and runs the application inside a container with configured resource and privilege restrictions.

### GitHub and Render

GitHub is used for repository operations and optional publishing. Render is used as the cloud deployment target.

---

## Technology Stack

| Technology            | Purpose                        |
| --------------------- | ------------------------------ |
| HTML, CSS, JavaScript | Frontend interface             |
| Python                | Backend and orchestration      |
| FastAPI               | REST API                       |
| Uvicorn               | ASGI server                    |
| Docker                | Containerization and execution |
| Docker SDK for Python | Docker Engine integration      |
| GitPython             | Git repository operations      |
| Server-Sent Events    | Live progress updates          |
| GitHub API            | Repository publishing          |
| Render API            | Cloud deployment               |
| Anthropic API         | Optional AI-assisted patching  |

---

## Project Structure

```text
zero-click-deploy-doctor/
│
├── frontend/
│   └── index.html
│
├── backend/
│   ├── main.py
│   ├── job_manager.py
│   ├── detectors/
│   │   └── stack_detector.py
│   ├── sandbox/
│   │   └── docker_runner.py
│   ├── templates/
│   ├── dockerfile_builder.py
│   ├── source_patcher.py
│   ├── patcher.py
│   ├── security.py
│   ├── env_detector.py
│   ├── deploy_render.py
│   ├── deploy_hf.py
│   ├── requirements.txt
│   └── tests/
│
├── workspace/
├── .env.example
├── main.py
├── start_backend.bat
├── start_frontend.bat
└── README.md
```

### Important Components

| File                                  | Responsibility                                       |
| ------------------------------------- | ---------------------------------------------------- |
| `backend/main.py`                     | FastAPI endpoints and deployment pipeline            |
| `backend/job_manager.py`              | Background jobs, concurrency, and event history      |
| `backend/detectors/stack_detector.py` | Application stack detection                          |
| `backend/dockerfile_builder.py`       | Dockerfile generation                                |
| `backend/source_patcher.py`           | Supported source-level host-binding patches          |
| `backend/patcher.py`                  | Dockerfile diagnostics and automatic corrections     |
| `backend/sandbox/docker_runner.py`    | Image builds, container execution, and health checks |
| `backend/security.py`                 | Potential-secret and sensitive-file scanning         |
| `backend/env_detector.py`             | Required environment-variable detection              |
| `backend/deploy_render.py`            | GitHub publishing and Render deployment integration  |
| `backend/templates/`                  | Stack-specific Dockerfile templates                  |
| `frontend/index.html`                 | User interface and deployment progress               |

---

## Supported Frameworks

The current templates cover the following application types:

| Framework         | Build and Runtime Approach                 |
| ----------------- | ------------------------------------------ |
| Flask             | Python dependencies and Gunicorn           |
| FastAPI           | Python dependencies and Uvicorn            |
| Django            | Python dependencies and development server |
| Express / Node.js | Node.js project configuration              |
| Next.js           | Node.js build and startup scripts          |
| Generic Python    | Python application configuration           |
| Java / Maven      | Maven build and runnable JAR               |
| C++ / CMake       | Native build using CMake                   |

Stack detection is file-based and intentionally conservative. Monorepos, nested application roots, unusual entry points, and nonstandard startup scripts may require manual adjustments.

---

## How to Use

Follow these steps to run Zero-Click Deploy Doctor locally.

### Step 1: Install the Requirements

Install the following on your computer:

* Python 3.11
* Git
* Docker Desktop
* A GitHub account
* A Render account if you want cloud deployment

Start Docker Desktop and ensure that the Docker Engine is running before starting the backend.

Verify Docker using:

```powershell
docker version
```

### Step 2: Configure API Credentials

Generate the required credentials from GitHub and Render.

Set these environment variables in the same PowerShell terminal from which you will start the backend:

```powershell
$env:GITHUB_TOKEN = "your_github_token"
$env:RENDER_API_KEY = "your_render_api_key"
$env:RENDER_OWNER_ID = "your_render_owner_id"
```

For optional AI-assisted Dockerfile patching, configure:

```powershell
$env:ANTHROPIC_API_KEY = "your_anthropic_api_key"
```

The Anthropic API key is optional. Rule-based patching can still be used without it.

**Important:**

* Replace the placeholder values with your actual credentials.
* Never commit real API keys or tokens to GitHub.
* The Render owner ID identifies the configured workspace or owner; it is not the Render API key.
* Keep the backend running in the same environment where these variables are configured.
* Cloud deployment requires the relevant GitHub and Render permissions.

### Step 3: Install Python Dependencies

Open PowerShell in the project root directory and run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

If PowerShell blocks virtual-environment activation, use the environment's Python executable directly.

### Step 4: Start the Backend

From the project root, run:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If your project uses the supplied `start_backend.bat`, you can use that instead.

Verify the backend by opening:

`http://127.0.0.1:8000/health`

The expected response is:

```json
{
  "ok": true,
  "service": "zero-click-deploy-doctor"
}
```

Keep the backend terminal running while using the application.

### Step 5: Open the Frontend

Open the `frontend` folder and launch `index.html` in your browser.

If the frontend does not communicate with the backend when opened directly, start the included frontend server instead.

Open a second PowerShell terminal:

```powershell
cd frontend
py -m http.server 5500
```

Then open:

`http://127.0.0.1:5500`

Make sure the frontend's Backend URL is set to:

`http://127.0.0.1:8000`

### Step 6: Deploy a Repository

Once the frontend is open:

1. Paste a public Git repository URL into the repository field.
2. Configure any optional deployment settings.
3. Start the deployment.
4. Follow the live progress displayed by the frontend.
5. Review the final status, report, and logs if a failure occurs.
6. If cloud deployment was requested, open the returned live URL and verify that the remote service responds.

For an initial test, use a small, conventional application with a clearly defined startup command.

### Step 7: Verify the Deployment

A successful local build and health check mean the application passed the local validation pipeline.

If Render deployment is enabled, open the returned live URL to verify the remote service.

A successful Render API request does not guarantee that the remote build has finished or that the service is healthy.

---

## API Endpoints

The FastAPI backend exposes the following endpoints.

| Method | Endpoint                | Description                                   |
| ------ | ----------------------- | --------------------------------------------- |
| `GET`  | `/health`               | Checks backend availability                   |
| `POST` | `/deploy`               | Runs the synchronous deployment pipeline      |
| `POST` | `/jobs`                 | Creates a background deployment job           |
| `GET`  | `/jobs/{job_id}`        | Returns job status, result, and event history |
| `GET`  | `/jobs/{job_id}/events` | Streams deployment progress using SSE         |

Interactive API documentation is available at:

`http://127.0.0.1:8000/docs`

### Example: Create a Deployment Job

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/owner/repository"}'
```

Example response:

```json
{
  "job_id": "example-job-id",
  "status": "queued",
  "events_url": "/jobs/example-job-id/events",
  "status_url": "/jobs/example-job-id"
}
```

Use the returned job ID to retrieve the status and progress events.

---

## Automated Diagnostics and Recovery

When a Docker build or health check fails, the backend captures available logs and attempts supported corrections.

The recovery process may include:

* Inspecting Docker build output.
* Identifying supported Dockerfile configuration problems.
* Applying targeted Dockerfile corrections.
* Retrying the build within the configured attempt limit.
* Inspecting container logs after a failed health check.
* Returning diagnostic information when automatic recovery is unsuccessful.

The retry count is configurable through `MAX_DEPLOY_ATTEMPTS`. It defaults to six and is restricted to a range of one to ten.

The patcher is not a general-purpose code-repair system. Complex application errors may require manual intervention.

---

## Security

The project includes several measures intended to reduce deployment risks.

* Repository URLs are validated before cloning.
* Potential secrets and sensitive files are scanned before public publishing.
* Docker containers are configured with resource restrictions and selected privilege restrictions.
* Temporary workspaces and containers are cleaned up by the pipeline where possible.
* Cloud credentials are supplied through environment variables rather than committed to source code.

However, running arbitrary repository code is inherently risky. The current container uses a bridge network during health checks, so it should not be treated as a perfectly isolated sandbox.

The application is a hackathon prototype and should not be exposed publicly without additional authentication, rate limiting, stronger isolation, persistent job storage, and audited secret management.

---

## Reliability and Limitations

The current implementation includes background jobs, bounded concurrency, progress streaming, configurable retries, health checks, and diagnostic logging.

Important limitations include:

* Job status and event history are stored in memory and are lost when the backend restarts.
* Stack detection may not support every repository structure.
* Automatic patching covers selected cases rather than arbitrary application failures.
* Secret scanning can produce false positives and false negatives.
* Docker isolation does not guarantee safe execution of hostile code.
* Long-running jobs require correct frontend polling and status reconciliation.
* A successful local health check does not prove that the remote deployment is healthy.
* Cloud deployment requires valid credentials and external service availability.

---

## Testing

Run the backend tests from the backend directory:

```bash
python -m unittest discover -s tests -v
```

The test suite covers selected areas, including stack detection, generated host-binding configuration, source patching, Java template presence, and secret scanning.

These tests do not replace integration testing against a real Docker Engine or cloud provider.

---

## Future Improvements

Potential improvements include:

* Persistent job storage and deployment history.
* More reliable SSE reconnection and frontend polling.
* Improved support for monorepos and nested application roots.
* Stronger sandbox and network isolation.
* More comprehensive failure classification.
* Remote deployment health verification.
* Better secret management and log redaction.
* Authentication, authorization, and rate limiting.
* Expanded framework support and integration tests.

---

## License

Add a `LICENSE` file and update this section with the actual license selected for the project before distributing it.

---

## Conclusion

Zero-Click Deploy Doctor brings repository analysis, Dockerfile generation, container execution, health validation, diagnostics, supported automatic fixes, and optional cloud deployment into a single workflow.

Its goal is to reduce repetitive deployment work, validate applications before publishing them, and help developers understand and resolve common deployment failures.
