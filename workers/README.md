# GPU workers: Wan 2.2 and ACE-Step 1.5

The Python application can run on the user's Windows/Linux machine. The large video and music models run in a CUDA notebook or GPU host. The worker scripts in this repository implement the JSON contract called by `ProductionPipeline`; they are not placeholders.

## 1. Wan 2.2 TI2V-5B

1. In the GPU environment, clone the official repository and install its pinned requirements:

```bash
git clone https://github.com/Wan-Video/Wan2.2.git
cd Wan2.2
# Follow the repository's requirements; torch >= 2.4 is required.
pip install -r requirements.txt
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir ../Wan2.2-TI2V-5B
```

2. Set `WAN_REPO_DIR` and `WAN_CHECKPOINT_DIR` to those exact directories. Set `WAN_NPROC_PER_NODE=1` for one GPU. Set it to 2 only when two visible CUDA devices are actually available and the installed Wan environment supports distributed FSDP/Ulysses.
3. The worker calls official `generate.py` with `--task ti2v-5B`, the approved keyframe, motion prompt, seed, frame count, checkpoint path and output MP4. It rounds frame count to Wan's 4n+1 constraint.
4. Official model card indicates 720p output and a 24 GB GPU (e.g. RTX 4090) for single-GPU inference. Two T4 GPUs may require distributed configuration and can still run out of memory. Always test one short shot first; orchestrator falls back to Ken Burns if the worker fails.

Run manually:

```bash
python workers/wan_worker.py --input path/to/shot.json --output outputs/clips/s01.mp4
```

## 2. ACE-Step 1.5

Install ACE-Step 1.5 in the GPU environment following its official README, then start its API server:

```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
# Use uv sync as documented upstream
uv sync
uv run acestep-api
```

The API listens on `http://127.0.0.1:8001` by default. Configure `ACE_STEP_API_URL` and optionally `ACE_STEP_API_KEY`. The worker submits instrumental text-to-music tasks to `/release_task`, polls `/query_result`, then downloads `/v1/audio`. It uses the storyboard's full score prompt, duration, candidate seed and cue map. Three distinct candidates are generated.

```bash
python workers/ace_step_worker.py --input path/to/music.json --output outputs/music/candidate_1.wav
```

If ACE-Step is hosted in a separate notebook, expose the API only through a private tunnel or authenticated network. Do not expose an unauthenticated GPU API to the public internet.

## 3. Worker payloads and outputs

The orchestrator passes an input JSON path and destination path through `{input_json}` and `{output}`. Wan writes MP4; ACE-Step writes WAV. Both workers fail loudly if required model/runtime settings are missing or the output is absent. Model weights are not included in this Git repository.
