# Development and Design Specification

## 1. Design principles

1. **Storyboard as contract:** all stages share one validated source of creative truth.
2. **Deterministic orchestration:** the runtime pipeline is Python-controlled; LLMs generate/critique content but do not schedule arbitrary jobs.
3. **Incremental production:** hash-based cache keys limit expensive regeneration to changed dependencies.
4. **Graceful degradation:** Wan failure falls back to Ken Burns rather than abandoning the film.
5. **Auditable decisions:** calls, retries, selection rationale, failures, experiments and review decisions are written down.
6. **Ethical release:** consent, license/output-rights review, native-speaker review and AI disclosure are release gates.

## 2. Development stages

- Repository skeleton: schema, Pydantic models, validation, database and JSONL logger.
- Planning: Gemini JSON draft, bounded repairs and human approval.
- Visual stage: character anchors, keyframes, approval hash and video worker.
- Audio stage: cue-aware score brief, three ACE-Step candidates, automated scoring and Gemini TTS per shot.
- Assembly: FFmpeg normalization, narration alignment, ducking, subtitles, loudness and two aspect ratios.
- Release: technical QC, consent/license review and native-speaker approval.

## 3. User-interface design changes

The revised UI removes the manual music dropdown, user-written music rationale and free-form narration review notes. The application now generates candidates, scores them and persists a rationale. It automatically produces a narration technical audit report. The only remaining narration UI action is the required native-speaker identity and explicit attestation after listening to the audio.

## 4. Test strategy

- Unit tests: schema constraints, relationships, cache hashing, music scoring and ethics gates.
- Adapter tests: mocked HTTP responses for Cloudflare and Gemini to verify request/response handling without credentials.
- Worker contract tests: validate JSON payload and missing configuration failures.
- Integration smoke test: synthetic clips/audio through FFmpeg, checking output ratios, audio stream, subtitles and disclosure source.
- Live deployment test: one Gemini planning/TTS request, one Cloudflare image, one ACE-Step candidate, one Wan shot, followed by full pipeline. Record real latency, GPU minutes, quotas and errors.
- User testing: show narration-only cut and near-final film to at least three intended audience members at each stage; document feedback and storyboard changes in `DESIGN.md`.

## 5. Acceptance criteria

A clean clone can install dependencies, validate the storyboard, start the UI and run tests. With real credentials and GPU endpoints configured, the system can generate all required stage artifacts, resume unchanged assets, produce both MP4 formats and block release until required evidence is complete.

## 6. Known limits

- External API model IDs and quotas may change.
- GPU availability and Wan memory fit vary by notebook/provider.
- Technical audio metrics do not judge emotional acting or language fidelity.
- Music ranking is objective/technical; it cannot replace a listener's artistic or cultural judgement.
- The system cannot fabricate audience research, human review, measured cost or successful live inference evidence.
