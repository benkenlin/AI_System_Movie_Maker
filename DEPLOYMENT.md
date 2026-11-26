# Deployment and API Configuration Guide

This guide configures the application host and the two GPU workers. The repository intentionally contains placeholders, not real API keys or tokens. Credentials belong to the operator's accounts and must never be committed.

## 1. Application host — Windows

Open PowerShell in the repository directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[all]"
Copy-Item .env.example .env
```

Open `.env` in a local editor and fill the following values:

```dotenv
GEMINI_API_KEY=YOUR_GOOGLE_AI_STUDIO_KEY
CLOUDFLARE_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN=YOUR_WORKERS_AI_TOKEN
```

### Gemini API key

1. Open Google AI Studio: https://aistudio.google.com/app/apikey
2. Create or select a project and create an API key.
3. Copy it into `GEMINI_API_KEY` in the local `.env` file.
4. Keep `GEMINI_TEXT_MODEL=gemini-3.8-flash` and `GEMINI_TTS_MODEL=gemini-3.8-flash-tts` unless your account's model list or provider documentation requires a different supported model ID.
5. Do not paste the key into this chat, GitHub, `storyboard.json` or a screenshot.

### Cloudflare Workers AI token

1. Open the Cloudflare dashboard and copy the account ID.
2. Create an API token with the minimum Workers AI inference permissions required for the account.
3. Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in `.env`.
4. Keep `CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-2-klein-9b` unless the model has been retired or is unavailable to the account.
5. Never put the token in a source file or commit.

## 2. Wan 2.2 GPU worker

The recommended topology is the main application on Windows and Wan on a separate GPU host. In Kaggle/Colab or a CUDA server:

```bash
git clone https://github.com/Wan-Video/Wan2.2.git
cd Wan2.2
# Follow upstream's torch/CUDA requirements and install the official requirements.
pip install -r requirements.txt
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir ../Wan2.2-TI2V-5B
```

In the GPU environment, set:

```dotenv
WAN_REPO_DIR=/path/to/Wan2.2
WAN_CHECKPOINT_DIR=/path/to/Wan2.2-TI2V-5B
WAN_WORKER_TOKEN=GENERATE_A_LONG_RANDOM_SECRET
WAN_SIZE=1280*704
WAN_NPROC_PER_NODE=1
```

From the AI Content System project root, install the worker extras and start the authenticated service:

```bash
pip install -e ".[workers]"
uvicorn workers.wan_server:app --host 0.0.0.0 --port 8787
```

Expose this service only through a private HTTPS tunnel or authenticated network. On the Windows application host, set:

```dotenv
VIDEO_WORKER_URL=https://YOUR_PRIVATE_WORKER_HOST
VIDEO_WORKER_TOKEN=THE_SAME_SECRET_AS_WAN_WORKER_TOKEN
```

The two token values must match. `VIDEO_WORKER_URL` is the base URL; the adapter calls `/generate`. `/health` is available for a basic health check. Do not expose the worker publicly without a secure access layer.

Wan 2.2 TI2V-5B is GPU intensive. Test one shot first. The official model card describes 720p/24fps capability and a 24 GB single-GPU baseline. A two-GPU T4 notebook may need distributed configuration and may still be constrained by memory or session time. The pipeline falls back to Ken Burns if a shot fails.

## 3. ACE-Step 1.5 GPU worker

On a GPU host:

```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
# Follow the official install guide; Python 3.11–3.12 is recommended.
uv sync
uv run acestep-api
```

The default API port is `8001`. If the application runs on another machine, expose the API through a private authenticated tunnel. Set on the application host:

```dotenv
ACE_STEP_API_URL=https://YOUR_PRIVATE_ACE_STEP_HOST
ACE_STEP_API_KEY=YOUR_OPTIONAL_ACE_STEP_SERVER_KEY
```

The worker sends the cue-aware instrumental prompt to `/release_task`, polls `/query_result`, and downloads the WAV from `/v1/audio`. It generates three distinct candidates.

## 4. Start and validate the application

```powershell
ai-content validate storyboard.json
pytest -q
streamlit run ui/app.py
```

In the Streamlit UI, create/review the storyboard, approve keyframes, generate narration and music, run the automatic audio/translation screen, obtain native-speaker approval, assemble both formats and run release QC.

For the interactive end-to-end CLI:

```powershell
ai-content film storyboard.json --output outputs --licenses model_licenses.json --consent consent_registry.json
```

The command pauses for keyframe inspection and native-speaker attestation. It does not bypass these gates.

## 5. License and consent registries

`model_licenses.json` is supplied as an unapproved starter and is ignored by Git. Review each exact model/checkpoint's terms and output rights. Only after review, update the per-model `reviewed` and `commercial_use_reviewed` flags, record the reviewer/date, and set the top-level release/output review flags. See `docs/LICENSE_REVIEW.md`.

`consent_registry.json` starts empty. Add a record only for a real person whose face, likeness or voice is used. Store the actual evidence privately, not in the public repository. Fictional characters do not require a person-consent record.
