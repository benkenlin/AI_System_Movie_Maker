#!/usr/bin/env python3
"""Wan 2.2 TI2V-5B worker using the official Wan-Video/Wan2.2 inference CLI.

Requires WAN_REPO_DIR and WAN_CHECKPOINT_DIR. The official CLI is run per shot so the
orchestrator can checkpoint, retry, and fall back independently.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, shutil
from pathlib import Path

def run(payload:dict, output:Path):
    repo=Path(os.getenv('WAN_REPO_DIR','')).expanduser()
    ckpt=Path(os.getenv('WAN_CHECKPOINT_DIR','')).expanduser()
    if not repo or not (repo/'generate.py').exists(): raise RuntimeError('Set WAN_REPO_DIR to a clone of https://github.com/Wan-Video/Wan2.2 containing generate.py')
    if not ckpt.exists(): raise RuntimeError('Set WAN_CHECKPOINT_DIR to the downloaded Wan2.2-TI2V-5B checkpoint directory')
    image=Path(payload['image']).resolve()
    if not image.exists(): raise FileNotFoundError(image)
    output=output.resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    seconds=float(payload.get('duration_s',5)); fps=24
    # Wan's frame count must be 4n+1; round up to the next valid count.
    frames=max(5,round(seconds*fps)); frames=((frames-1+3)//4)*4+1
    size=os.getenv('WAN_SIZE','1280*704')
    cmd=[sys.executable,str(repo/'generate.py'),'--task','ti2v-5B','--size',size,
         '--ckpt_dir',str(ckpt),'--offload_model','True','--convert_model_dtype','--t5_cpu',
         '--image',str(image),'--prompt',str(payload.get('motion_prompt','gentle cinematic movement')),
         '--base_seed',str(int(payload.get('seed') or 0)),'--frame_num',str(frames),'--save_file',str(output)]
    env=os.environ.copy(); env.setdefault('PYTORCH_CUDA_ALLOC_CONF','expandable_segments:True')
    # Optional multi-GPU path for Kaggle/Colab. Enable only after verifying CUDA_VISIBLE_DEVICES.
    nproc=int(os.getenv('WAN_NPROC_PER_NODE','1'))
    if nproc>1:
        cmd=[sys.executable,'-m','torch.distributed.run',f'--nproc_per_node={nproc}',*cmd[1:]]
        cmd.extend(['--dit_fsdp','--t5_fsdp','--ulysses_size',str(nproc)])
    proc=subprocess.run(cmd,cwd=repo,env=env,text=True,capture_output=True,timeout=int(os.getenv('WAN_WORKER_TIMEOUT_S','7200')))
    if proc.returncode:
        raise RuntimeError(f'Wan worker failed ({proc.returncode}).\nSTDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-4000:]}')
    if not output.exists() or output.stat().st_size<100_000:
        raise RuntimeError('Wan completed but output MP4 is missing or unexpectedly small')
    return output

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
    payload=json.loads(Path(a.input).read_text(encoding='utf-8')); print(run(payload,Path(a.output)))
if __name__=='__main__': main()
