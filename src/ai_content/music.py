from __future__ import annotations
import json, shutil, subprocess, re, os, base64, tempfile, hashlib
from pathlib import Path
from typing import Any

class MusicSelectionError(ValueError): pass

def inspect_candidate(path: str | Path) -> dict[str, Any]:
    path=Path(path)
    if not path.exists(): raise MusicSelectionError(f'Music candidate does not exist: {path}')
    if not shutil.which('ffprobe'): raise MusicSelectionError('ffprobe is required to inspect music candidates')
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True)
    if p.returncode: raise MusicSelectionError(p.stderr)
    duration=float(p.stdout.strip())
    if duration <= 0: raise MusicSelectionError('Music candidate has invalid duration')
    mean_db=peak_db=None
    if shutil.which('ffmpeg'):
        q=subprocess.run(['ffmpeg','-hide_banner','-i',str(path),'-af','volumedetect','-f','null','-'],capture_output=True,text=True)
        output=q.stderr
        m=re.search(r'mean_volume:\s*(-inf|-?[0-9.]+) dB',output)
        pk=re.search(r'max_volume:\s*(-inf|-?[0-9.]+) dB',output)
        mean_db=(-999.0 if m and m.group(1)=='-inf' else float(m.group(1))) if m else None
        peak_db=(-999.0 if pk and pk.group(1)=='-inf' else float(pk.group(1))) if pk else None
    return {'path':str(path),'duration_s':duration,'bytes':path.stat().st_size,'mean_volume_db':mean_db,'peak_volume_db':peak_db}

