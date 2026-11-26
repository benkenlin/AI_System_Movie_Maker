import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from ai_content.models import Storyboard
from ai_content.observability import log_model_call
from ai_content.costs import summarize_costs
from ai_content.ethics import check_release_gates, ReleaseBlocked
from ai_content.providers import ProviderConfig, ProviderRegistry, ProviderError
from ai_content.music import select_music_candidate, MusicSelectionError

ROOT=Path(__file__).resolve().parents[1]

def storyboard_payload(): return json.loads((ROOT/'examples/storyboard.example.json').read_text(encoding='utf-8'))

def test_storyboard_requires_both_formats_and_consistent_shot_count():
    p=storyboard_payload(); p['aspect_ratios']=['16:9']
    with pytest.raises(ValidationError): Storyboard.model_validate(p)
    p=storyboard_payload(); p['shot_count']=9
    with pytest.raises(ValidationError): Storyboard.model_validate(p)

def test_storyboard_rejects_unknown_character_and_nonsequential_ids():
    p=storyboard_payload(); p['shots'][0]['characters']=['not_defined']
    with pytest.raises(ValidationError): Storyboard.model_validate(p)
    p=storyboard_payload(); p['shots'][1]['id']='s09'
    with pytest.raises(ValidationError): Storyboard.model_validate(p)

def test_real_character_requires_release_consent():
    p=storyboard_payload(); p['characters']['grandmother']['origin']='consented_real'
    with pytest.raises(ValidationError): Storyboard.model_validate(p)

def test_log_model_call_writes_success_and_failure_events(tmp_path):
    log=tmp_path/'runs.jsonl'
    assert log_model_call(log,stage='unit',provider='test',model='mock',inputs={'a':1},output=None,call=lambda:42)==42
    with pytest.raises(RuntimeError): log_model_call(log,stage='unit',provider='test',model='mock',inputs={},output=None,call=lambda:(_ for _ in ()).throw(RuntimeError('expected')))
    rows=[json.loads(x) for x in log.read_text().splitlines()]
    assert [x['status'] for x in rows]==['succeeded','failed']
    assert summarize_costs(log)['total_calls']==2

def test_registry_fails_clearly_without_cloudflare_credentials(tmp_path):
    cfg=ProviderConfig(cloudflare_account_id='',cloudflare_token='')
    with pytest.raises(ProviderError,match='CLOUDFLARE_ACCOUNT_ID'):
        ProviderRegistry(cfg).image().generate('prompt',tmp_path/'x.png')

def test_release_gate_blocks_until_license_reviewed(tmp_path):
    p=storyboard_payload(); sb=Storyboard.model_validate(p)
    (tmp_path/'licenses.json').write_text(json.dumps({'release_reviewed':False}))
    with pytest.raises(ReleaseBlocked): check_release_gates(sb,tmp_path/'consent.json',licenses_path=tmp_path/'licenses.json')
    (tmp_path/'licenses.json').write_text(json.dumps({'release_reviewed':True,'output_rights_reviewed':True,'models':{k:{'model':'test-v1','license':'Test license reviewed','source_url':'https://example.invalid/license','reviewed':True,'commercial_use_reviewed':True} for k in ('image','video','music','tts')}}))
    p['music']['candidates']=['candidate.wav']; p['music']['selected']='candidate.wav'; p['music']['rationale']='This instrumental candidate fits the reflective mood and has a clean ending.'
    sb=Storyboard.model_validate(p)
    (tmp_path/'narration.json').write_text(json.dumps({'approved':True,'reviewer':'Native speaker','notes':'Pronunciation and meaning reviewed.'}))
    assert check_release_gates(sb,tmp_path/'consent.json',licenses_path=tmp_path/'licenses.json',narration_review_path=tmp_path/'narration.json')['allowed']

def test_music_selection_requires_reason(tmp_path):
    with pytest.raises(MusicSelectionError,match='rationale'):
        select_music_candidate(tmp_path/'storyboard.json',tmp_path/'candidate.wav','no')

