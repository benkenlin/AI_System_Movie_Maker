from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

def summarize_costs(path:str|Path='runs.jsonl')->dict:
    totals=defaultdict(lambda:{'calls':0,'failures':0,'latency_s':0.0,'worker_wall_minutes':0.0,'estimated_cost_usd':0.0})
    p=Path(path)
    if not p.exists(): return {'stages':{},'total_calls':0,'total_estimated_cost_usd':0.0}
    for line in p.read_text(encoding='utf-8').splitlines():
        try: row=json.loads(line)
        except json.JSONDecodeError: continue
        item=totals[row.get('stage','unknown')]; item['calls']+=1; item['failures']+=row.get('status')=='failed'; item['latency_s']+=float(row.get('latency_s',0)); item['worker_wall_minutes']+=float(row.get('worker_wall_minutes',0)); item['estimated_cost_usd']+=float(row.get('estimated_cost_usd') or 0)
    stages={k:{**v,'latency_s':round(v['latency_s'],3),'worker_wall_minutes':round(v['worker_wall_minutes'],3),'estimated_cost_usd':round(v['estimated_cost_usd'],6)} for k,v in totals.items()}
    return {'stages':stages,'total_calls':sum(v['calls'] for v in stages.values()),'total_estimated_cost_usd':round(sum(v['estimated_cost_usd'] for v in stages.values()),6)}
