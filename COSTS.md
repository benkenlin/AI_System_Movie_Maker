# Costs and performance

## Measurement policy

`runs.jsonl` is the source of truth for call count, latency, worker wall minutes for video/music, success/failure, input hash, and any configured cost estimate. Run `python -c "from ai_content.costs import summarize_costs; import json; print(json.dumps(summarize_costs(), indent=2))"` with `PYTHONPATH=src` to aggregate it.

No live provider calls or GPU jobs have been measured in this repository snapshot. API and GPU costs are therefore **not yet measured**. The logger records a null cost when no pricing estimate is configured; do not interpret that as $0. Record free-tier quota observations, GPU type/minutes, runtime, retries, and current provider pricing after each experiment.

| Stage | Provider/model | Calls | Latency | Cost | Evidence |
|---|---|---:|---:|---:|---|
| Planning | Gemini / offline mock | Pending measurement | Pending | Pending | runs.jsonl |
| Keyframes | Cloudflare Workers AI | Pending | Pending | Pending | runs.jsonl |
| Video | Wan 2.2 worker | Pending | Pending | Pending | runs.jsonl + GPU notebook |
| Music | ACE-Step worker | Pending | Pending | Pending | runs.jsonl + GPU notebook |
| Narration | Gemini TTS | Pending | Pending | Pending | runs.jsonl |
| Assembly | FFmpeg local | Pending | Pending | Local compute | QC report |
