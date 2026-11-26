# Requirements Specification

## 1. Purpose and scope

The system is a small, code-driven studio that transforms a reviewed storyboard into a 60–90 second short film. Deliverables are a horizontal 16:9 MP4 and a vertical 9:16 MP4, narration in the selected language, English subtitles, original instrumental score ducked beneath narration, and an AI disclosure end card.

## 2. Functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| FR-01 | Create a storyboard draft from a story idea using Gemini or an offline fallback | Draft is saved and displayed for approval |
| FR-02 | Validate storyboard JSON against the JSON Schema and semantic rules before generation | `ai-content validate` and validation tests |
| FR-03 | Use one `storyboard.json` contract across all stages | Stage modules read the same model |
| FR-04 | Generate character reference images and shot keyframes through Cloudflare Workers AI | Per-character and per-shot images under `outputs/` |
| FR-05 | Require keyframe approval before video generation | Approval hashes are checked against current files |
| FR-06 | Generate image-to-video clips using Wan 2.2 TI2V-5B | MP4 per shot, or documented fallback |
| FR-07 | Generate three instrumental music candidates with ACE-Step 1.5 | Three WAV candidates and model-call logs |
| FR-08 | Incorporate storyboard mood, shot progression and timed music cues into the music prompt | Prompt payload includes cue map and shot context |
| FR-09 | Score candidates and automatically persist selected music and rationale | `music.selected`, `music.rationale`, selection report in storyboard |
| FR-10 | Generate per-shot narration using Gemini TTS | WAV per shot, duration measured during review/assembly |
| FR-11 | Apply pronunciation lexicon substitutions to TTS input without changing subtitle source text | TTS request uses lexicon; storyboard remains unchanged |
| FR-12 | Automatically audit narration file presence, duration, loudness, clipping and pacing | `outputs/narration_review.json` |
| FR-13 | Require native-speaker approval of pronunciation, meaning and subtitle accuracy | Named reviewer and explicit approval in review JSON |
| FR-14 | Assemble video, narration, score, ducking, subtitles and AI disclosure | FFmpeg outputs in both ratios |
| FR-15 | Perform final technical QC with ffprobe | `outputs/final_qc.json` and release gate |
| FR-16 | Enforce consent and model/output-license review before release | `check_release_gates` blocks incomplete registries |
| FR-17 | Cache stage outputs by hash and retry transient failures within a bounded budget | Sidecar metadata and `runs.jsonl` |
| FR-18 | Preserve logs for each model call and failure | JSONL records include stage, provider, model, inputs, output, latency, status |

## 3. Non-functional requirements

- **Reproducibility:** fixed seeds where supported, immutable storyboard versions and SHA-256 cache keys.
- **Reliability:** bounded retries, resumable per-shot jobs and still-image fallback for failed video generation.
- **Security:** API keys only in environment variables or secret stores; no secrets in Git.
- **Auditability:** append-only `runs.jsonl`, license registry, consent registry, review report and experiment/failure records.
- **Maintainability:** stage-specific modules and replaceable provider adapters.
- **Portability:** main app on Windows/Linux; GPU workers can run locally or remotely behind authenticated HTTP endpoints.
- **Performance:** expensive GPU jobs are isolated from the UI host; unchanged outputs are reused.
- **Accessibility/usability:** Streamlit UI provides a guided stage-based workflow and automatic music selection.
- **Output quality:** consistent frame rate, 16:9/9:16 exports, English subtitles, normalized loudness and AI disclosure.

## 4. Constraints and assumptions

- Python 3.11/3.12, FFmpeg/ffprobe, Gemini API key, Cloudflare Workers AI credentials and a GPU runtime are required for live generation.
- Wan 2.2 TI2V-5B is GPU intensive; test the exact Kaggle/Colab hardware before a full run.
- ACE-Step API and model weights are deployed separately from the application package.
- Gemini/Cloudflare model names, API availability, free quotas and terms can change; verify on deployment day.
- The system cannot autonomously certify native-language correctness. A fluent native speaker must review the actual audio.

## 5. Out of scope

- Training or fine-tuning foundation models.
- Guaranteeing factual truth of personal/family stories.
- Guaranteeing model output uniqueness or absence of all copyright similarity.
- Replacing consent, legal review, cultural review or native-speaker judgement.
- Hosting GPU model weights inside the GitHub repository.

## 6. Challenge traceability

The requirements directly implement the challenge's five production stages (keyframes, moving shots, music, narration and assembly), shared storyboard contract, 60–90 second runtime, two aspect ratios, English subtitles, original score, AI end card, reproducibility, logging, documentation, audience testing and ethical release gates.
