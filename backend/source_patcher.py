"""Conservative source-level host-binding fixes for common web frameworks."""
from __future__ import annotations

import os, re
from dataclasses import dataclass

@dataclass
class SourcePatchResult:
    changed: bool
    files: list[str]
    notes: list[str]

def patch_source_host_binding(repo_path: str, stack: str, port: int) -> SourcePatchResult:
    changed, files, notes = False, [], []
    candidates = []
    for root, dirs, names in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "dist", "build"}]
        for name in names:
            if name.endswith(".py") or (stack in {"express", "node-generic", "nextjs"} and name.endswith((".js", ".cjs", ".mjs", ".ts"))):
                candidates.append(os.path.join(root, name))
    for path in candidates[:1000]:
        try:
            original = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        updated = original
        if stack == "flask":
            # Only alter calls that do not already specify a host; avoid duplicate keyword args.
            def flask_run(match):
                args = match.group(1).strip()
                if "host=" in args or "host =" in args:
                    return match.group(0)
                prefix = args + ", " if args else ""
                if "port=" not in args and "port =" not in args:
                    prefix += f'port=int(os.environ.get("PORT", "{port}")), '
                return "app.run(" + prefix + 'host="0.0.0.0")'
            updated = re.sub(r'app\.run\(([^)]*)\)', flask_run, updated)
            if updated != original and "import os" not in updated:
                # Place import after a module docstring when one exists; prepend is valid except shebang.
                lines = updated.splitlines()
                insert_at = 1 if lines and lines[0].startswith("#!") else 0
                lines.insert(insert_at, "import os")
                updated = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
            if updated != original:
                notes.append("Made Flask app.run bind to 0.0.0.0 and honor PORT.")
        elif stack in {"express", "node-generic"}:
            # app.listen(PORT) can be exposed on all interfaces by Node, but explicit host is clearer.
            updated = re.sub(r'\.listen\(\s*(process\.env\.PORT\s*\|\|\s*\d+|PORT)\s*\)', r'.listen(\1, "0.0.0.0")', updated)
            if updated != original:
                notes.append("Made Node listen call explicitly bind to 0.0.0.0.")
        if updated != original:
            try:
                with open(path, "w", encoding="utf-8") as f: f.write(updated)
                changed = True
                files.append(os.path.relpath(path, repo_path))
            except OSError:
                pass
    return SourcePatchResult(changed, files, notes)
