# AI Content System — Complete System Documentation Report

**Project:** Storyboard-driven AI Filmmaking Pipeline  
**Reference film:** *The Last Coffee Ceremony*  
**Version:** 1.0  
**Prepared:** 26 November 2026  
**Status:** Engineering documentation for deployment and challenge submission

> This report describes the implemented codebase and the deployment requirements. It does not claim that live Gemini, Cloudflare, Wan or ACE-Step calls have been completed. Those integrations require the operator's credentials and GPU services. Replace any deployment measurements with actual values from `runs.jsonl` and the GPU logs.

## 1. System Overview

### 1.1 Purpose

The AI Content System is a modular filmmaking pipeline that transforms a written story concept into a 60–90 second short film. It generates a validated storyboard, character reference images, shot keyframes, moving shots, original instrumental music and narration. It then assembles the media with English subtitles, narration-first audio mixing, loudness normalization and an AI disclosure end card. The final outputs are horizontal 16:9 and vertical 9:16 MP4 files.

### 1.2 Objectives

- Reduce manual production work through coordinated generative models and deterministic orchestration.
- Keep `storyboard.json` as the single source of creative intent and the contract shared by all stages.
- Re-run only outputs whose inputs changed by using content hashes and cache sidecars.
- Isolate GPU-heavy video and music generation from the desktop application.
- Preserve reproducibility, auditability, consent, model-license review and human-language quality assurance.

### 1.3 Scope

The system covers planning, validation, image generation, image-to-video generation, score generation, TTS narration, FFmpeg assembly, technical QC, logging, release gates, UI and documentation. Foundation-model training, voice cloning, automatic consent collection, and autonomous certification of native-language pronunciation are outside scope.

## 2. Requirements Specification

### 2.1 Functional requirements

| ID | Requirement | Implementation / evidence |
|---|---|---|
| FR-01 | Draft a storyboard from a natural-language idea | Gemini planner and offline template planner |
| FR-02 | Validate the storyboard before production | JSON Schema, Pydantic and semantic validation |
| FR-03 | Use one shared storyboard contract | `storyboard.json` and `schema/storyboard.schema.json` |
| FR-04 | Generate character references and shot keyframes | Cloudflare Workers AI FLUX.2 Klein provider |
| FR-05 | Approve keyframes before GPU video generation | Keyframe approval file stores SHA-256 hashes |
| FR-06 | Generate moving shots from keyframes | Wan 2.2 TI2V-5B worker; Ken Burns fallback |
| FR-07 | Generate original instrumental music candidates | ACE-Step 1.5 API worker; three seeded candidates |
| FR-08 | Use timed story/music cues | Cue-aware prompt includes shot arc and cue map; default cues are persisted when absent |
| FR-09 | Select a music candidate automatically | Gemini audio-fit screening plus duration, loudness, peak-headroom and file-integrity ranking; rationale saved in storyboard |
| FR-10 | Generate narration per shot | Gemini TTS provider with voice, language, style and pronunciation lexicon |
| FR-11 | Check narration assets automatically | File existence, duration, loudness, clipping and estimated speaking-rate audit |
| FR-12 | Retain native-speaker review | Explicit human attestation required before release |
| FR-13 | Assemble film with narration-first mix | FFmpeg normalization, sidechain ducking, subtitles and loudness normalization |
| FR-14 | Export both aspect ratios | 16:9 and 9:16 MP4 files |
| FR-15 | Enforce consent and model/output rights | Consent and model-license release gates |
| FR-16 | Log model calls and failures | `runs.jsonl`, per-output metadata and cost summaries |
| FR-17 | Support incremental regeneration | SHA-256 input hashes, sidecars and SQLite artifact/job store |
| FR-18 | Provide a guided user interface and end-to-end command | Streamlit UI and `ai-content film` / `make film` |

### 2.2 Non-functional requirements

- **Reliability:** bounded retries, resumable shot-level work and documented fallbacks.
- **Reproducibility:** stable shot IDs, model identifiers, seeds and content hashes.
- **Security:** secrets loaded from environment variables or deployment secret stores; `.env` excluded from Git.
- **Auditability:** model-call log, experiment log, failure journal, cost report, consent registry and model-license registry.
- **Maintainability:** clear modules and provider adapters that can be replaced when APIs change.
- **Portability:** desktop application can use remote GPU workers through authenticated HTTP services.
- **Quality:** consistent frame rate and aspect ratios, subtitle file, narration-first mix, AI disclosure and ffprobe checks.
- **Ethics:** consent for real people, exact model/checkpoint terms reviewed, no unapproved real voice/face use.

### 2.3 Constraints

