from __future__ import annotations
import json, re, shutil, subprocess, base64, os
from pathlib import Path
from typing import Any
from .models import Storyboard
from .hashing import sha256_json

def _audio_stats(path: Path) -> dict[str,Any]:
    if not shutil.which('ffprobe'): raise RuntimeError('ffprobe is required for narration review')
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr)
    duration=float(p.stdout.strip()); mean=None; peak=None
    if shutil.which('ffmpeg'):
        q=subprocess.run(['ffmpeg','-hide_banner','-i',str(path),'-af','volumedetect','-f','null','-'],capture_output=True,text=True)
        m=re.search(r'mean_volume:\s*(-inf|-?[0-9.]+) dB',q.stderr); pk=re.search(r'max_volume:\s*(-inf|-?[0-9.]+) dB',q.stderr)
        mean=(-999.0 if m and m.group(1)=='-inf' else float(m.group(1))) if m else None
        peak=(-999.0 if pk and pk.group(1)=='-inf' else float(pk.group(1))) if pk else None
    return {'duration_s':duration,'mean_volume_db':mean,'peak_volume_db':peak}

def audit_narration_assets(storyboard: Storyboard, narration_dir: str|Path, output_path: str|Path) -> dict:
    """Run repeatable technical/script checks. It does not certify native pronunciation."""
    root=Path(narration_dir); rows=[]; problems=[]
    for shot in storyboard.shots:
        audio=root/f'{shot.id}.wav'
        row={'shot_id':shot.id,'audio_exists':audio.exists(),'script_characters':len(shot.narration.text),'lexicon_entries':len(shot.narration.lexicon)}
        if not audio.exists():
            row['passed']=False; row['issues']=['missing audio file']; problems.append(f'{shot.id}: missing narration audio'); rows.append(row); continue
        try:
            stats=_audio_stats(audio); row.update(stats)
            rate=len(shot.narration.text.split())/max(stats['duration_s'],0.01)
            row['words_per_second']=round(rate,2)
            issues=[]
            if stats['duration_s']<0.25: issues.append('audio duration is implausibly short')
            if stats['mean_volume_db'] is None: issues.append('audio loudness could not be measured')
            elif stats['mean_volume_db']<-45: issues.append('audio may be silent or too quiet')
            if stats['peak_volume_db'] is not None and stats['peak_volume_db']>0: issues.append('audio clips above 0 dBFS')
            # The target durations are planning estimates; warn if spoken words are unusually dense.
            limit=2.2 if shot.narration.lang.startswith(('am','om','ti')) else 3.0
            if rate>limit: issues.append('spoken rate is high; check pacing against the picture')
            row['issues']=issues; row['passed']=not issues
            problems.extend(f'{shot.id}: {x}' for x in issues)
        except Exception as exc:
            row['passed']=False; row['issues']=[str(exc)]; problems.append(f'{shot.id}: {exc}')
        rows.append(row)
    passed=all(r.get('passed',False) for r in rows)
    notes=('Automated technical audit passed: all narration files exist, are measurable, and passed silence/clipping/pacing checks. ' if passed else 'Automated technical audit found issues: '+'; '.join(problems)+'. ')
    notes+='This automated report does not verify Amharic/Afaan Oromo pronunciation, idiom, or translation accuracy; native-speaker listening approval remains mandatory before release.'
    contract={s.id:{'text':s.narration.text,'lang':s.narration.lang,'lexicon':s.narration.lexicon,'subtitle_en':s.subtitle_en} for s in storyboard.shots}
    report={'automated_audit':True,'automated_checks_passed':passed,'narration_contract_hash':sha256_json(contract),'native_speaker_review_required':True,'approved':False,'reviewer':'','notes':notes,'shots':rows,'issues':problems}
    dest=Path(output_path); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