def default_music_cues(shots: list) -> list[dict[str,str]]:
    """Create a simple beginning/build/resolution cue map when the draft omitted cues."""
    ids=[s.get('id') if isinstance(s,dict) else s.id for s in shots]
    if not ids: return []
    cues=[{'at_shot':ids[0],'action':'fade_in','note':'Introduce the main motif gently beneath the opening narration.'}]
    if len(ids)>=4:
        cues.append({'at_shot':ids[len(ids)//2],'action':'swell','note':'Build warmth and emotional momentum through the central story beat.'})
    if len(ids)>=6:
        cues.append({'at_shot':ids[-2],'action':'drop','note':'Reduce density and leave space for the final narration.'})
    cues.append({'at_shot':ids[-1],'action':'fade_out','note':'Resolve the motif with a soft, clean ending.'})
    # Avoid duplicate cue actions at the same shot for short storyboards.
    dedup=[]; seen=set()
    for cue in cues:
        key=(cue['at_shot'],cue['action'])
        if key not in seen: dedup.append(cue); seen.add(key)
    return dedup

def build_cue_aware_prompt(storyboard) -> str:
    """Turn storyboard emotion and shot-tied cues into explicit score instructions."""
    music=storyboard.music
    shot_map={s.id:s for s in storyboard.shots}
    cue_lines=[]
    active_cues=music.cues or default_music_cues(storyboard.shots)
    for cue in active_cues:
        at_shot=cue.get('at_shot') if isinstance(cue,dict) else cue.at_shot
        action=cue.get('action') if isinstance(cue,dict) else cue.action
        note=cue.get('note') if isinstance(cue,dict) else cue.note
        shot=shot_map.get(at_shot)
        emotion=(shot.narration.text[:180] if shot else '')
        cue_lines.append(f"At {at_shot}: {action.replace('_',' ')}; {note or emotion}")
    arc='; '.join(f"{s.id}: {s.narration.text[:100]}" for s in storyboard.shots)
    cues=' | '.join(cue_lines) if cue_lines else 'Begin restrained, develop gradually through the middle, reach a gentle emotional peak near the final third, then resolve with a clean natural fade.'
    return (f"{music.prompt}. Instrumental score only: absolutely no vocals, lyrics, speech, choir or vocal samples. "
            f"Narrative context: {storyboard.title}. {storyboard.logline}. Emotional progression by shot: {arc}. "
            f"Timed music cues: {cues}. Keep the arrangement supportive under spoken narration, with sparse midrange during voice, "
            f"no abrupt transient peaks, a coherent motif, and a resolved ending with room for a 2-second fade. "
            f"Target duration {music.duration_s:.1f} seconds.")

def score_candidate(info: dict[str, Any], target_duration: float) -> tuple[float, list[str]]:
    reasons=[]; score=100.0
    duration=info['duration_s']
    if duration < target_duration:
        score -= 1000; reasons.append('too short for the film')
    elif duration > target_duration*1.35:
        score -= min(20,(duration/target_duration-1.35)*20); reasons.append('requires a longer trim')
    else: reasons.append('covers the complete film')
    mean=info.get('mean_volume_db'); peak=info.get('peak_volume_db')
    if mean is None: score -= 1000; reasons.append('loudness could not be measured')
    elif mean < -45: score -= 1000; reasons.append('candidate is silent or nearly silent')
    elif -27 <= mean <= -13: reasons.append('average level is suitable for narration mixing')
    else: score -= min(25,abs(mean+20)*1.5); reasons.append('average level needs more gain staging')
    if peak is None: score -= 5
    elif peak < -45: score -= 1000; reasons.append('candidate has no meaningful audio peak')
    elif peak <= -0.5: reasons.append('peak headroom is available')
    else: score -= min(20,(peak+0.5)*4); reasons.append('peak level risks clipping')
    if info.get('bytes',0)<100_000: score-=50; reasons.append('file is unexpectedly small')
    return score,reasons


def audit_music_candidates_with_gemini(storyboard_payload: dict, candidates: list[str|Path], *, output_path: str|Path, log_path: str|Path='runs.jsonl') -> dict|None:
    """Multimodal screening of instrumental candidates against the storyboard's arc/cues."""
    from .providers import ProviderConfig, _post_json
    from .observability import log_model_call
    config=ProviderConfig.from_env()
    if not config.gemini_api_key: return None
    if not shutil.which('ffmpeg'): return {'status':'skipped','reason':'ffmpeg unavailable for compact audio upload'}
    music=storyboard_payload['music']; shots=storyboard_payload['shots']
    cues=music.get('cues',[]) or default_music_cues(shots)
    context={'title':storyboard_payload['title'],'logline':storyboard_payload['logline'],
             'music_brief':music['prompt'],'instrumental_required':bool(music.get('instrumental',True)),
             'shot_arc':[{'id':x['id'],'narration':x['narration']['text']} for x in shots], 'music_cues':cues}
    parts=[{'text':("Listen to each attached candidate as an original film score. Evaluate actual audio, not just its filename. "
        "Compare its emotional arc and timed cue behavior to the supplied storyboard, check for vocals/speech, assess whether it leaves space for narration, "
        "and judge whether the ending resolves cleanly. Return JSON only: candidates array with candidate (exact filename), instrumental_confidence (0..1), "
        "vocal_presence (none|possible|clear), narrative_fit_score (0..100), cue_fit_score (0..100), ending_score (0..100), "
        "rationale (short evidence-based explanation); summary (string). If uncertain, say so in rationale. Do not infer details that cannot be heard.\n"+json.dumps(context,ensure_ascii=False))}]
    hashes={}; temp_dirs=[]
    try:
        for index,path_value in enumerate(candidates,1):
            source=Path(path_value); hashes[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
            td=tempfile.TemporaryDirectory(prefix='music-audit-'); temp_dirs.append(td)
            compact=Path(td.name)/f'candidate_{index}.mp3'
            proc=subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-ac','1','-ar','22050','-b:a','64k',str(compact)],capture_output=True,text=True)
            if proc.returncode or not compact.exists(): raise RuntimeError(f'Could not prepare {source.name} for Gemini audio review: {proc.stderr[-500:]}')
            parts.append({'text':f'Candidate audio {index}: {source.name}.'})
            parts.append({'inlineData':{'mimeType':'audio/mpeg','data':base64.b64encode(compact.read_bytes()).decode('ascii')}})
        request={'contents':[{'role':'user','parts':parts}], 'generationConfig':{'responseMimeType':'application/json','temperature':0.1}}
        model=os.getenv('GEMINI_TEXT_MODEL','gemini-3.8-flash')
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        response=log_model_call(Path(log_path),stage='music_candidate_audio_audit',provider='Google Gemini',model=model,
            inputs={'storyboard_title':storyboard_payload['title'],'candidate_hashes':hashes,'music_cues':cues},output=output_path,
            call=lambda:_post_json(url,request,{'x-goog-api-key':config.gemini_api_key},config.request_timeout_s))
        raw=response['candidates'][0]['content']['parts'][0]['text']
        result=json.loads(raw[raw.find('{'):raw.rfind('}')+1])
        expected={Path(x).name for x in candidates}; actual={x.get('candidate') for x in result.get('candidates',[])}
        if expected != actual: raise RuntimeError(f'Gemini music audit candidate mismatch: expected {sorted(expected)}, got {sorted(actual)}')
        report={'status':'completed','model':model,'summary':result.get('summary',''),'candidates':result['candidates']}
        Path(output_path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return report
    finally:
        for td in temp_dirs: td.cleanup()

def auto_select_music_candidate(storyboard_path: str | Path, candidates: list[str | Path], *, log_path: str|Path='runs.jsonl') -> dict[str, Any]:
    """Select the best technically valid candidate and persist its auditable rationale.

    This is a machine-assisted selection (Gemini audio fit plus coverage/loudness/headroom), not a claim
    that a model can replace a listener's subjective or cultural judgement.
    """
    path=Path(storyboard_path); payload=json.loads(path.read_text(encoding='utf-8'))
    target=sum(float(s['duration_s']) for s in payload['shots'])
    ranked=[]
    for candidate in candidates:
        info=inspect_candidate(candidate); score,reasons=score_candidate(info,target)
        ranked.append({'info':info,'score':round(score,2),'reasons':reasons})
    if not ranked: raise MusicSelectionError('No music candidates were generated')
    semantic=None
    try:
        semantic=audit_music_candidates_with_gemini(payload,candidates,output_path=path.parent/'music_semantic_audit.json',log_path=log_path)
    except Exception as exc:
        semantic={'status':'failed','reason':str(exc)}
        (path.parent/'music_semantic_audit.json').write_text(json.dumps(semantic,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if semantic and semantic.get('status')=='completed':
        by_name={x['candidate']:x for x in semantic['candidates']}
        for item in ranked:
            audit=by_name.get(Path(item['info']['path']).name,{})
            if audit:
                semantic_score=(float(audit.get('narrative_fit_score',0))*.35 + float(audit.get('cue_fit_score',0))*.30 + float(audit.get('ending_score',0))*.20 + float(audit.get('instrumental_confidence',0))*15)
                item['semantic_audit']=audit; item['semantic_score']=round(semantic_score,2)
                item['score']=round(item['score']*.60+semantic_score*.40,2)
                if audit.get('vocal_presence')=='clear' and payload.get('music',{}).get('instrumental',True):
                    item['score']-=1000; item['reasons'].append('Gemini detected clear vocals in an instrumental score')
    ranked.sort(key=lambda x:x['score'],reverse=True)
    best=ranked[0]
    if best['score'] < 0: raise MusicSelectionError('No candidate meets the minimum technical checks')
    rel=str(Path(best['info']['path']))
    all_candidates=payload.setdefault('music',{}).setdefault('candidates',[])
    for item in ranked:
        candidate_path=str(Path(item['info']['path']))
        if candidate_path not in all_candidates: all_candidates.append(candidate_path)
    cues=payload.get('music',{}).get('cues',[])
    if not cues:
        cues=default_music_cues(payload.get('shots',[]))
        payload['music']['cues']=cues
    cue_summary=', '.join(f"{c['action']} at {c['at_shot']}" for c in cues) or 'gradual emotional build and resolved ending'
    if best.get('semantic_audit'):
        rationale=(f"Automatically selected using technical checks and Gemini audio-fit screening ({best['score']}/100): "
          + str(best['semantic_audit'].get('rationale','')) + ' Technical checks: ' + '; '.join(best['reasons']) +
          f". Storyboard cue map: {cue_summary}. Narration ducking and final loudness normalization are applied during assembly.")
    else:
        rationale=(f"Automatically selected by technical score ({best['score']}/100): "
          + '; '.join(best['reasons']) + f". The candidate was generated from the storyboard's instrumental brief and cue map ({cue_summary}); "
          "Gemini audio-fit screening was unavailable, so no semantic music-quality claim is made. Narration ducking and final loudness normalization are applied during assembly.")
    payload['music']['selected']=rel; payload['music']['rationale']=rationale
    selection_report={'method':'technical_plus_gemini_audio_fit_v1' if semantic and semantic.get('status')=='completed' else 'technical_only_v1','selected_score':best['score'],'ranked_candidates':ranked}
    (path.parent/'music_selection.json').write_text(json.dumps(selection_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for stale in (path.parent/'assembly'/'horizontal.mp4',path.parent/'assembly'/'vertical.mp4',path.parent/'final_qc.json'):
        if stale.exists(): stale.unlink()
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'selected':rel,'rationale':rationale,'ranking':ranked}

def select_music_candidate(storyboard_path: str | Path,candidate: str | Path,rationale: str)->None:
    """Compatibility/manual override helper for controlled experiments."""
    if len(rationale.strip())<20: raise MusicSelectionError('Selection rationale must be at least 20 characters')
    path=Path(storyboard_path); payload=json.loads(path.read_text(encoding='utf-8')); info=inspect_candidate(candidate)
    if info['duration_s']<sum(float(s['duration_s']) for s in payload['shots']): raise MusicSelectionError('Selected music is shorter than the film')
    rel=str(Path(candidate)); candidates=payload.setdefault('music',{}).setdefault('candidates',[])
    if rel not in candidates: candidates.append(rel)
    payload['music']['selected']=rel; payload['music']['rationale']=rationale.strip()
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