The production host requires Python 3.11/3.12 and FFmpeg/ffprobe. Live generation requires a Gemini API key, Cloudflare account/token, Wan 2.2 GPU runtime and ACE-Step 1.5 API service. Model availability, API quotas, prices, free tiers and licensing terms may change. GPU memory requirements must be verified on the actual Kaggle/Colab hardware. A fluent native speaker is required for language review.

## 3. Architectural Design

### 3.1 Architecture pattern

The system uses a deterministic stage-oriented pipeline. Gemini helps draft and repair creative content; it does not control runtime scheduling. The Python orchestrator validates stage inputs, computes artifact hashes, invokes model adapters, applies bounded retries and records outcomes.

### 3.2 Logical architecture

```text
Human director / Streamlit UI
             |
             v
     Gemini story planner
             |
             v
       storyboard.json
             |
             v
   Schema + semantic validator
             |
             v
 Deterministic orchestrator + cache
      |       |       |       |
      v       v       v       v
   FLUX     Wan    ACE-Step  Gemini TTS
 keyframes video     music   narration
      \       |       |       /
       \      |       |      /
        +-----+-------+-----+
                  |
                  v
            FFmpeg assembly
                  |
                  v
      Horizontal + vertical MP4
                  |
                  v
       Release gates and final QC
```

### 3.3 Main components

1. **User interface:** Streamlit application provides storyboard creation, approval, asset generation, music automation, narration QA and release QC.
2. **Planning agent:** Gemini creates JSON storyboard drafts; a local validator remains authoritative.
3. **Storyboard contract:** stores story, language, style, characters, narration, music prompt/cues, shots, subtitles and AI disclosure.
4. **Validation layer:** schema and semantic checks prevent invalid storyboards from entering expensive stages.
5. **Orchestrator and cache:** SQLite job/artifact tracking plus per-artifact SHA-256 sidecars support resumable work.
6. **Visual generation:** Cloudflare Workers AI FLUX.2 Klein produces reference images and keyframes.
7. **Video generation:** Wan 2.2 TI2V-5B animates approved keyframes. The worker can run locally or as an authenticated remote service.
8. **Music generation:** ACE-Step 1.5 produces three instrumental candidates from a cue-aware score prompt.
9. **Music selection:** automatic technical ranking selects the best candidate and persists rationale and a separate ranking report.
10. **Narration:** Gemini TTS creates individual shot narration files; pronunciation lexicon substitutions affect spoken input only.
11. **Narration review:** automatic technical checks are combined with required native-speaker attestation.
12. **Assembly and QC:** FFmpeg creates both exports; ffprobe validates duration, dimensions and audio presence.
13. **Ethics and release:** checks consent, licenses/output rights, narration review, music selection and AI disclosure.

### 3.4 Deployment architecture

The desktop host runs Python, Streamlit, the local database, Gemini and Cloudflare adapters, and FFmpeg. Wan and ACE-Step run on GPU infrastructure. The Wan server accepts a keyframe and JSON payload over an authenticated endpoint. ACE-Step exposes its official asynchronous API; the local worker submits tasks, polls results and downloads generated audio. GPU endpoints should be private or protected by a secure tunnel and bearer token.

### 3.5 Failure handling

- Invalid storyboard: stop before generation and report schema/semantic errors.
- Gemini/Cloudflare API error: log and retry within the configured retry budget.
- Quota exhaustion: stop cleanly and reuse cached outputs on the next run.
- Wan worker failure or OOM: record failure and generate a Ken Burns fallback from the approved still.
- ACE-Step failure: stop music generation and report worker/API diagnostics; do not silently substitute stock music.
- TTS failure: retry only missing/changed shot narration.
- Assembly/QC failure: preserve intermediate artifacts and block release.
- Missing consent/license/native-speaker evidence: block release.

## 4. Technical Design

### 4.1 Technology stack

| Layer | Technology |
|---|---|
| Language/runtime | Python 3.11+ |
| Data contract | JSON Schema 2020-12 and Pydantic 2 |
| UI | Streamlit |
| Storyboard planning | Gemini API |
| Narration | Gemini 3.8 Flash TTS (configured model ID) |
| Keyframes | Cloudflare Workers AI FLUX.2 Klein 9B |
| Video | Wan 2.2 TI2V-5B |
| Music | ACE-Step 1.5 |
| Media assembly | FFmpeg and ffprobe |
| Persistence | SQLite and JSON/JSONL files |
| Testing | pytest |

### 4.2 Storyboard contract

The top-level storyboard contains schema and storyboard versions, title, logline, narration and subtitle languages, target runtime, shot count, aspect ratios, style, characters, narration voice, music and cues, shots, and AI disclosure. Each shot includes a stable `sNN` ID, duration, image and motion prompts, camera move, character references, vertical crop focus, optional seed, narration text/language/lexicon, English subtitle and transition. Music cues are attached to shot IDs and use `fade_in`, `swell`, `drop` or `fade_out` actions.

