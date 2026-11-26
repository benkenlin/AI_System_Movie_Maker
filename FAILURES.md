# Failure journal

Record each actual failure with timestamp, stage, model/version, seed, input hash, exact error, attempted fixes, final resolution, and whether the failure is reproducible. Do not invent incidents.

## Known operational risks and designed mitigations

- Provider model IDs and quotas change: keep model IDs configurable and verify the endpoint/model page before a run.
- API quota/network failure: bounded retries, JSONL logs, hash-based reuse; resume later without repeating successful stages.
- Wan worker OOM/session expiry: process one shot at a time, persist checkpoints, reduce resolution/frame count, then Ken Burns fallback.
- Music worker unavailable: keep music generation separate from assembly; stop with a clear worker/API error and resume after the ACE-Step service is restored. The selector never substitutes stock music.
- TTS pronunciation errors: use lexicon substitutions and native-speaker review; regenerate only the affected shot.
- Consent/license gaps: release gate blocks publication.
- FFmpeg/codec/font differences: record FFmpeg version, inspect ffprobe metadata, and rerun technical QC.

## Actual incidents

No live provider or GPU failures are recorded in this snapshot. Add incidents below as they occur.
