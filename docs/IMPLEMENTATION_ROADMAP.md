# Implementation roadmap — challenge-first

## Target deliverable

A reproducible, documented pipeline that takes a reviewed storyboard and produces a short,
narration-led film, with an animatic fallback that completes even if cloud GPU generation fails.

## Phase 0 — Foundation (first)
- Python package, Git, configuration, structured logs.
- Storyboard JSON contract, JSON Schema, semantic validation.
- Unit tests and a CLI.
- **Exit criterion:** the example passes; intentionally invalid examples fail with actionable errors.

## Phase 1 — Orchestration and provenance
- SQLite job/run registry.
- Explicit job states: pending, running, succeeded, retry_wait, failed, cancelled, stale.
- Content-addressed artifact keys (SHA-256 over normalized inputs + model/config versions).
- Atomic writes, artifact manifest, run log (`runs.jsonl`).
- **Exit criterion:** changing narration for one shot invalidates narration/subtitles/assembly only.

## Phase 2 — Planning and human review
- LLM planner adapter creates a draft storyboard.
- Critic/repair pass is bounded (one or two repairs, never an infinite loop).
- Human approves storyboard before any generation.
- Store prompt/model/version and approval timestamp.
- **Exit criterion:** a human-approved storyboard is saved and validated.

## Phase 3 — Character references and keyframes
- Generate character reference sheets.
- Generate one keyframe per shot conditioned on reference sheets.
- Build contact sheet and review gate.
- Track prompt, seed, model, image hash, and reviewer decision.
- **Exit criterion:** all shots have approved keyframes.

## Phase 4 — Animatic before video
- Turn approved stills into motion using FFmpeg (Ken Burns/pan/zoom).
- Use measured narration durations and storyboard timing.
- Generate both 16:9 and 9:16 previews.
- **Exit criterion:** a complete, watchable film can be exported without a video model.

## Phase 5 — Cloud video workers
- Add a model adapter for Wan 2.2 TI2V-5B or a viable alternative.
- Run one shot per task in a cloud GPU session.
- Checkpoint each completed shot to durable storage immediately.
- Bound retries; fall back to the approved still animation after the retry budget.
- **Exit criterion:** at least one approved shot can be generated, downloaded, and substituted into the animatic.

## Phase 6 — Narration and music
- TTS adapter produces one audio file per shot.
- Maintain pronunciation lexicon; obtain native-speaker review for target-language narration.
- Music adapter generates several candidates; score and record selection rationale.
- **Exit criterion:** narration and music are reviewed, measured, and linked to the storyboard.

## Phase 7 — Assembly and quality control
- Normalize frame rate, dimensions, pixel format, and audio sample rate.
- Fit visuals to measured narration length; hold/slow/extend still animation instead of regenerating video.
- Mix narration/music with ducking; loudness normalization.
- Generate English subtitles and burn them in.
- Export horizontal 16:9 and vertical 9:16 with per-shot crop positions.
- Run ffprobe checks, subtitle sync checks, loudness checks, and disclosure check.
- **Exit criterion:** both final files pass automated QC and human review.

## Phase 8 — Challenge evidence and report
- `DESIGN.md`: architecture and design decisions.
- `ETHICS.md`: likeness/voice consent, AI labelling, model/output licences, private-data policy.
- `README.md`: setup, commands, reproducibility, known limitations.
- `runs.jsonl`: model calls, parameters, latency, failures, retries, artifact paths, costs where known.
- Record audience tests (at least two rounds, three or more people each, per the design brief).
- Include one measured experiment and explain what it changed in the design.

## Critical challenge priorities

1. A complete working pipeline with fallback is more valuable than an ambitious collection of disconnected model demos.
2. Keep the storyboard as the single contract.
3. Human approval gates must precede expensive video generation and release.
4. Real faces/voices without documented informed consent block release.
5. Preserve provenance/watermarks and include an AI disclosure end card.
6. Record model versions and licences; re-check provider terms before use.
7. Keep private family details out of free endpoints unless their data-use terms are acceptable.

## Cloud execution pattern

Local machine:
- storyboard editing and validation
- SQLite job state and orchestration
- review UI/contact sheets
- final assembly and report

Cloud worker:
- receives a job manifest and required assets
- checks out pinned model/code versions
- runs one bounded task
- uploads outputs and metadata to durable storage
- returns a success/failure manifest

Do not treat an ephemeral notebook filesystem as durable storage. A disconnected GPU session must
not destroy completed work.

## Phase 1 implementation notes

SQLite is the local source of truth for project/run/job state. WAL mode and `BEGIN IMMEDIATE`
transactions serialize claims so two local workers should not claim the same pending job.
The cloud worker must never treat its notebook filesystem as authoritative: it downloads a job
manifest, executes one task, uploads artifacts, and reports the artifact path/hash. The local
orchestrator records completion only after it can verify the uploaded artifact.

The artifact key includes stage, input values, model identifier/version, config and key version.
Callers must include parent artifact content hashes in downstream `inputs`; this is how upstream
changes invalidate downstream cache entries. Model outputs can be nondeterministic, so hashes
identify actual produced bytes and cache identity, not guaranteed repeatability of inference.