### 4.3 Validation

Validation is performed before production. Structural validation checks types, enumerations and required fields. Semantic validation checks sequential unique shot IDs, character references, narration language, subtitle presence, speech-length estimates, total runtime, music duration and cue references. The `MusicCue` relationship check uses the cue model's `at_shot` property.

### 4.4 Provider integrations

**Gemini planning:** sends a storyboard instruction and requests JSON output. The response is parsed and validated locally.  
**Gemini TTS:** requests audio for each shot with the configured voice, BCP-47 language, style and lexicon-expanded spoken text. The response WAV/PCM is written to a per-shot file.  
**Cloudflare FLUX:** uses the Workers AI multipart endpoint; reference images use the `input_image_0`…`input_image_3` fields.  
**Wan 2.2:** the local worker calls the official `generate.py` TI2V-5B task with the approved keyframe, motion prompt, seed, frame count and output path. Frame count is rounded to the model's 4n+1 requirement.  
**ACE-Step:** the worker submits an instrumental `text2music` job to `/release_task`, polls `/query_result`, and downloads the WAV from `/v1/audio`.

### 4.5 Music prompt and selection

The score prompt includes the original music brief, title/logline, narration context by shot, instrumental-only requirement, target duration and timed cues. If the storyboard omits cues, the system creates a default fade-in, mid-film swell, late drop and final fade-out map. Three candidates are generated using distinct seeds. Gemini multimodal screening evaluates audible narrative/cue fit, ending quality and possible vocals; technical scoring checks duration coverage, average loudness, peak headroom and file integrity. The combined score selects the path saved to `storyboard.json`; detailed ranking and audio-screen results are saved separately in `outputs/music_selection.json` and `outputs/music_semantic_audit.json`. If Gemini screening is unavailable, technical-only selection is recorded explicitly. This is not an automatic artistic or cultural quality guarantee.

### 4.6 Narration QA

Per-shot audio is checked for presence, decodable duration, silence/low level, clipping and estimated words per second. The report is saved to `outputs/narration_review.json`. Gemini multimodal screening also compares the rendered audio with the expected script and English subtitle and flags possible pronunciation/language/alignment issues. This is a machine-assisted signal, not proof of correct Amharic/Afaan Oromo pronunciation or idiom. A fluent native speaker must listen to every line and explicitly attest to pronunciation, meaning and English subtitle accuracy.

### 4.7 Assembly

FFmpeg normalizes clip dimensions/frame rate, pads video to match measured narration duration, concatenates narration, creates SRT timings, joins shots with transitions, mixes music under speech using sidechain compression, applies loudness normalization, burns subtitles, adds an AI end card and exports both aspect ratios. Final QC checks audio stream, aspect ratio, duration, subtitles and disclosure source.

### 4.8 Caching and reproducibility

The production pipeline computes SHA-256 hashes from stage/provider/model and the inputs that affect an artifact. A matching non-empty output and metadata sidecar is reused. Keyframe hashes are also stored in the approval file; a changed keyframe invalidates the approval and blocks video generation. The SQLite orchestrator tracks project, run, job dependencies and artifacts. Model calls are logged in `runs.jsonl`.

### 4.9 Security and configuration

`.env.example` lists configuration variables. `python-dotenv` loads `.env`; `.gitignore` prevents secrets from being committed. The UI shows whether credentials are configured, not their values. For hosted GPU endpoints, use bearer-token protection and HTTPS/private networking. Never place credentials in storyboard JSON or output reports.

## 5. Development and Design

### 5.1 Repository organization

- `src/ai_content/models.py`: Pydantic storyboard models.
- `validation.py`: schema and semantic validation.
- `planning.py`: draft lifecycle and planner interfaces.
- `providers.py`: Gemini, Cloudflare, command and remote HTTP providers.
- `orchestrator.py`, `db.py`, `hashing.py`: deterministic job state and cache identifiers.
- `visual.py`, `production.py`: image/video/audio stage operations.
- `music.py`: cue-aware prompt and automatic selection.
- `review.py`: technical narration audit and human approval record.
- `assembly.py`: FFmpeg assembly and QC.
- `ethics.py`: consent, license and release gates.
- `observability.py`, `costs.py`: logging and cost aggregation.
- `ui/app.py`: Streamlit UI.
- `workers/`: Wan and ACE-Step worker entry points.
- `tests/`: validation, providers, caching, release gates and FFmpeg smoke tests.

### 5.2 Development workflow

