"""
Env Var Detector
----------------
Reads .env.example (or similar) and extracts required variable names.
We NEVER guess values — if the repo needs secrets, the user must supply
them. This avoids silently deploying an app with broken/placeholder
credentials that "builds" but doesn't actually work.
"""

import re
from typing import List


def extract_required_env_vars(env_example_path: str) -> List[str]:
    if not env_example_path:
        return []
    try:
        with open(env_example_path, "r", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return []

    names = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m:
            names.append(m.group(1))
    return names