def test_production_cache_reuses_only_matching_inputs(tmp_path):
    from ai_content.production import ProductionPipeline
    from ai_content.providers import ProviderRegistry, ProviderConfig
    pipeline=ProductionPipeline(tmp_path,ProviderRegistry(ProviderConfig()),tmp_path/'runs.jsonl')
    destination=tmp_path/'asset.bin'; calls=[]
    def make():
        calls.append(1); destination.write_bytes(b'asset'); return destination
    pipeline._run('image','fake','v1',{'prompt':'one'},destination,make)
    pipeline._run('image','fake','v1',{'prompt':'one'},destination,make)
    assert len(calls)==1
    pipeline._run('image','fake','v1',{'prompt':'two'},destination,make)
    assert len(calls)==2

def test_music_selection_persists_human_rationale(tmp_path):
    import wave
    payload=storyboard_payload(); storyboard=tmp_path/'storyboard.json'; storyboard.write_text(json.dumps(payload),encoding='utf-8')
    candidate=tmp_path/'music.wav'
    with wave.open(str(candidate),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(8000); wf.writeframes(b'\0\0'*8000*70)
    select_music_candidate(storyboard,candidate,'The restrained instrumental texture supports the reflective arc and has a clean ending.')
    updated=json.loads(storyboard.read_text())
    assert updated['music']['selected']==str(candidate)
    assert len(updated['music']['rationale'])>=20
    Storyboard.model_validate(updated)

def test_video_worker_requires_human_keyframe_approval_and_invalidates_changed_frames(tmp_path):
    from ai_content.production import ProductionPipeline, ProductionError
    from ai_content.providers import ProviderRegistry, ProviderConfig
    sb=Storyboard.model_validate(storyboard_payload()); pipe=ProductionPipeline(tmp_path,ProviderRegistry(ProviderConfig()),tmp_path/'runs.jsonl')
    frames=tmp_path/'keyframes'; frames.mkdir()
    for shot in sb.shots: (frames/f'{shot.id}.png').write_bytes(shot.id.encode())
    with pytest.raises(ProductionError,match='Human keyframe approval'):
        pipe.generate_clips(sb)
    pipe.approve_keyframes(sb,'Reviewer A')
    (frames/'s01.png').write_bytes(b'changed')
    with pytest.raises(ProductionError,match='changed after approval'):
        pipe.generate_clips(sb)

def test_cloudflare_flux2_uses_multipart_reference_image_and_writes_result(tmp_path,monkeypatch):
    import base64
    import ai_content.providers as providers
    reference=tmp_path/'ref.png'; reference.write_bytes(b'fake-reference-image')
    captured={}
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return json.dumps({'success':True,'result':{'image':base64.b64encode(b'generated-png').decode()}}).encode()
    def fake_urlopen(request,timeout):
        captured['data']=request.data; captured['content_type']=request.headers['Content-type']; captured['timeout']=timeout
        return Response()
    monkeypatch.setattr(providers,'urlopen',fake_urlopen)
    cfg=ProviderConfig(cloudflare_account_id='acct',cloudflare_token='token')
    output=ProviderRegistry(cfg).image().generate('a cinematic coffee ceremony',tmp_path/'out.png',seed=77,reference_images=[reference],width=1280,height=720)
    body=captured['data']
    assert b'name="input_image_0"' in body and b'fake-reference-image' in body
    assert b'name="width"' in body and b'1280' in body and b'77' in body
    assert captured['content_type'].startswith('multipart/form-data; boundary=')
    assert output.read_bytes()==b'generated-png'

def test_gemini_tts_uses_pronunciation_lexicon_and_writes_wav(tmp_path,monkeypatch):
    import base64
    import ai_content.providers as providers
    captured={}
    def fake_post(url,payload,headers,timeout):
        captured['url']=url; captured['payload']=payload; captured['headers']=headers
        return {'candidates':[{'content':{'parts':[{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(b'RIFF-test').decode()}}]}}]}
    monkeypatch.setattr(providers,'_post_json',fake_post)
    cfg=ProviderConfig(gemini_api_key='secret-key',gemini_tts_model='gemini-3.8-flash-tts')
    output=providers.GeminiTTSProvider(cfg).synthesize('Hello Abebe','am',tmp_path/'voice.wav',voice='Kore',lexicon={'Abebe':'Ah-beh-beh'},model='gemini-3.8-flash-tts')
    text=captured['payload']['contents'][0]['parts'][0]['text']
    assert text=='Hello Ah-beh-beh'
    assert captured['payload']['generationConfig']['speechConfig']['voiceConfig']['voice']=='Kore'
    assert captured['payload']['generationConfig']['speechConfig']['languageCode']=='am'
    assert captured['headers']['x-goog-api-key']=='secret-key'
    assert output.read_bytes()==b'RIFF-test'

