from __future__ import annotations
import json, os, sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
except ImportError:
    pass
sys.path.insert(0,str(ROOT/'src'))
from ai_content.db import Database
from ai_content.planning import DraftService, MockPlanner
from ai_content.providers import ProviderConfig, ProviderRegistry, GeminiTextPlanner
from ai_content.production import ProductionPipeline
from ai_content.assembly import FilmAssembler, final_quality_check
from ai_content.validation import load_storyboard
from ai_content.ethics import check_release_gates, ReleaseBlocked
from ai_content.music import auto_select_music_candidate
from ai_content.review import audit_narration_assets, audit_narration_with_gemini, approve_native_review

st.set_page_config(page_title='AI Film Studio',page_icon='🎬',layout='wide')
st.title('🎬 AI Film Studio')
st.caption('Storyboard-driven filmmaking · Amharic narration · English subtitles · 16:9 and 9:16 exports')
OUT=ROOT/'outputs'; OUT.mkdir(exist_ok=True); DB=Database(str(OUT/'studio.db'))
with st.sidebar:
    st.header('Provider configuration')
    st.caption('API keys are read from environment variables; never paste secrets into the storyboard or commit them.')
    st.write('Gemini API key:', 'configured' if os.getenv('GEMINI_API_KEY') else 'not configured')
    st.write('Cloudflare token:', 'configured' if os.getenv('CLOUDFLARE_API_TOKEN') else 'not configured')
    video_ready=bool(os.getenv('VIDEO_WORKER_URL') or (os.getenv('WAN_REPO_DIR') and os.getenv('WAN_CHECKPOINT_DIR')))
    st.write('Video worker:', 'configured' if video_ready else 'not configured')
    st.write('Music worker:', 'configured' if os.getenv('MUSIC_GENERATION_COMMAND') else 'not configured')
    st.divider(); st.write('FFmpeg:', 'available' if os.system('ffmpeg -version >nul 2>&1' if os.name=='nt' else 'ffmpeg -version >/dev/null 2>&1')==0 else 'not found')

tabs=st.tabs(['1 · Create story','2 · Review & approve','3 · Generate assets','4 · Assemble & export','5 · Release & QC'])
with tabs[0]:
    st.subheader('Create a storyboard')
    title=st.text_input('Film title','The Last Coffee Ceremony')
    idea=st.text_area('Film idea','An intimate Ethiopian coffee ceremony brings three generations together through memory, hospitality and shared stories.',height=110)
    lang=st.selectbox('Narration language',['am','en','om','ti','so'],index=0)
    planner_mode=st.radio('Story planner',['Gemini API','Offline template'],horizontal=True,index=0)
    if st.button('Generate storyboard draft',type='primary'):
        try:
            planner=GeminiTextPlanner(ProviderConfig.from_env()) if planner_mode=='Gemini API' else MockPlanner()
            draft=DraftService(DB,planner=planner).create_draft(idea,title=title,language=lang,subtitle_language='en')
            st.session_state['draft_id']=draft['id']; st.success(f"Draft created: {draft['id']} ({draft['status']})")
            st.json(draft['payload'])
        except Exception as e: st.error(str(e))
with tabs[1]:
    st.subheader('Human review gate')
    draft_id=st.text_input('Draft ID',st.session_state.get('draft_id',''))
    if draft_id:
        try:
            draft=DraftService(DB).get_draft(draft_id); st.write('Status:',draft['status']); st.json(draft['payload'])
            if draft['issues']: st.error('\n'.join(draft['issues']))
            c1,c2=st.columns(2)
            with c1:
                if st.button('Approve storyboard',type='primary'):
                    pid,path=DraftService(DB).approve(draft_id,OUT/'storyboard.json'); st.session_state['project_id']=pid; st.success(f'Approved: {path}')
            with c2:
                if st.button('Reject draft'):
                    DraftService(DB).reject(draft_id,'Rejected by reviewer; revise the storyboard before approval.'); st.warning('Draft rejected')
        except Exception as e: st.error(str(e))
with tabs[2]:
    st.subheader('Generate production assets')
    sb_path=st.text_input('Approved storyboard path',str(OUT/'storyboard.json'))
    if st.button('Generate character references and keyframes',type='primary'):
        try:
            sb=load_storyboard(sb_path); pipe=ProductionPipeline(OUT,ProviderRegistry(),ROOT/'runs.jsonl')
            refs=pipe.generate_character_references(sb); frames=pipe.generate_keyframes(sb)
            st.session_state['keyframes']=[str(x) for x in frames]
            st.success(f'Generated {len(refs)} character references and {len(frames)} keyframes.')
        except Exception as e: st.error(str(e))
    frames=st.session_state.get('keyframes',[])
    if not frames:
        frames=[str(p) for p in sorted((OUT/'keyframes').glob('s*.png'))]
    if frames:
        st.markdown('**Review the keyframes before spending GPU time on video.**')
        cols=st.columns(2)
        for i,frame in enumerate(frames):
            with cols[i%2]: st.image(frame,caption=Path(frame).name,use_container_width=True)
        reviewer=st.text_input('Keyframe reviewer')
        if st.button('Approve these keyframes'):
            try:
                sb=load_storyboard(sb_path); approval=ProductionPipeline(OUT,ProviderRegistry(),ROOT/'runs.jsonl').approve_keyframes(sb,reviewer)
                st.success(f'Keyframes approved: {approval}')
            except Exception as e: st.error(str(e))
        if st.button('Generate moving video clips'):
            try:
                sb=load_storyboard(sb_path); clips=ProductionPipeline(OUT,ProviderRegistry(),ROOT/'runs.jsonl').generate_clips(sb)
                st.success(f'Generated or resumed {len(clips)} clips.')
            except Exception as e: st.error(str(e))
    if st.button('Generate narration and score automatically',type='primary'):
        try:
            sb=load_storyboard(sb_path); pipe=ProductionPipeline(OUT,ProviderRegistry(),ROOT/'runs.jsonl')
            narration=pipe.generate_narration(sb); st.session_state['narration_files']=[str(x) for x in narration]
            candidates=pipe.generate_music(sb)
            decision=auto_select_music_candidate(sb_path,candidates,log_path=ROOT/'runs.jsonl')
            st.session_state['selected_music_path']=decision['selected']
            st.success('Narration generated. Music candidates were scored and the best technical candidate was selected automatically.')
            st.write('Automatic music selection rationale:',decision['rationale'])
            st.json(decision['ranking'])
        except Exception as e: st.error(str(e))
