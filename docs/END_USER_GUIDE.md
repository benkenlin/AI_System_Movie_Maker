# End-User Guide

## 1. Start the application

Install Python 3.11/3.12, FFmpeg and ffprobe. Create a virtual environment, install `pip install -e ".[all]"`, copy `.env.example` to `.env`, fill the provider values, and run `streamlit run ui/app.py`.

## 2. Configure the providers

- Gemini: set `GEMINI_API_KEY`, text/TTS model IDs and voice.
- Cloudflare: set account ID and API token with Workers AI inference permission.
- Wan: either run the worker locally or configure a private `VIDEO_WORKER_URL` and bearer token for the remote GPU server.
- ACE-Step: start the official API server and set `ACE_STEP_API_URL`; set `ACE_STEP_API_KEY` if authentication is enabled.

Never share `.env` or commit it.

## 3. Create and approve a story

Open tab 1, enter a title and idea, select narration language and generate a storyboard. Review the title, character descriptors, shot count, prompts, narration and subtitles. Approve only when the creative direction is correct. The approved storyboard is written to `outputs/storyboard.json`.

## 4. Generate visual assets

In tab 3, generate character references and keyframes. Inspect the contact sheet carefully; keyframe approval is required before video generation. After approval, generate moving clips. Failed Wan clips automatically use Ken Burns still animation, and the failure remains in `runs.jsonl`.

## 5. Generate narration and music

Click **Generate narration and score automatically**. Gemini creates per-shot voice files. ACE-Step generates three score candidates from the storyboard's cue-aware prompt. The app automatically ranks candidates by coverage, loudness and peak headroom and writes its selection/rationale to `storyboard.json`. There is no music-choice form.

## 6. Review narration

Play each narration line in tab 5. Click **Run automatic narration checks** to check file presence, duration, pacing, silence and clipping; Gemini also screens the rendered audio against the spoken script and English subtitle for possible pronunciation/language/alignment issues. A fluent native speaker must still listen to all lines and verify pronunciation, meaning and subtitle accuracy. Enter the reviewer's name and tick the attestation only after the human review is complete. The system stores the audit notes automatically; the user does not need to type review notes.

## 7. Assemble and release

Tab 4 assembles both MP4 formats using the selected score from the storyboard. Before release, complete `model_licenses.json` and any required real-person consent records. Run release gates and final QC in tab 5. A release block is an intentional safeguard; read the exact missing requirement and complete it rather than bypassing it.

## 8. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Gemini 400/404 | Invalid API key or retired/unsupported model ID | Check key, enabled API and current model list; update `.env` |
| Cloudflare 401/403 | Wrong token/account ID or missing permission | Create a Workers AI inference token and verify account ID |
| Cloudflare 400 | Invalid model input or reference image constraints | Confirm FLUX.2 multipart fields; references must be under 512×512 |
| Wan worker 401 | Token mismatch | Match `VIDEO_WORKER_TOKEN` and `WAN_WORKER_TOKEN` |
| Wan OOM | Insufficient VRAM or wrong runtime | Lower workload, use supported distributed configuration, or rely on Ken Burns fallback |
| ACE-Step connection refused | API server is not running or URL unreachable | Start `uv run acestep-api`; verify `/health` |
| ACE-Step task failed | GPU OOM, checkpoint load or API task error | Inspect worker logs, free VRAM, verify model checkpoint and retry |
| Narration WAV invalid | Provider response or raw PCM handling | Check `runs.jsonl`, MIME type and FFmpeg decode |
| Music candidate too short | Model returned shorter audio than requested | Regenerate; selection requires runtime coverage |
| Release blocked | License, consent, native-speaker or music gate incomplete | Complete the named evidence file; do not mark unreviewed terms as reviewed |
| FFmpeg not found | FFmpeg is not on PATH | Install FFmpeg and reopen terminal/IDE |

## 9. Backup and reset

Back up `storyboard.json`, `outputs/`, `runs.jsonl`, `outputs/studio.db`, consent and license registries. Do not include API keys or private consent evidence in public backups. To start a new film, create a new storyboard and a separate output root/database rather than deleting audit records from an existing release.