def test_ffmpeg_assembly_smoke_exports_both_ratios(tmp_path):
    import shutil, subprocess
    from ai_content.assembly import FilmAssembler, final_quality_check
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/ffprobe are not installed')
    sb=Storyboard.model_validate(storyboard_payload())
    for folder in ('clips','narration','music'): (tmp_path/folder).mkdir(exist_ok=True)
    for shot in sb.shots:
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x90:d=1','-an','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(tmp_path/'clips'/f'{shot.id}.mp4')],check=True)
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1','-c:a','pcm_s16le',str(tmp_path/'narration'/f'{shot.id}.wav')],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=65','-c:a','pcm_s16le',str(tmp_path/'music'/'score.wav')],check=True)
    outputs=FilmAssembler(tmp_path,width=320,height=180).assemble(sb,music=tmp_path/'music'/'score.wav',release_check=False)
    qc=final_quality_check(outputs)
    assert qc['horizontal']['width']==320 and qc['horizontal']['height']==180
    assert qc['vertical']['width']==180 and qc['vertical']['height']==320
    assert all(x['passed'] for x in qc.values())

def test_auto_music_selection_adds_cues_and_persists_technical_ranking(tmp_path):
    import subprocess
    from ai_content.music import auto_select_music_candidate
    payload=storyboard_payload(); payload['music']['cues']=[]
    storyboard=tmp_path/'storyboard.json'; storyboard.write_text(json.dumps(payload),encoding='utf-8')
    candidate=tmp_path/'candidate.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=220:duration=70','-c:a','pcm_s16le',str(candidate)],check=True)
    result=auto_select_music_candidate(storyboard,[candidate])
    updated=json.loads(storyboard.read_text())
    assert updated['music']['selected']==str(candidate)
    assert len(updated['music']['cues'])>=3
    assert len(updated['music']['rationale'])>=20
    assert (tmp_path/'music_selection.json').exists()
    Storyboard.model_validate(updated)
    assert result['ranking'][0]['score']>=0


