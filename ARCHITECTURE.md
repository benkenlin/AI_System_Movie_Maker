# Architecture

The detailed architecture is maintained in [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) and [`docs/TECHNICAL_DESIGN.md`](docs/TECHNICAL_DESIGN.md).

## Contract and stages

`storyboard.json` is the validated creative contract shared by the production stages. The deterministic Python orchestrator and stage services perform: (1) Gemini storyboard planning and human approval; (2) Cloudflare FLUX character references and keyframes; (3) Wan 2.2 TI2V-5B shot generation with Ken Burns fallback; (4) ACE-Step 1.5 score generation, three-candidate technical scoring and automatic selection with a persisted rationale; (5) Gemini TTS per-shot narration; and (6) FFmpeg assembly, subtitles, ducking, loudness normalization, dual exports and final QC.

## Interfaces and deployment

`ImageProvider`, `SpeechProvider`, and `MediaGenerationProvider` define replaceable provider contracts. Gemini and Cloudflare use HTTPS API requests. Video can use the local Wan CLI worker or an authenticated remote HTTP worker. Music uses the ACE-Step asynchronous API through `workers/ace_step_worker.py`. GPU workers can run on a separate Kaggle/Colab/local host.

## Cache and recovery

Production artifacts use SHA-256 input hashes and `.meta.json` sidecars. The SQLite orchestrator separately tracks projects, runs, job dependencies and artifacts. Keyframe approval hashes prevent a changed frame from silently entering video generation. Retries are bounded and logged. Wan failures use a Ken Burns fallback; successful artifacts are reused on reruns.

## Audio review and release

Music is selected automatically using Gemini audio-fit screening plus duration, loudness and peak-headroom metrics; the selection rationale and ranking report are persisted. Gemini performs a multimodal screening of narration audio against scripts and English subtitles, while technical checks measure file validity, duration, silence, clipping and pacing. A native speaker must still listen to all lines and explicitly approve pronunciation, meaning and subtitle accuracy. Real-person assets require documented consent. Exact model/checkpoint licenses and output rights must be reviewed before release.

## Observability

Every wrapped model/worker call appends a JSON record to `runs.jsonl` with stage, provider, model, input hash, latency, status, error and output path. Cost estimates remain nullable until configured and measured.
