"""Render a stack-specific, conservative Dockerfile."""
import json, os
from detectors.stack_detector import StackInfo

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
STACK_TO_TEMPLATE = {
    "flask":"flask.Dockerfile.j2", "fastapi":"fastapi.Dockerfile.j2",
    "django":"python-generic.Dockerfile.j2", "python-generic":"python-generic.Dockerfile.j2",
    "express":"node.Dockerfile.j2", "node-generic":"node.Dockerfile.j2", "nextjs":"node.Dockerfile.j2",
    "java-maven":"java-maven.Dockerfile.j2", "cpp-cmake":"cpp-cmake.Dockerfile.j2",
}

def _simple_render(text, context):
    for key, value in context.items(): text = text.replace("{{ "+key+" }}", str(value))
    return text

def build_dockerfile(stack_info: StackInfo) -> str:
    template_name = STACK_TO_TEMPLATE.get(stack_info.stack)
    if not template_name: raise ValueError(f"No Dockerfile template available for stack '{stack_info.stack}'")
    with open(os.path.join(TEMPLATE_DIR, template_name), encoding="utf-8") as f: template = f.read()
    run_cmd = (stack_info.run_cmd or "").replace("{PORT}", str(stack_info.port))
    run_json = json.dumps(["sh","-c",run_cmd]) if any(op in run_cmd for op in ("&&","||","|",";","*")) else json.dumps(run_cmd.split())
    rendered = _simple_render(template, {"port":stack_info.port, "run_cmd_json":run_json,
                                         "requirements_file":stack_info.dependency_file or "requirements.txt"})
    if stack_info.stack == "nextjs":
        rendered = rendered.replace("npm ci --omit=dev || npm install --omit=dev", "npm ci || npm install")
    if stack_info.stack in {"flask","fastapi","django","python-generic"}:
        old = "pip install --no-cache-dir -r "+(stack_info.dependency_file or "requirements.txt")
        if stack_info.dependency_file == "pyproject.toml":
            install = "pip install --no-cache-dir ."
        elif stack_info.dependency_file == "Pipfile":
            install = "pip install --no-cache-dir pipenv && pipenv install --system --deploy"
        elif stack_info.dependency_file == "requirements.txt":
            install = old
        else:
            install = ("pip install --no-cache-dir fastapi uvicorn" if stack_info.stack == "fastapi" else "pip install --no-cache-dir django" if stack_info.stack == "django" else "pip install --no-cache-dir flask gunicorn" if stack_info.stack == "flask" else "pip install --no-cache-dir gunicorn")
        if stack_info.stack == "flask" and stack_info.dependency_file != "requirements.txt": install += " gunicorn"
        rendered = rendered.replace(old, install)
    return rendered