with tabs[3]:
    st.subheader('Assemble dual-format film')
    sb_for_music=load_storyboard(OUT/'storyboard.json') if (OUT/'storyboard.json').exists() else None
    selected_music=(sb_for_music.music.selected if sb_for_music else None)
    music_path=Path(selected_music) if selected_music else None
    st.write('Automatically selected score:',str(music_path) if music_path else 'Not generated yet')
    if st.button('Assemble horizontal and vertical MP4',type='primary'):
        try:
            sb=load_storyboard(OUT/'storyboard.json'); paths=FilmAssembler(OUT).assemble(sb,music=Path(sb.music.selected) if sb.music.selected else None,registry_path=ROOT/'consent_registry.json',licenses_path=ROOT/'model_licenses.json',narration_review_path=OUT/'narration_review.json'); st.success('Assembly complete'); st.json({k:str(v) for k,v in paths.items()})
        except Exception as e: st.error(str(e))
with tabs[4]:
    st.subheader('Consent, narration, license and final quality gates')
    st.caption('A fluent Amharic/native-language reviewer must listen to every narration line before release.')
    sb_path=OUT/'storyboard.json'
    narration_files=st.session_state.get('narration_files',[str(p) for p in sorted((OUT/'narration').glob('s*.wav'))])
    for audio_path in narration_files:
        if Path(audio_path).exists():
            st.write(Path(audio_path).name); st.audio(str(audio_path))
    narration_root=OUT/'narration'
    if st.button('Run automatic narration checks'):
        try:
            sb=load_storyboard(sb_path); report=audit_narration_assets(sb,narration_root,OUT/'narration_review.json')
            try:
                audit_narration_with_gemini(sb,narration_root,OUT/'narration_review.json',log_path=ROOT/'runs.jsonl')
                report=json.loads((OUT/'narration_review.json').read_text(encoding='utf-8'))
            except Exception as audit_error:
                st.warning(f'Gemini pronunciation/translation screening could not complete: {audit_error}')
            st.session_state['narration_audit']=report
            if report.get('gemini_audio_audit',{}).get('completed'):
                st.success('Technical narration checks and Gemini audio/translation screening completed.')
            else:
                st.success('Technical narration checks completed; Gemini audio screening is unavailable or incomplete.')
        except Exception as e: st.error(str(e))
    report=st.session_state.get('narration_audit')
    if report is None and (OUT/'narration_review.json').exists():
        report=json.loads((OUT/'narration_review.json').read_text(encoding='utf-8'))
    if report:
        st.write('Automated technical audit:', 'passed' if report.get('automated_checks_passed') else 'issues found')
        st.write(report.get('notes',''))
        if report.get('issues'): st.warning('\n'.join(report['issues']))
        if report.get('gemini_audio_audit'):
            st.subheader('Gemini audio, pronunciation and subtitle screening')
            st.write(report['gemini_audio_audit'].get('summary',''))
            st.json(report['gemini_audio_audit'].get('shots',[]))
    st.info('Human attestation remains required: a fluent native speaker must listen to every line and confirm pronunciation, meaning and subtitle accuracy. The system cannot honestly self-certify this.')
    reviewer=st.text_input('Native-speaker reviewer (required for release)')
    approved=st.checkbox('I listened to every narration line and approve pronunciation, meaning and English subtitles')
    if st.button('Record native-speaker approval'):
        try:
            result=approve_native_review(OUT/'narration_review.json',reviewer,approved)
            st.session_state['narration_audit']=result; st.success('Native-speaker approval recorded.')
        except Exception as e: st.error(str(e))
    st.caption('Release is blocked until real-person consent records and exact model/output licenses are reviewed.')
    st.code('consent_registry.json\nmodel_licenses.json')
    if st.button('Run release gate and final QC'):
        try:
            sb=load_storyboard(sb_path); gate=check_release_gates(sb,ROOT/'consent_registry.json',licenses_path=ROOT/'model_licenses.json',narration_review_path=OUT/'narration_review.json')
            qc=final_quality_check({'horizontal':OUT/'assembly'/'horizontal.mp4','vertical':OUT/'assembly'/'vertical.mp4'})
            (OUT/'final_qc.json').write_text(json.dumps(qc,indent=2),encoding='utf-8')
            st.success('Release gates passed'); st.json({'release':gate,'quality':qc})
        except Exception as e: st.error(str(e))