def test_automatic_narration_audit_does_not_accept_silent_audio(tmp_path):
    import wave
    from ai_content.review import audit_narration_assets, approve_native_review
    sb=Storyboard.model_validate(storyboard_payload()); narration=tmp_path/'narration'; narration.mkdir()
    for shot in sb.shots:
        with wave.open(str(narration/f'{shot.id}.wav'),'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(8000); wf.writeframes(b'\0\0'*8000)
    report=audit_narration_assets(sb,narration,tmp_path/'review.json')
    assert report['automated_audit'] is True
    assert report['automated_checks_passed'] is False
    with pytest.raises(ValueError,match='automated narration checks'):
        approve_native_review(tmp_path/'review.json','Native reviewer',True)

def test_music_prompt_contains_default_shot_cues_when_storyboard_has_none():
    from ai_content.music import build_cue_aware_prompt
    sb=Storyboard.model_validate(storyboard_payload())
    prompt=build_cue_aware_prompt(sb)
    assert 'fade in' in prompt
    assert 'swell' in prompt
    assert 'fade out' in prompt
    assert 'no vocals' in prompt.lower()

def test_release_gate_rejects_stale_automated_narration_review(tmp_path):
    p=storyboard_payload(); p['music']['candidates']=['candidate.wav']; p['music']['selected']='candidate.wav'
    p['music']['rationale']='The selected instrumental track covers the film and has acceptable headroom.'
    sb=Storyboard.model_validate(p)
    licenses={'release_reviewed':True,'output_rights_reviewed':True,
              'models':{k:{'model':'test-v1','license':'Test license','source_url':'https://example.invalid/license','reviewed':True,'commercial_use_reviewed':True} for k in ('image','video','music','tts')}}
    (tmp_path/'licenses.json').write_text(json.dumps(licenses))
    contract={s['id']:{'text':s['narration']['text'],'lang':s['narration']['lang'],'lexicon':s['narration'].get('lexicon',{}),'subtitle_en':s['subtitle_en']} for s in p['shots']}
    (tmp_path/'narration.json').write_text(json.dumps({'automated_audit':True,'approved':True,'reviewer':'Native speaker','notes':'Reviewed all lines.','narration_contract_hash':'stale-hash'}))
    with pytest.raises(ReleaseBlocked,match='stale'):
        check_release_gates(sb,tmp_path/'consent.json',licenses_path=tmp_path/'licenses.json',narration_review_path=tmp_path/'narration.json')

def test_production_narration_reads_pydantic_voice_config_and_passes_style(tmp_path):
    from ai_content.production import ProductionPipeline
    from ai_content.providers import ProviderRegistry, ProviderConfig
    sb=Storyboard.model_validate(storyboard_payload())
    cfg=ProviderConfig(gemini_tts_voice='FallbackVoice',gemini_tts_model='fallback-model',gemini_tts_style='Default style')
    registry=ProviderRegistry(cfg); calls=[]
    class FakeSpeech:
        def synthesize(self,text,language,destination,*,voice,lexicon=None,model=None,style_prompt=None):
            calls.append({'voice':voice,'model':model,'style_prompt':style_prompt,'language':language})
            destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(b'fake wav'); return destination
    registry.speech=lambda:FakeSpeech()
    result=ProductionPipeline(tmp_path,registry,tmp_path/'runs.jsonl').generate_narration(sb)
    assert len(result)==sb.shot_count
    assert calls[0]['voice']==sb.narration_voice.voice
    assert calls[0]['model']==sb.narration_voice.model
    assert calls[0]['style_prompt']==cfg.gemini_tts_style

def test_gemini_music_audit_receives_compact_audio_and_returns_per_candidate_scores(tmp_path,monkeypatch):
    import subprocess
    import ai_content.providers as providers
    from ai_content.music import audit_music_candidates_with_gemini
    candidates=[]
    for i in range(3):
        path=tmp_path/f'candidate_{i+1}.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=frequency={220+i*50}:duration=3','-c:a','pcm_s16le',str(path)],check=True)
        candidates.append(path)
    captured={}
    def fake_post(url,payload,headers,timeout):
        captured['payload']=payload
        return {'candidates':[{'content':{'parts':[{'text':json.dumps({'candidates':[{'candidate':p.name,'instrumental_confidence':0.95,'vocal_presence':'none','narrative_fit_score':80+i,'cue_fit_score':82,'ending_score':85,'rationale':'Restrained instrumental texture supports the reflective arc.'} for i,p in enumerate(candidates,1)],'summary':'All three candidates are instrumental; candidate 3 has the strongest cue fit.'})}]}}]}
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    monkeypatch.setattr(providers,'_post_json',fake_post)
    report=audit_music_candidates_with_gemini(storyboard_payload(),candidates,output_path=tmp_path/'music_semantic_audit.json',log_path=tmp_path/'runs.jsonl')
    assert report['status']=='completed'
    assert len(report['candidates'])==3
    assert any(p.get('inlineData',{}).get('mimeType')=='audio/mpeg' for p in captured['payload']['contents'][0]['parts'])
