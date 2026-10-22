"""In-memory bounded deployment job manager with event history for SSE clients."""
from __future__ import annotations
import threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from collections import deque

MAX_WORKERS = 2
MAX_QUEUED = 12
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="deploy-job")
_lock = threading.RLock()
_jobs = {}
_waiting = 0

def create_job(payload: dict) -> str:
    global _waiting
    with _lock:
        active = sum(1 for j in _jobs.values() if j["status"] in {"queued", "running"})
        if active >= MAX_WORKERS + MAX_QUEUED:
            raise RuntimeError("Deployment queue is full. Try again shortly.")
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {"id": job_id, "status": "queued", "created_at": time.time(),
                         "events": deque(maxlen=500), "result": None, "condition": threading.Condition(_lock)}
        emit(job_id, "queued", "Deployment queued.")
        return job_id

def emit(job_id: str, stage: str, message: str, **data):
    with _lock:
        job = _jobs.get(job_id)
        if not job: return
        event = {"id": len(job["events"]) + 1, "stage": stage, "message": message, "time": time.time(), **data}
        job["events"].append(event)
        if stage not in {"queued", "complete", "failed"}:
            job["status"] = "running"
        if stage in {"complete", "failed"}:
            job["status"] = stage
        job["condition"].notify_all()

def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if not job: return None
        return {"id": job["id"], "status": job["status"], "result": job["result"],
                "events": list(job["events"]), "created_at": job["created_at"]}

def set_result(job_id: str, result: dict):
    with _lock:
        if job_id in _jobs: _jobs[job_id]["result"] = result

def submit(job_id: str, fn, *args):
    def run():
        try:
            result = fn(*args)
            set_result(job_id, result)
            emit(job_id, "complete" if result.get("status") == "success" else "failed",
                 result.get("report") or ("Deployment successful." if result.get("status") == "success" else "Deployment failed."),
                 result=result)
        except Exception as exc:
            result = {"status": "failed", "report": str(exc)}
            set_result(job_id, result)
            emit(job_id, "failed", str(exc), result=result)
    executor.submit(run)

def wait_events(job_id: str, after_id: int, timeout: float = 15):
    with _lock:
        job = _jobs.get(job_id)
        if not job: return None, []
        available = [e for e in job["events"] if e["id"] > after_id]
        if not available and job["status"] not in {"complete", "failed"}:
            job["condition"].wait(timeout=timeout)
            available = [e for e in job["events"] if e["id"] > after_id]
        return job["status"], available