def approve_native_review(review_path: str|Path, reviewer: str, approved: bool) -> dict:
    path=Path(review_path); report=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not reviewer.strip(): raise ValueError('A native-speaker reviewer identity is required')
    if not report.get('automated_audit') or not report.get('automated_checks_passed'):
        raise ValueError('Run and pass the automated narration checks before recording native-speaker approval')
    if not approved: raise ValueError('Native-speaker approval must be explicitly confirmed')
    report['reviewer']=reviewer.strip(); report['approved']=True
    report['native_speaker_approval']='explicit human attestation after listening to all narration lines'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def audit_narration_with_gemini(storyboard: Storyboard, narration_dir: str|Path, report_path: str|Path, *, log_path: str|Path='runs.jsonl') -> dict:
    """Ask Gemini multimodal to compare each rendered narration clip with its script/subtitle.

    This is a machine-assisted screening signal, not a native-speaker certification.
    """
    from .providers import ProviderConfig, _post_json
    from .observability import log_model_call
    config=ProviderConfig.from_env()
    if not config.gemini_api_key: raise RuntimeError('GEMINI_API_KEY is required for Gemini narration/translation audit')
    root=Path(narration_dir); parts=[]; manifest=[]
    for shot in storyboard.shots:
        audio=root/f'{shot.id}.wav'
        if not audio.exists(): raise RuntimeError(f'Missing narration audio for Gemini audit: {audio}')
        raw=audio.read_bytes()
        if len(raw)>8_000_000: raise RuntimeError(f'{audio.name} is too large for inline Gemini audit; transcode to mono 24 kHz WAV first')
        manifest.append({'id':shot.id,'spoken_script':shot.narration.text,'spoken_language':shot.narration.lang,'english_subtitle':shot.subtitle_en})
        parts.append({'text':f"Audio clip for {shot.id}. Expected spoken language: {shot.narration.lang}. Expected script: {shot.narration.text}. English subtitle: {shot.subtitle_en}. Listen to this audio now."})
        parts.append({'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(raw).decode('ascii')}})
    instruction=("You are an audio QA reviewer for a multilingual short film. Compare each attached shot audio with its expected script and English subtitle. "
      "For each shot, assess whether the spoken audio appears to match the script, whether the language matches, whether any pronunciation is clearly problematic, "
      "and whether the English subtitle preserves the meaning of the narration. If the language is outside your reliable competence or audio is unclear, use unable_to_assess; "
      "do not guess. Do not claim native-speaker approval. Return JSON only with keys: shots (array of objects with id, audio_matches_script (pass|possible_issue|unable_to_assess), "
      "language_match (pass|possible_issue|unable_to_assess), pronunciation_status (clear|possible_issue|unable_to_assess), subtitle_alignment (aligned|partial|misaligned|unable_to_assess), "
      "confidence (number 0..1), notes (short string)), and summary (string). Preserve shot IDs exactly.\nShot manifest:\n"+json.dumps(manifest,ensure_ascii=False))
    request={'contents':[{'role':'user','parts':[{'text':instruction},*parts]}],
             'generationConfig':{'responseMimeType':'application/json','temperature':0.1}}
    model=os.getenv('GEMINI_TEXT_MODEL','gemini-3.8-flash')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    response=log_model_call(Path(log_path),stage='narration_audio_translation_audit',provider='Google Gemini',model=model,
        inputs={'storyboard_title':storyboard.title,'shot_ids':[s.id for s in storyboard.shots]},output=report_path,
        call=lambda:_post_json(url,request,{'x-goog-api-key':config.gemini_api_key},config.request_timeout_s))
    try:
        raw_text=response['candidates'][0]['content']['parts'][0]['text']
        result=json.loads(raw_text[raw_text.find('{'):raw_text.rfind('}')+1])
    except Exception as exc:
        raise RuntimeError(f'Gemini audio audit returned invalid JSON: {str(response)[:800]}') from exc
    expected={s.id for s in storyboard.shots}; actual={x.get('id') for x in result.get('shots',[])}
    if expected != actual: raise RuntimeError(f'Gemini audio audit shot IDs mismatch; expected {sorted(expected)}, got {sorted(actual)}')
    path=Path(report_path); report=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    report['gemini_audio_audit']={'completed':True,'model':model,'summary':result.get('summary',''),'shots':result['shots']}
    report['notes']=(report.get('notes','')+' Gemini multimodal audit: '+str(result.get('summary','No summary returned'))+
      '. This is an automated screening result only; native-speaker approval remains mandatory.')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report['gemini_audio_audit']
