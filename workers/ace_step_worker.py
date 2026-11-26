#!/usr/bin/env python3
"""ACE-Step 1.5 API worker implementing the project's JSON worker contract.

Run ACE-Step's official API server separately (default http://127.0.0.1:8001):
    python -m acestep.api_server
"""
from __future__ import annotations
import argparse, json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

BASE=os.getenv('ACE_STEP_API_URL','http://127.0.0.1:8001').rstrip('/')
TOKEN=os.getenv('ACE_STEP_API_KEY','')
TIMEOUT=int(os.getenv('ACE_STEP_WORKER_TIMEOUT_S','3600'))

def request(method, url, payload=None):
    data=json.dumps(payload).encode() if payload is not None else None
    headers={'Content-Type':'application/json'} if payload is not None else {}
    if TOKEN: headers['Authorization']=f'Bearer {TOKEN}'
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=120) as r: return r.read(),r.headers.get('Content-Type','')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'ACE-Step API {e.code}: {e.read().decode(errors="replace")[:1500]}') from e

def unwrap(obj):
    if obj.get('code',200)!=200 or obj.get('error'): raise RuntimeError(f'ACE-Step error: {obj.get("error")}')
    return obj.get('data',obj)

def run(payload:dict, output:Path):
    prompt=payload.get('prompt','').strip()
    if not prompt: raise ValueError('Music prompt is empty')
    duration=float(payload.get('duration_s',60))
    body={'prompt':prompt,'lyrics':'','thinking':True,'task_type':'text2music','audio_format':'wav',
          'audio_duration':duration,'use_random_seed':False,'seed':int(payload.get('seed',0)),
          'batch_size':1,'inference_steps':8,'use_cot_caption':True,'use_cot_language':False}
    if payload.get('instrumental',True): body['lyrics']=''
    raw,_=request('POST',BASE+'/release_task',body); task=unwrap(json.loads(raw))
    task_id=task.get('task_id')
    if not task_id: raise RuntimeError(f'ACE-Step response missing task_id: {task}')
    deadline=time.time()+TIMEOUT
    while time.time()<deadline:
        raw,_=request('POST',BASE+'/query_result',{'task_id_list':[task_id]})
        result=unwrap(json.loads(raw)); item=(result[0] if isinstance(result,list) and result else result)
        status=item.get('status')
        if status==2: raise RuntimeError(f'ACE-Step generation failed: {item}')
        if status==1:
            detail=item.get('result',[])
            if isinstance(detail,str): detail=json.loads(detail)
            if isinstance(detail,dict): detail=[detail]
            if not detail or not detail[0].get('file'): raise RuntimeError(f'ACE-Step succeeded without an audio file: {item}')
            file_url=detail[0]['file']
            if file_url.startswith('/'): file_url=BASE+file_url
            elif not file_url.startswith('http'): file_url=BASE+'/'+file_url.lstrip('/')
            headers={'Authorization':f'Bearer {TOKEN}'} if TOKEN else {}
            req=urllib.request.Request(file_url,headers=headers)
            with urllib.request.urlopen(req,timeout=300) as r: audio=r.read()
            if not audio: raise RuntimeError('ACE-Step returned an empty audio file')
            output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(audio)
            return output
        time.sleep(5)
    raise TimeoutError(f'ACE-Step task {task_id} exceeded {TIMEOUT}s')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
    payload=json.loads(Path(a.input).read_text(encoding='utf-8')); out=run(payload,Path(a.output)); print(out)
if __name__=='__main__': main()
