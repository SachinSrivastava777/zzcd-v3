"""File-based stack detection used by Zero-Click Deploy Doctor."""
import json, os, re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class StackInfo:
    stack: str
    language: str
    entry_point: Optional[str] = None
    port: int = 8000
    dependency_file: Optional[str] = None
    install_cmd: Optional[str] = None
    run_cmd: Optional[str] = None
    env_example_path: Optional[str] = None
    notes: list = field(default_factory=list)

def _read(path):
    try:
        with open(path, "r", errors="ignore") as f: return f.read()
    except (OSError, TypeError): return ""

def _find_env_example(root):
    for name in (".env.example", ".env.sample", "env.example", ".env.template"):
        path = os.path.join(root, name)
        if os.path.isfile(path): return path
    return None

def _guess_port(text, default):
    patterns = [
        r'app\.run\([^)]*port\s*=\s*(\d{3,5})',
        r'listen\(\s*(\d{3,5})',
        r'PORT\s*(?:=|:|\|\|)\s*["\']?(\d{3,5})',
        r'getenv\(["\']PORT["\']\s*,\s*["\']?(\d{3,5})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try: return int(match.group(1))
            except ValueError: pass
    return default

def _detect_python(root):
    files = os.listdir(root)
    dep = next((n for n in ("requirements.txt", "pyproject.toml", "Pipfile") if os.path.isfile(os.path.join(root,n))), None)
    entry = next((n for n in ("app.py","main.py","run.py","server.py","wsgi.py","manage.py") if os.path.isfile(os.path.join(root,n))), None)
    if not entry:
        entry = next((n for n in files if n.endswith(".py") and "__main__" in _read(os.path.join(root,n))), None)
    source = _read(os.path.join(root, entry)) if entry else ""
    all_text = source + "\n" + (_read(os.path.join(root,dep)) if dep else "")
    if "manage.py" in files and ("django" in all_text.lower() or os.path.exists(os.path.join(root,"settings.py"))):
        stack, port, run = "django", 8000, "python manage.py runserver 0.0.0.0:{PORT}"
    elif re.search(r'from\s+flask|import\s+flask|Flask\(', all_text, re.I):
        stack, port, run = "flask", _guess_port(all_text, 5000), "gunicorn --bind 0.0.0.0:{PORT} app:app"
        # Use detected entry module and conventional app object; fallback source patch handles direct run.
        module = ((entry or "app.py")[:-3] if (entry or "app.py").endswith(".py") else (entry or "app.py"))
        run = f"gunicorn --bind 0.0.0.0:{{PORT}} {module}:app"
    elif re.search(r'\bFastAPI\b|from\s+fastapi', all_text):
        stack, port = "fastapi", _guess_port(all_text, 8000)
        module = ((entry or "main.py")[:-3] if (entry or "main.py").endswith(".py") else (entry or "main.py"))
        run = f"uvicorn {module}:app --host 0.0.0.0 --port {{PORT}}"
    else:
        stack, port = "python-generic", _guess_port(all_text, 8000)
        run = f"python {entry}" if entry else "python app.py"
    info = StackInfo(stack, "python", entry, port, dep,
        "pip install --no-cache-dir -r requirements.txt" if dep == "requirements.txt" else "pip install --no-cache-dir -e .",
        run, _find_env_example(root))
    if not dep: info.notes.append("No Python dependency manifest found.")
    if not entry: info.notes.append("Entry point uncertain; review generated run command.")
    return info

def _detect_node(root):
    pkg_path = os.path.join(root,"package.json")
    try: pkg = json.loads(_read(pkg_path) or "{}")
    except json.JSONDecodeError: pkg = {}
    scripts, deps = pkg.get("scripts",{}) or {}, {**(pkg.get("dependencies",{}) or {}), **(pkg.get("devDependencies",{}) or {})}
    entry = pkg.get("main") or ("server.js" if os.path.isfile(os.path.join(root,"server.js")) else "index.js")
    text = json.dumps(pkg)
    for name in (entry,"server.js","app.js","index.js"):
        text += "\n" + _read(os.path.join(root,name))
    port = _guess_port(text, 3000)
    if "next" in deps:
        stack, port, run = "nextjs", _guess_port(text, 3000), "npm run build && npm run start -- --hostname 0.0.0.0 --port {PORT}"
    elif "express" in deps or re.search(r'require\(["\']express["\']\)|from\s+["\']express["\']',text):
        stack, run = "express", ("npm start" if "start" in scripts else f"node {entry}")
    else:
        stack, run = "node-generic", ("npm start" if "start" in scripts else f"node {entry}")
    return StackInfo(stack,"node",entry,port,"package.json","npm ci --omit=dev || npm install --omit=dev",run,_find_env_example(root),
                     [] if os.path.isfile(pkg_path) else ["No package.json found."])

def detect_stack(repo_path: str) -> StackInfo:
    if os.path.isfile(os.path.join(repo_path,"package.json")): return _detect_node(repo_path)
    if any(os.path.isfile(os.path.join(repo_path,n)) for n in ("requirements.txt","pyproject.toml","Pipfile","manage.py")):
        return _detect_python(repo_path)
    if os.path.isfile(os.path.join(repo_path,"pom.xml")):
        return StackInfo("java-maven","java","pom.xml",8080,"pom.xml","mvn -DskipTests package","java -jar target/*.jar",_find_env_example(repo_path))
    if os.path.isfile(os.path.join(repo_path,"CMakeLists.txt")):
        return StackInfo("cpp-cmake","cpp","CMakeLists.txt",8080,"CMakeLists.txt","cmake -S . -B build && cmake --build build","./build/app",_find_env_example(repo_path),
                         ["C++ apps must expose an HTTP service on port 8080 for deployment health checks."])
    return StackInfo("unknown","unknown",notes=["Could not detect a supported stack from repository files."])
