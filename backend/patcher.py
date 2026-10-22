"""
Patcher
-------
When a build or run fails, we hand the error log + current Dockerfile to an
LLM and ask for a MINIMAL patch — not a rewrite. This keeps the "template +
targeted fix" reliability property intact instead of letting the LLM
regenerate the whole file (which is where flakiness creeps back in).

Falls back to a small set of rule-based fixes for the most common failure
patterns if no ANTHROPIC_API_KEY is set, so the demo never hard-blocks on
missing credentials.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None


@dataclass
class PatchResult:
    patched_dockerfile: str
    explanation: str
    used_llm: bool


RULE_BASED_FIXES = [
    # (pattern to search in logs, fix function)
    (
        re.compile(r"ModuleNotFoundError: No module named '([\w\-\.]+)'", re.IGNORECASE),
        lambda m, dockerfile: dockerfile.replace(
            "RUN pip install --no-cache-dir --upgrade pip && \\",
            f"RUN pip install --no-cache-dir --upgrade pip && \\\n    pip install --no-cache-dir {m.group(1)} && \\",
        ),
    ),
    (
        re.compile(r"gcc.*not found|error: command 'gcc' failed", re.IGNORECASE),
        lambda m, dockerfile: dockerfile if "gcc" in dockerfile else dockerfile.replace(
            "WORKDIR /app", "WORKDIR /app\nRUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*"
        ),
    ),
    (
        re.compile(r"npm ERR!.*peer dep|ERESOLVE", re.IGNORECASE),
        lambda m, dockerfile: dockerfile.replace("npm ci --omit=dev || npm install --omit=dev", "npm install --omit=dev --legacy-peer-deps"),
    ),
    (
        re.compile(r"EADDRINUSE|address already in use", re.IGNORECASE),
        lambda m, dockerfile: dockerfile,  # not a Dockerfile issue — port collision on our side; no-op
    ),
]


def _rule_based_patch(dockerfile: str, logs: str) -> Optional[PatchResult]:
    for pattern, fix_fn in RULE_BASED_FIXES:
        m = pattern.search(logs)
        if m:
            new_dockerfile = fix_fn(m, dockerfile)
            if new_dockerfile != dockerfile:
                return PatchResult(
                    patched_dockerfile=new_dockerfile,
                    explanation=f"Rule-based fix applied for pattern: {pattern.pattern}",
                    used_llm=False,
                )
    return None


def _llm_patch(dockerfile: str, logs: str, stack: str) -> Optional[PatchResult]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or anthropic is None:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""You are fixing a Dockerfile that failed to build or run. Stack: {stack}.

Current Dockerfile:
```
{dockerfile}
```

Build/run error log (last part):
```
{logs[-3000:]}
```

Make the SMALLEST possible change to the Dockerfile to fix this specific error.
Do not rewrite unrelated parts. Do not change the base image unless that is the
actual problem. Return ONLY the full corrected Dockerfile, no explanation, no
markdown fences."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        patched = resp.content[0].text.strip()
        # strip accidental markdown fences
        patched = re.sub(r"^```[\w]*\n", "", patched)
        patched = re.sub(r"\n```$", "", patched)
        if patched and patched != dockerfile:
            return PatchResult(patched_dockerfile=patched, explanation="LLM-generated targeted patch based on error log.", used_llm=True)
    except Exception:
        return None
    return None


def patch_dockerfile(dockerfile: str, logs: str, stack: str) -> Optional[PatchResult]:
    """Try LLM patch first (more general), fall back to rules."""
    result = _llm_patch(dockerfile, logs, stack)
    if result:
        return result
    return _rule_based_patch(dockerfile, logs)
