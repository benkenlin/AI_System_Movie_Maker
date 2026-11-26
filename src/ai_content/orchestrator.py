"""Deterministic SQLite-backed job orchestration with dependency gating and caching."""
from __future__ import annotations
import uuid
from pathlib import Path
from typing import Any, Iterable
from .db import Database
from .hashing import artifact_key, sha256_file, sha256_json

class OrchestratorError(RuntimeError):
    pass

class Orchestrator:
    def __init__(self, database: Database):
        self.db = database

    def register_project(self, storyboard_path: str | Path) -> str:
        # Import here to preserve the validator as the first mandatory gate.
        from .validation import load_storyboard
        source_path = Path(storyboard_path).expanduser().resolve()
        storyboard = load_storyboard(source_path)
        file_hash = sha256_file(source_path)
        # Keep a managed copy inside the shared project tree so moving the whole
        # repository does not invalidate the SQLite project's storyboard path.
        stored_path = self.db.store_project_file(source_path, content_hash=file_hash)
        project_id = sha256_json({"storyboard_hash": file_hash, "title": storyboard.title})[:24]
        with self.db.transaction() as con:
            con.execute("""INSERT INTO projects
              (id,title,storyboard_path,storyboard_hash,language,subtitle_language)
              VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              storyboard_path=excluded.storyboard_path, storyboard_hash=excluded.storyboard_hash,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
              (project_id, storyboard.title, stored_path, file_hash,
               storyboard.language, storyboard.subtitle_language))
        return project_id

    def create_run(self, project_id: str, config: dict[str, Any] | None = None) -> str:
        run_id = str(uuid.uuid4())
        with self.db.transaction() as con:
            if not con.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                raise OrchestratorError(f"Unknown project: {project_id}")
            con.execute("INSERT INTO runs(id,project_id,status,config_json) VALUES(?,?,?,?)",
                        (run_id, project_id, "pending", self.db.json_dump(config or {})))
            self._event(con, run_id, None, "run_created", {"config": config or {}})
        return run_id

    def add_job(self, run_id: str, *, stage: str, inputs: dict[str, Any],
                subject_id: str = "project", model: str | None = None,
                model_version: str | None = None, config: dict[str, Any] | None = None,
                dependencies: Iterable[str] = (), max_attempts: int = 2) -> tuple[str, bool]:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        key = artifact_key(stage=stage, inputs=inputs, model=model,
                           model_version=model_version, config=config, subject_id=subject_id)
        job_id = str(uuid.uuid4())
        with self.db.transaction() as con:
            run = con.execute("SELECT project_id FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                raise OrchestratorError(f"Unknown run: {run_id}")
            project_id = run["project_id"]
            cached = con.execute("SELECT id FROM artifacts WHERE project_id=? AND artifact_key=?",
                                 (project_id, key)).fetchone()
            for dep_id in dependencies:
                dep = con.execute("SELECT run_id FROM jobs WHERE id=?", (dep_id,)).fetchone()
                if not dep or dep["run_id"] != run_id:
                    raise OrchestratorError(f"Dependency {dep_id} must exist in this run")
            con.execute("""INSERT INTO jobs
              (id,run_id,stage,subject_id,status,input_hash,max_attempts)
              VALUES(?,?,?,?,?,?,?)""",
              (job_id, run_id, stage, subject_id, "succeeded" if cached else "pending", key, max_attempts))
            for dep_id in dependencies:
                con.execute("INSERT INTO job_dependencies(job_id,depends_on_job_id) VALUES(?,?)",
                            (job_id, dep_id))
            self._event(con, run_id, job_id, "cache_hit" if cached else "job_created",
                        {"stage": stage, "subject_id": subject_id, "artifact_key": key})
        return job_id, bool(cached)

    def start_run(self, run_id: str) -> None:
        with self.db.transaction() as con:
            cur = con.execute("""UPDATE runs SET status='running',
              started_at=COALESCE(started_at,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
              WHERE id=? AND status IN ('pending','running')""", (run_id,))
            if cur.rowcount != 1:
                raise OrchestratorError(f"Run cannot be started: {run_id}")
            self._event(con, run_id, None, "run_started", {})

    def claim_ready_job(self, run_id: str, worker: str) -> dict[str, Any] | None:
        """Atomically claim one job whose dependencies all succeeded."""
        with self.db.transaction() as con:
            row = con.execute("""SELECT j.* FROM jobs j
              WHERE j.run_id=? AND j.status IN ('pending','retry_wait')
              AND NOT EXISTS (SELECT 1 FROM job_dependencies d
                JOIN jobs parent ON parent.id=d.depends_on_job_id
                WHERE d.job_id=j.id AND parent.status <> 'succeeded')
              AND (j.next_retry_at IS NULL OR j.next_retry_at <= strftime('%Y-%m-%dT%H:%M:%fZ','now'))
              ORDER BY j.created_at,j.id LIMIT 1""", (run_id,)).fetchone()
            if not row:
                return None
            con.execute("""UPDATE jobs SET status='running',worker=?,attempt=attempt+1,
              started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),finished_at=NULL,error=NULL
              WHERE id=? AND status IN ('pending','retry_wait')""", (worker, row["id"]))
            claimed = con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            self._event(con, run_id, row["id"], "job_claimed",
                        {"worker": worker, "attempt": claimed["attempt"]})
            return dict(claimed)

    def complete_job(self, job_id: str, *, artifact_path: str | Path,
                     media_type: str | None = None,
                     metadata: dict[str, Any] | None = None) -> str:
        path = Path(artifact_path).resolve()
        if not path.is_file():
            raise OrchestratorError(f"Artifact file does not exist: {path}")
        content_hash = sha256_file(path)
        artifact_id = str(uuid.uuid4())
        with self.db.transaction() as con:
            job = con.execute("""SELECT j.*,r.project_id FROM jobs j
              JOIN runs r ON r.id=j.run_id WHERE j.id=?""", (job_id,)).fetchone()
            if not job:
                raise OrchestratorError(f"Unknown job: {job_id}")
            if job["status"] != "running":
                raise OrchestratorError("Only a running job can be completed")
            con.execute("""INSERT INTO artifacts
              (id,project_id,run_id,job_id,stage,subject_id,artifact_key,content_hash,path,media_type,metadata_json)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (artifact_id, job["project_id"], job["run_id"], job_id, job["stage"],
               job["subject_id"], job["input_hash"], content_hash, str(path), media_type,
               self.db.json_dump(metadata or {})))
            con.execute("""UPDATE jobs SET status='succeeded',
              finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""", (job_id,))
            self._event(con, job["run_id"], job_id, "job_succeeded",
                        {"artifact_id": artifact_id, "content_hash": content_hash, "path": str(path)})
        return artifact_id

    def fail_job(self, job_id: str, error: str, retry: bool = True) -> str:
        with self.db.transaction() as con:
            job = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise OrchestratorError(f"Unknown job: {job_id}")
            if job["status"] != "running":
                raise OrchestratorError("Only a running job can fail")
            status = "retry_wait" if retry and job["attempt"] < job["max_attempts"] else "failed"
            con.execute("""UPDATE jobs SET status=?,error=?,
              next_retry_at=CASE WHEN ?='retry_wait' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now','+30 seconds') ELSE NULL END,
              finished_at=CASE WHEN ?='failed' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END
              WHERE id=?""", (status, error, status, status, job_id))
            self._event(con, job["run_id"], job_id, "job_failed", {"status": status, "error": error})
            return status

    def finish_run_if_complete(self, run_id: str) -> str:
        with self.db.transaction() as con:
            # A failed/cancelled prerequisite makes its descendants un-runnable.
            # Mark those jobs stale so the run cannot remain pending forever.
            while True:
                blocked = con.execute("""UPDATE jobs SET status='stale',
                  error='blocked by unsuccessful dependency',
                  finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                  WHERE run_id=? AND status IN ('pending','retry_wait')
                  AND EXISTS (SELECT 1 FROM job_dependencies d
                    JOIN jobs parent ON parent.id=d.depends_on_job_id
                    WHERE d.job_id=jobs.id AND parent.status IN ('failed','cancelled','stale'))""",
                  (run_id,)).rowcount
                if not blocked:
                    break
            statuses = [r["status"] for r in con.execute("SELECT status FROM jobs WHERE run_id=?", (run_id,))]
            if any(s in {"pending", "running", "retry_wait"} for s in statuses):
                return "running"
            status = "failed" if any(s in {"failed", "stale"} for s in statuses) else "succeeded"
            con.execute("UPDATE runs SET status=?,finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                        (status, run_id))
            self._event(con, run_id, None, "run_finished", {"status": status})
            return status

    def status(self, run_id: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            raise OrchestratorError(f"Unknown run: {run_id}")
        jobs = self.db.execute("""SELECT id,stage,subject_id,status,attempt,max_attempts,error
          FROM jobs WHERE run_id=? ORDER BY created_at,id""", (run_id,))
        return {"run": dict(rows[0]), "jobs": [dict(x) for x in jobs]}

    @staticmethod
    def _event(con, run_id, job_id, event_type, details):
        import json
        con.execute("INSERT INTO events(run_id,job_id,event_type,details_json) VALUES(?,?,?,?)",
                    (run_id, job_id, event_type,
                     json.dumps(details, sort_keys=True, ensure_ascii=False, separators=(",", ":"))))

    def recover_stale_jobs(self, run_id: str, older_than_minutes: int = 60) -> int:
        """Move abandoned running jobs to retry_wait or failed after worker loss."""
        if older_than_minutes < 1:
            raise ValueError("older_than_minutes must be at least 1")
        with self.db.transaction() as con:
            rows = con.execute("""SELECT * FROM jobs WHERE run_id=? AND status='running'
              AND started_at < strftime('%Y-%m-%dT%H:%M:%fZ','now',?)""",
              (run_id, f"-{older_than_minutes} minutes")).fetchall()
            for job in rows:
                status = "retry_wait" if job["attempt"] < job["max_attempts"] else "failed"
                con.execute("""UPDATE jobs SET status=?,worker=NULL,error='worker heartbeat expired',
                  next_retry_at=CASE WHEN ?='retry_wait' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END,
                  finished_at=CASE WHEN ?='failed' THEN strftime('%Y-%m-%dT%H:%M:%fZ','now') ELSE NULL END
                  WHERE id=?""", (status, status, status, job["id"]))
                self._event(con, run_id, job["id"], "job_recovered_as_stale", {"new_status": status})
            return len(rows)

    def export_events_jsonl(self, run_id: str, destination: str | Path) -> Path:
        """Export durable DB events as one JSON object per line for submission/audit."""
        import json
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        events = self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))
        with path.open("w", encoding="utf-8") as stream:
            for event in events:
                item = dict(event)
                item["details"] = json.loads(item.pop("details_json"))
                stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        return path
