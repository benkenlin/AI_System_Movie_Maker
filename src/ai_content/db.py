"""SQLite persistence for projects, runs, jobs, artifacts and audit events."""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, storyboard_path TEXT NOT NULL,
 storyboard_hash TEXT NOT NULL, language TEXT NOT NULL, subtitle_language TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','cancelled')),
 config_json TEXT NOT NULL DEFAULT '{}', started_at TEXT, finished_at TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), error TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 stage TEXT NOT NULL, subject_id TEXT NOT NULL DEFAULT 'project',
 status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','retry_wait','failed','cancelled','stale')),
 input_hash TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt >= 0),
 max_attempts INTEGER NOT NULL DEFAULT 2 CHECK(max_attempts >= 1), worker TEXT,
 started_at TEXT, finished_at TEXT, next_retry_at TEXT, error TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(run_id,stage,subject_id,input_hash)
);
CREATE TABLE IF NOT EXISTS job_dependencies (
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 depends_on_job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 PRIMARY KEY(job_id,depends_on_job_id), CHECK(job_id <> depends_on_job_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
 job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
 stage TEXT NOT NULL, subject_id TEXT NOT NULL DEFAULT 'project', artifact_key TEXT NOT NULL,
 content_hash TEXT NOT NULL, path TEXT NOT NULL, media_type TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(project_id,artifact_key)
);
CREATE TABLE IF NOT EXISTS storyboard_drafts (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, idea TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL, planner TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending_approval','needs_revision','approved','rejected')),
 repair_attempts INTEGER NOT NULL DEFAULT 0, issues_json TEXT NOT NULL DEFAULT '[]',
 approved_project_id TEXT REFERENCES projects(id), approved_path TEXT, rejection_reason TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON storyboard_drafts(status,created_at);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
 job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE, event_type TEXT NOT NULL,
 details_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_run_status ON jobs(run_id,status);
CREATE INDEX IF NOT EXISTS idx_jobs_input_hash ON jobs(input_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_stage ON artifacts(project_id,stage);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id,id);
"""

class Database:
    def __init__(self, path: str | Path):
        # SQLite's special in-memory database name must be passed through
        # literally; treating it as a filesystem path breaks on Windows.
        self._is_memory = str(path) == ":memory:"
        self.path = Path(":memory:") if self._is_memory else Path(path).expanduser().resolve()
        self._memory_connection: sqlite3.Connection | None = None
        if self._is_memory:
            self._memory_connection = sqlite3.connect(
                ":memory:", timeout=30, isolation_level=None
            )
            self._configure(self._memory_connection)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @property
    def project_root(self) -> Path:
        """Resolve the shared project root from the database location.

        The standard layout is <project>/outputs/system.db. For custom database
        locations, the database's parent directory is treated as the root.
        """
        return self.path.parent.parent if self.path.parent.name == "outputs" else self.path.parent

    def store_project_file(self, source: str | Path, *, category: str = "storyboards",
                           content_hash: str | None = None) -> str:
        """Copy a project input into the shared project tree and return a portable path."""
        import shutil
        from .hashing import sha256_file

        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Project input file not found: {source_path}")
        digest = content_hash or sha256_file(source_path)
        suffix = source_path.suffix or ".json"
        destination = self.project_root / "assets" / category / f"{digest}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or sha256_file(destination) != digest:
            shutil.copy2(source_path, destination)
        return destination.relative_to(self.project_root).as_posix()

    def resolve_project_file(self, stored_path: str | Path, *, expected_hash: str | None = None) -> Path:
        """Resolve portable paths and recover legacy absolute paths after a folder move."""
        from .hashing import sha256_file

        value = Path(stored_path).expanduser()
        candidates = []
        if value.is_absolute():
            candidates.append(value)
        else:
            candidates.append(self.project_root / value)
        for candidate in candidates:
            if candidate.is_file():
                if expected_hash is None or sha256_file(candidate) == expected_hash:
                    return candidate.resolve()

        # Backward compatibility for databases created before paths became portable.
        search_roots = [self.project_root / "assets" / "storyboards",
                        self.project_root / "outputs" / "approved",
                        self.project_root / "examples"]
        for root in search_roots:
            if root.exists():
                for candidate in root.rglob("*.json"):
                    if expected_hash is None or sha256_file(candidate) == expected_hash:
                        return candidate.resolve()
        raise FileNotFoundError(
            f"Storyboard file not found: {stored_path}. Expected it under project root "
            f"{self.project_root}; restore the storyboard or re-register the project."
        )

    @staticmethod
    def _configure(con: sqlite3.Connection) -> None:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")

    def connect(self) -> sqlite3.Connection:
        if self._is_memory:
            # Keep one connection alive so the in-memory database persists
            # across service methods that call connect().
            assert self._memory_connection is not None
            return self._memory_connection
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self._configure(con)
        return con

    def initialize(self) -> None:
        con = self.connect()
        try:
            if not self._is_memory:
                con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        finally:
            if not self._is_memory:
                con.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            if not self._is_memory:
                con.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        con = self.connect()
        try:
            return list(con.execute(sql, params))
        finally:
            if not self._is_memory:
                con.close()

    def close(self) -> None:
        """Close the retained in-memory connection, if this is an in-memory DB."""
        if self._memory_connection is not None:
            self._memory_connection.close()
            self._memory_connection = None

    @staticmethod
    def json_dump(value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
