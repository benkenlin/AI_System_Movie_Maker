# Phase 1 — SQLite orchestrator and artifact identity

## What is implemented

1. **Project registration:** validates the storyboard first, computes its file SHA-256, and stores language metadata (`am` narration, `en` subtitles).
2. **Run registry:** each execution has a UUID, config snapshot, lifecycle status and timestamps.
3. **Job registry:** jobs have stage/subject identifiers, status, attempt counters, retry metadata and worker assignment.
4. **Dependency graph:** a job can be claimed only after every prerequisite succeeds. Dependencies must be created earlier in the same run, which enforces a topological insertion order and prevents cycles through this API.
5. **Atomic claims:** SQLite `BEGIN IMMEDIATE` transactions prevent concurrent local workers from claiming the same pending job.
6. **Artifact identity:** SHA-256 hashes canonical JSON inputs and actual output bytes. Model name/version and render config are part of the cache key.
7. **Cache reuse:** a previously completed artifact with the same project and artifact key creates a cache-hit job that does not need a worker claim.
8. **Bounded retries:** attempts stop at `max_attempts`; worker-loss recovery can move abandoned jobs to retry or failure.
9. **Auditability:** important run/job transitions are persisted in SQLite and exportable as `runs.jsonl`.
10. **Failure propagation:** jobs blocked by a failed prerequisite become `stale`; the run can finish as failed rather than remaining pending forever.

## Key engineering decisions

- SQLite is the local orchestration database, not a cloud notebook database.
- WAL mode supports concurrent readers; write claims use explicit immediate transactions.
- The cloud worker should be stateless between jobs and checkpoint artifacts to durable object storage.
- Every downstream job must include parent artifact content hashes in its `inputs` so cache invalidation follows the dependency graph.
- Cache identity is not the same as model determinism. It identifies the exact requested computation and the actual bytes produced.
- `subject_id` is included in artifact identity so two different shots do not accidentally collide merely because their prompt text happens to match.

## Known limitations / Phase 2+ work

- The orchestrator is a scheduling/persistence layer; it does not yet launch remote Kaggle/Colab jobs.
- Retry delay is currently a simple 30-second delay, not exponential backoff with provider-aware quota handling.
- There is no lease heartbeat protocol yet. Stale recovery uses a started-at age threshold.
- Artifacts are currently recorded by filesystem path. A cloud adapter must upload to durable storage and verify the downloaded/remote content hash before registering success.
- Cache-hit jobs are marked succeeded; the worker/assembly layer must query the artifact table by project and artifact key to obtain the reused path.
- A production system should add migrations, structured logging, cancellation propagation, storage checksums, and explicit worker lease tokens.

## Validation evidence

`pytest -q`: **15 tests passed**. Tests cover deterministic hashing, cache-key sensitivity, validator gating, dependency blocking, artifact persistence/reuse, retry bounds, failed-dependency propagation and JSONL event export.
