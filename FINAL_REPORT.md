# AI Content Generation — System Development and Design Report

**Project:** AI Content System — *The Last Coffee Ceremony*  
**Submission:** B2W0 — AI-Content Generation: Codebase and Report  
**Author:** [Insert author]  
**Date:** [Insert submission date]

> **Evidence status:** This is a report draft based on the submitted system design, challenge document and inspected codebase. Replace bracketed items with your actual live run IDs, GPU measurements, user-test evidence and film links. Do not claim an API or GPU run that has not actually completed.

## 1. Executive summary

The project implements a storyboard-driven AI filmmaking pipeline. It is designed to transform a written concept into a 60–90 second narrated short with AI-generated keyframes, moving shots, original instrumental music, narration, English subtitles, and horizontal and vertical exports. The system uses a validated `storyboard.json` contract and a deterministic Python orchestrator so that production can resume and only changed assets are regenerated.

## 2. Requirements

The target deliverables are 60–90 seconds, both 16:9 and 9:16 MP4 exports, narration in [language], English subtitles, an original score mixed below narration, and an AI disclosure end card. Engineering requirements include schema validation, per-stage scripts, caching, bounded retries, secrets outside Git, a JSONL call log, technical documentation, experiments, failure records, cost measurements and audience tests.

## 3. System architecture

The architecture consists of a Streamlit interface, Gemini planning adapter, shared storyboard contract, validator, deterministic orchestrator/cache, Cloudflare FLUX keyframe generation, Wan 2.2 video worker, ACE-Step music worker, Gemini TTS narration, FFmpeg assembly, final QC and ethics/release gates. The main application can run on a desktop host while the GPU workers run remotely behind authenticated endpoints.

## 4. Technical implementation

The repository is organized into `src/ai_content/` modules for planning, validation, provider adapters, orchestration, visual production, audio production, music selection, review, assembly, logging and ethics. `workers/` contains Wan 2.2 and ACE-Step worker adapters. The Streamlit interface provides a guided workflow. Generated outputs are stored under `outputs/`; hashes and sidecars support reuse; `runs.jsonl` provides call-level audit evidence.

## 5. Development and design decisions

The storyboard is the single contract between stages. The runtime orchestrator is deterministic rather than LLM-directed. Keyframes are approved before expensive video generation. Wan failures use Ken Burns fallback. Music candidates are generated from a cue-aware prompt and automatically ranked using duration coverage, loudness and peak headroom. Narration is generated per shot to make corrections local. The final mix ducks music beneath speech and exports two aspect ratios.

## 6. Quality, ethics and release

Automated checks validate storyboard fields, output media, narration file integrity, duration, loudness, clipping and pacing. A native speaker must listen to all narration and attest to pronunciation, meaning and subtitle accuracy. Real-person likenesses/voices require documented consent. Every exact model/checkpoint and generated-output terms must be reviewed. The film includes an AI disclosure end card.

## 7. Implementation and validation evidence

- Automated tests: [insert command, date and actual pass/fail count].
- FFmpeg smoke test: [insert actual result and output dimensions].
- Gemini live planning/TTS: [insert run IDs and measured latency].
- Cloudflare keyframe: [insert run IDs, model ID and latency].
- Wan video: [insert GPU model, VRAM, resolution, frames, generation time and fallback count].
- ACE-Step music: [insert model/checkpoint, GPU, candidate count and generation time].
- Measured costs: [populate from `runs.jsonl` and GPU logs].

## 8. Audience and design testing

**Intended audience:** [identify the audience and viewing context].

**Radio-cut test (at least three people):** [summarize each response without publishing private details].

**Storyboard changes made because of feedback:** [list specific shot/narration/subtitle edits].

**Near-final test (at least three people):** [summarize feedback].

**Changes made:** [list specific changes].

## 9. Experiments and failures

Summarize at least ten experiments from `EXPERIMENTS.md` with hypothesis, change and result. Describe real failures from `FAILURES.md`, including API quotas, GPU memory, model drift, Amharic pronunciation or FFmpeg issues. State what was attempted and what evidence supports the fix or fallback.

## 10. Suggested practices tested honestly

- **Practice that helped:** [describe a practice and the measured evidence].
- **Practice that did not help:** [describe what was tried, why it did not help and what was learned].

## 11. Hardest problem and resolution

[Describe the hardest actual blocker, its root cause, diagnostic steps, fix/fallback and evidence in logs.] 

## 12. Curiosity beyond the baseline

[Describe any extra language, benchmark, CLI/MCP tool, character-consistency experiment or family-facing UI feature. Include evidence and what was learned. If none, state that honestly.]

## 13. Limitations and future work

The pipeline depends on third-party API availability, GPU capacity and model-specific terms. Automated audio metrics cannot judge native-language pronunciation or cultural nuance. Future work includes richer automated audio transcription comparison, more robust remote job queuing, stronger visual consistency evaluation, more language-specific TTS evaluation and expanded audience testing.

## 14. Submission links

- Public GitHub repository: [insert URL]
- Vertical MP4 (9:16): [insert URL]
- Horizontal MP4 (16:9): [insert URL]
- Walkthrough video (maximum five minutes): [insert URL]
- Public post or screenshot: [insert URL]
