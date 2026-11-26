"""FastAPI wrapper for running the Wan worker in a GPU notebook/server.

Start from the project root with: uvicorn workers.wan_server:app --host 0.0.0.0 --port 8787
Protect it with WAN_WORKER_TOKEN and expose only over a private tunnel/network.
"""
from __future__ import annotations
import json, os, tempfile, hmac
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import FileResponse
from .wan_worker import run

app=FastAPI(title='AI Content System Wan Worker',version='1.0')
TOKEN=os.getenv('WAN_WORKER_TOKEN','')
@app.get('/health')
def health(): return {'status':'ok','worker':'wan2.2-ti2v-5b'}
@app.post('/generate')
async def generate(payload: str = Form(...), image: UploadFile = File(...), authorization: str|None=Header(default=None)):
    if not TOKEN:
        raise HTTPException(503,'WAN_WORKER_TOKEN must be configured before accepting generation requests')
    if not hmac.compare_digest((authorization or '').removeprefix('Bearer ').strip(),TOKEN):
        raise HTTPException(401,'Invalid worker token')
    try: data=json.loads(payload)
    except json.JSONDecodeError: raise HTTPException(400,'payload must be JSON')
    with tempfile.TemporaryDirectory(prefix='wan-api-') as td:
        image_path=Path(td)/(Path(image.filename or 'keyframe.png').name)
        image_path.write_bytes(await image.read()); data['image']=str(image_path)
        output=Path(td)/'shot.mp4'
        try: run(data,output)
        except Exception as exc: raise HTTPException(500,str(exc))
        # FileResponse streams before the temporary directory is removed only if we defer cleanup;
        # read into memory because generated short clips are a few MB and response lifecycle is bounded.
        from fastapi.responses import Response
        return Response(output.read_bytes(),media_type='video/mp4',headers={'Content-Disposition':'attachment; filename=shot.mp4'})
