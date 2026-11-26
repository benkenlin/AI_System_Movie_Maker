from __future__ import annotations
import json, time, hashlib
from pathlib import Path
from typing import Any, Callable

def log_model_call(path:str|Path,*,stage:str,provider:str,model:str,inputs:dict[str,Any],output:str|Path|None,call:Callable[[],Any],estimated_cost_usd:float|None=None,experiment_id:str|None=None,attempt:int|None=None)->Any:
    """Append one durable JSONL event for every external/model invocation."""
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    canonical=json.dumps(inputs,sort_keys=True,ensure_ascii=False,default=str).encode()
    input_hash=hashlib.sha256(canonical).hexdigest(); started=time.perf_counter(); event={'timestamp':time.time(),'stage':stage,'provider':provider,'model':model,'input_hash':input_hash,'parameters':inputs,'estimated_cost_usd':estimated_cost_usd,'cost_estimate_configured':estimated_cost_usd is not None,'experiment_id':experiment_id,'attempt':attempt,'output_path':str(output) if output else None}
    try:
        value=call(); elapsed=time.perf_counter()-started; event.update(status='succeeded',latency_s=round(elapsed,3)); return value
    except Exception as exc:
        elapsed=time.perf_counter()-started
        event.update(status='failed',latency_s=round(elapsed,3),error_type=type(exc).__name__,error=str(exc)[:2000]); raise
    finally:
        if stage in {'video','music'}:
            event['worker_wall_minutes']=round((time.perf_counter()-started)/60,3)
        with p.open('a',encoding='utf-8') as f: f.write(json.dumps(event,ensure_ascii=False,default=str)+'\n')
