# Technical Design Specification

## 1. Runtime and dependencies

- Python 3.11/3.12; Pydantic 2; python-dotenv.
- Streamlit for the browser UI.
- FFmpeg/ffprobe for media transforms and QC.
- `pytest` for tests.
- Optional worker service dependencies: FastAPI, Uvicorn and python-multipart.
- External services: Gemini API, Cloudflare Workers AI, ACE-Step 1.5 API, Wan 2.2 inference runtime.

## 2. Repository map

| Path | Responsibility |
|---|---|
| `storyboard.json` | Current creative contract |
| `schema/storyboard.schema.json` | JSON Schema contract |
| `src/ai_content/models.py` | Strict Pydantic models and cross-field rules |
| `validation.py` | JSON loading, schema validation and semantic checks |
| `planning.py` | Draft lifecycle and planner abstraction |
| `providers.py` | Gemini, Cloudflare, local command and remote HTTP adapters |
| `orchestrator.py`, `db.py` | Job state, DAG orchestration, database and retries |
| `hashing.py` | Stable input fingerprints |
| `visual.py`, `production.py` | Character references, keyframes, video, music and narration |
| `music.py` | Cue-aware music brief, technical scoring and selection |
| `review.py` | Automated narration technical audit and native-speaker attestation |
| `assembly.py` | FFmpeg assembly and final QC |
| `ethics.py` | Consent, model-license and release gates |
| `observability.py`, `costs.py` | JSONL call logging and cost aggregation |
| `ui/app.py` | Streamlit application |
| `workers/wan_worker.py` | Wan CLI adapter |
| `workers/wan_server.py` | Authenticated remote Wan HTTP endpoint |
| `workers/ace_step_worker.py` | ACE-Step API client/worker |
| `tests/` | Unit and integration-smoke tests |

## 3. Storyboard contract

Top-level fields include `schema_version`, `storyboard_version`, `title`, `logline`, `language`, `subtitle_language`, `target_runtime_s`, `shot_count`, `aspect_ratios`, `style`, `characters`, `narration_voice`, `music`, `shots` and `ai_disclosure`.

Each shot has a stable ID (`s01`...), duration, image prompt, motion prompt, camera movement, character IDs, vertical crop focus, optional seed, narration text/language/lexicon, English subtitle and transition. Music contains an instrumental prompt, target duration, candidates, selected path, rationale and shot-linked cues (`fade_in`, `swell`, `drop`, `fade_out`).

## 4. Cache and invalidation

A stage cache key is SHA-256 over the stage/provider/model and canonicalized inputs. A matching output plus sidecar is reused. Changing a shot narration should invalidate only that shot's narration, subtitle timing and final assembly; it should not regenerate its keyframe or clip. Changing a motion prompt invalidates that shot's video, not the music or other shots. Changing the global style invalidates character references/keyframes and dependent video.

## 5. Provider contracts

### Gemini planning

`generateContent` with JSON response mode. Model is configured using `GEMINI_TEXT_MODEL`. The planner output is always validated locally; JSON mode is not treated as schema enforcement.

### Gemini TTS

One `generateContent` audio request per shot using `responseModalities=[AUDIO]`, `speechConfig.voiceConfig.voice`, language code and `speechMetadata.style`. Pronunciation lexicon replacements apply to spoken input only; storyboard/subtitle text remains canonical. The adapter writes the returned WAV or wraps raw PCM when needed.

### Cloudflare Workers AI

FLUX.2 Klein 9B uses multipart form data. Reference images use `input_image_0` through `input_image_3` and must satisfy the model's input constraints. `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are required.

### Wan 2.2

The local worker calls the official Wan `generate.py` CLI with `--task ti2v-5B`, approved image, prompt, seed, checkpoint and `--save_file`. Frame count is rounded to 4n+1. The remote service accepts multipart `payload` and `image`, requires a bearer token when configured, and streams MP4 back to the application.

### ACE-Step 1.5

The worker uses `/release_task`, `/query_result` and `/v1/audio`. It requests `text2music`, no lyrics, WAV output, duration, seed and the cue-aware score prompt. Each candidate has a distinct seed. The API server must be started separately in the GPU runtime.

## 6. Music candidate selection

The system generates three candidates from the same storyboard-derived brief, including narrative arc and cue timings. Gemini multimodal audio screening evaluates narrative fit, cue fit, clean ending and possible vocals. Technical score uses:

- Full runtime coverage (hard requirement).
- Mean loudness near a conservative mix target.
- Peak headroom to avoid clipping.
- File size/integrity checks.

The highest scoring candidate is saved to `music.selected`, with a generated rationale and a machine-readable ranking. This automatic selector does not detect cultural appropriateness or guarantee the musical climax is artistically ideal; those are optional human review considerations, not a UI form requirement.

## 7. Narration QA and human review

Automated checks verify file existence, decodable duration, low/silent level, clipping and estimated speaking rate. A Gemini multimodal audit also compares rendered audio with the expected transcript and English subtitle, and flags possible pronunciation, language or subtitle-alignment issues. Model confidence is not a guarantee; the report explicitly states it does not replace native-speaker review. A native speaker listens to every line and signs off in the UI. Release requires this attestation.

## 8. Assembly and quality controls

The assembler normalizes frame rate and output geometry, pads the visual duration when narration runs long, creates English SRT timings from measured audio, concatenates narration, ducks the music using sidechain compression, normalizes loudness, burns subtitles, creates an AI end card and exports both ratios. `ffprobe` checks duration, dimensions, audio stream and subtitle/disclosure source files.

## 9. Observability

Every model call records stage, provider, model, parameters/inputs, attempt, latency, output path, status and error. `COSTS.md` should be populated from actual run logs and measured GPU minutes; do not substitute list-price estimates for measured costs without labeling them.

## 10. Configuration and secret handling

`.env.example` documents variable names. `.env` is loaded locally but ignored by Git. In hosted deployments, use the platform's secret manager. The app displays configured/not configured status only, never secret values.