1. Build and validate the schema/model contract.
2. Implement provider interfaces and mockable adapters.
3. Add artifact hashes, cache sidecars, retries and JSONL logging.
4. Add keyframe approval and video fallback.
5. Add cue-aware music generation and automatic candidate ranking.
6. Add per-shot TTS and technical narration audit.
7. Add FFmpeg assembly and dual-aspect exports.
8. Add consent/license/native-speaker gates and documentation.
9. Run tests, then perform live provider smoke tests on configured infrastructure.

### 5.3 UI design changes

The revised interface removes manual music candidate selection, user-written music rationale and free-form narration review notes. Music candidates are screened by Gemini for audible narrative/cue fit and possible vocals, then combined with technical scoring and selected automatically. The system writes the music rationale and ranking report. Narration technical notes are generated automatically. The UI retains the native-speaker identity and explicit approval control because a human review is a challenge requirement and cannot be truthfully automated.

### 5.4 Test strategy and current evidence

Unit tests validate storyboard rules, cue relationships, provider request formation, caching, music selection, ethics gates and narration audit behavior. The FFmpeg smoke test creates synthetic media and verifies both export aspect ratios and technical QC. At packaging time, the suite contains **45 passing tests** in the local environment. This does not establish live API success, model quality, GPU fit, language accuracy or audience acceptance.

### 5.5 Known limitations

- Live Gemini, Cloudflare, Wan and ACE-Step execution has not been performed in the packaging environment.
- Wan 2.2 TI2V-5B is resource intensive; GPU memory and distributed configuration must be tested on the actual host.
- ACE-Step server must be separately installed and started.
- The music selector evaluates technical suitability, not emotional/cultural preference.
- Automated narration QA cannot replace native-speaker listening.
- Audience tests and measured generation costs must be completed and recorded by the project owner.

## 6. End-User Guide

### 6.1 Install and launch

1. Install Python 3.11/3.12, FFmpeg and ffprobe.
2. Create a virtual environment and install `pip install -e ".[all]"`.
3. Copy `.env.example` to `.env` and set Gemini, Cloudflare, Wan and ACE-Step variables.
4. Run `ai-content validate storyboard.json`.
5. Launch `streamlit run ui/app.py`.

### 6.2 Generate the film

1. Enter the film title and story idea; select the narration language.
2. Generate a Gemini storyboard draft and review it.
3. Approve the storyboard to create `outputs/storyboard.json`.
4. Generate character references and keyframes; inspect and approve the contact sheet.
5. Generate moving clips. Failed clips fall back to Ken Burns animation.
6. Generate narration and three music candidates. The system selects the music candidate automatically.
7. Play every narration line, run automated technical checks, and obtain native-speaker approval.
8. Complete consent and model-license registries.
9. Assemble horizontal and vertical MP4 files and run final release QC.

### 6.3 One-command execution

After configuring providers and registries, run `make film` or:

```bash
ai-content film storyboard.json --output outputs --licenses model_licenses.json --consent consent_registry.json
```

The command pauses for keyframe inspection and native-speaker attestation. It does not bypass human or release gates.

### 6.4 Troubleshooting

- **Gemini 400/404:** verify the API key, enabled API and current model ID.
- **Cloudflare 401/403:** verify account ID and Workers AI inference permissions.
- **Wan OOM:** reduce the workload, validate multi-GPU settings or use the still-image fallback.
- **ACE-Step unavailable:** start the official API server and verify the configured endpoint.
- **Narration audit fails:** inspect the specific shot's audio, rerun TTS if necessary, then repeat native review.
- **Music too short:** regenerate candidates; a candidate must cover the complete film.
- **Release blocked:** complete the named consent, model license/output rights, narration or music requirement.
- **FFmpeg not found:** install FFmpeg and ensure `ffmpeg` and `ffprobe` are on `PATH`.

## 7. Deployment and Release Checklist

- [ ] Python environment installed and dependencies pinned.
- [ ] `.env` configured locally or secrets installed in deployment manager.
- [ ] Gemini planning and TTS smoke tests pass.
- [ ] Cloudflare FLUX smoke test passes.
- [ ] Wan worker health check and one-shot generation pass.
- [ ] ACE-Step health check and one candidate generation pass.
- [ ] Storyboard validates and approved keyframe hashes match.
- [ ] All shots have video or fallback, narration and music.
- [ ] Music candidate selected and rationale persisted.
- [ ] Automated narration checks pass.
- [ ] Native speaker reviewed every line and approved.
- [ ] Every real person has scoped consent evidence.
- [ ] Exact model/checkpoint terms and generated-output rights reviewed.
- [ ] Both MP4 exports pass ffprobe/QC and include subtitles/audio/AI end card.
- [ ] `runs.jsonl`, `COSTS.md`, `FAILURES.md`, `EXPERIMENTS.md` and `DESIGN.md` contain actual run evidence.
- [ ] Report contains real audience test feedback and measured costs.
