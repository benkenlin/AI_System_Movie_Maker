from __future__ import annotations
import json, shutil, subprocess, time, hashlib
from pathlib import Path
from typing import Any
from .models import Storyboard
from .providers import ProviderRegistry, ProviderError
from .observability import log_model_call
from .music import build_cue_aware_prompt, default_music_cues

class ProductionError(RuntimeError): pass

class ProductionPipeline:
    """Resumable per-shot media workers; successful artifacts are checkpoints."""
    def __init__(self,root:str|Path='outputs',registry:ProviderRegistry|None=None,log_path:str|Path='runs.jsonl',max_retries:int=2):
        self.root=Path(root); self.registry=registry or ProviderRegistry(); self.log_path=Path(log_path); self.max_retries=max_retries
    def _run(self,stage:str,provider:str,model:str,inputs:dict[str,Any],dest:Path,fn):
        digest=hashlib.sha256(json.dumps({'stage':stage,'provider':provider,'model':model,'inputs':inputs},sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        sidecar=dest.with_suffix(dest.suffix+'.meta.json')
        if dest.exists() and dest.stat().st_size>0 and sidecar.exists():
            try:
                if json.loads(sidecar.read_text()).get('input_hash')==digest: return dest
            except Exception: pass
        error=None
        for attempt in range(self.max_retries+1):
            try:
                result=log_model_call(self.log_path,stage=stage,provider=provider,model=model,inputs=inputs,output=dest,call=fn,attempt=attempt)
                sidecar.write_text(json.dumps({'input_hash':digest,'stage':stage,'provider':provider,'model':model},indent=2),encoding='utf-8')
                return result
            except Exception as exc:
                error=exc
                if attempt<self.max_retries: time.sleep(min(2**attempt,8))
        raise ProductionError(f'{stage} failed after {self.max_retries+1} attempts: {error}') from error
    def generate_character_references(self,storyboard:Storyboard)->dict[str,Path]:
        provider=self.registry.image(); refs={}
        for character_id,character in storyboard.characters.items():
            dest=self.root/'refs'/f'{character_id}.png'
            prompt=f"{storyboard.style.block}\nCreate a clean cinematic character anchor portrait on a neutral background. Fictional character only. {character.descriptor}. Full face and clothing details, no text."
            refs[character_id]=self._run('character_reference',type(provider).__name__,self.registry.config.cloudflare_image_model,{'character_id':character_id,'prompt':prompt},dest,lambda p=prompt,d=dest:provider.generate(p,d,width=448,height=448))
        return refs

    def generate_keyframes(self,storyboard:Storyboard)->list[Path]:
        provider=self.registry.image(); out=[]; refs=self.generate_character_references(storyboard)
        for shot in storyboard.shots:
            dest=self.root/'keyframes'/f'{shot.id}.png'
            prompt=f"{storyboard.style.block}\n{shot.image_prompt}\nCharacters: " + '; '.join(storyboard.characters[c].descriptor for c in shot.characters)
            shot_refs=[refs[c] for c in shot.characters if c in refs]
            if shot_refs:
                reference_notes = [f"image {i} is {character_id}: {storyboard.characters[character_id].descriptor}" for i, character_id in enumerate(shot.characters) if character_id in refs]
                prompt += "\nUse these visual identity references: " + "; ".join(reference_notes) + ". Preserve face, hair, age, and clothing."
            inputs={'prompt':prompt,'seed':shot.seed,'reference_images':[str(x) for x in shot_refs],'reference_sha256':[hashlib.sha256(x.read_bytes()).hexdigest() for x in shot_refs]}
            out.append(self._run('keyframe',type(provider).__name__,self.registry.config.cloudflare_image_model,inputs,dest,lambda p=prompt,d=dest,s=shot.seed,r=shot_refs:provider.generate(p,d,seed=s,reference_images=r,width=1280,height=720)))
        return out

    def approve_keyframes(self,storyboard:Storyboard,reviewer:str)->Path:
        if not reviewer.strip(): raise ProductionError('A reviewer name is required to approve keyframes')
        hashes={}
        for shot in storyboard.shots:
            path=self.root/'keyframes'/f'{shot.id}.png'
            if not path.exists(): raise ProductionError(f'Missing keyframe for {shot.id}')
            hashes[shot.id]=hashlib.sha256(path.read_bytes()).hexdigest()
        approval=self.root/'keyframes'/'approval.json'; approval.parent.mkdir(parents=True,exist_ok=True)
        approval.write_text(json.dumps({'reviewer':reviewer.strip(),'approved_at':time.time(),'hashes':hashes},indent=2),encoding='utf-8')
        return approval
    def generate_clips(self,storyboard:Storyboard)->list[Path]:
        approval=self.root/'keyframes'/'approval.json'
        if not approval.exists(): raise ProductionError('Human keyframe approval is required before video generation')
        approved=json.loads(approval.read_text(encoding='utf-8')).get('hashes',{})
        for shot in storyboard.shots:
            frame=self.root/'keyframes'/f'{shot.id}.png'
            if not frame.exists() or approved.get(shot.id)!=hashlib.sha256(frame.read_bytes()).hexdigest(): raise ProductionError(f'Keyframe {shot.id} changed after approval; review and approve again')
        provider=self.registry.video(); out=[]
        for shot in storyboard.shots:
            keyframe=self.root/'keyframes'/f'{shot.id}.png'; dest=self.root/'clips'/f'{shot.id}.mp4'
            if not keyframe.exists(): raise ProductionError(f'Missing approved keyframe: {keyframe}')
            payload={'shot_id':shot.id,'image':str(keyframe),'keyframe_sha256':hashlib.sha256(keyframe.read_bytes()).hexdigest(),'motion_prompt':shot.motion_prompt,'duration_s':shot.duration_s,'seed':shot.seed,'checkpoint_dir':str(self.root/'checkpoints'/shot.id)}
            try: out.append(self._run('video',type(provider).__name__,'configured-worker',payload,dest,lambda p=payload,d=dest:provider.generate(p,d)))
            except ProductionError:
                # Explicit, documented fallback: create a Ken Burns clip from the approved still.
                fallback=self.root/'clips'/f'{shot.id}_fallback.mp4'; self._ken_burns(keyframe,fallback,shot.duration_s)
                out.append(fallback)
        return out
    def generate_music(self,storyboard:Storyboard)->list[Path]:
        provider=self.registry.music(); candidates=[]
        music_prompt=build_cue_aware_prompt(storyboard)
        for i in range(3):
            dest=self.root/'music'/f'candidate_{i+1}.wav'; payload={'prompt':music_prompt,'instrumental':storyboard.music.instrumental,'duration_s':storyboard.music.duration_s,'candidate':i+1,'seed':1000+i,'music_cues':[c.model_dump() for c in storyboard.music.cues] if storyboard.music.cues else default_music_cues(storyboard.shots)}
            candidates.append(self._run('music',type(provider).__name__,'configured-worker',payload,dest,lambda p=payload,d=dest:provider.generate(p,d)))
        return candidates
    def generate_narration(self,storyboard:Storyboard)->list[Path]:
        # Any TTS run invalidates prior human approval and final exports.
        review=self.root/'narration_review.json'
        if review.exists(): review.unlink()
        for stale in (self.root/'assembly'/'horizontal.mp4',self.root/'assembly'/'vertical.mp4',self.root/'final_qc.json'):
            if stale.exists(): stale.unlink()
        provider=self.registry.speech(); voice=storyboard.narration_voice.voice or self.registry.config.gemini_tts_voice; model=storyboard.narration_voice.model or self.registry.config.gemini_tts_model; out=[]
        for shot in storyboard.shots:
            dest=self.root/'narration'/f'{shot.id}.wav'; text=shot.narration.text
            out.append(self._run('narration',type(provider).__name__,model,{'text':text,'language':shot.narration.lang,'voice':voice,'lexicon':shot.narration.lexicon},dest,lambda t=text,d=dest,s=shot:provider.synthesize(t,s.narration.lang,d,voice=voice,lexicon=s.narration.lexicon,model=model,style_prompt=storyboard.narration_voice.style_prompt or self.registry.config.gemini_tts_style)))
        return out
    @staticmethod
    def _ken_burns(image:Path,dest:Path,duration:float):
        if not shutil.which('ffmpeg'): raise ProductionError('ffmpeg is required for Ken Burns fallback')
        dest.parent.mkdir(parents=True,exist_ok=True)
        cmd=['ffmpeg','-y','-loop','1','-i',str(image),'-t',str(duration),'-vf',f"scale=1920:1080,zoompan=z='min(zoom+0.0005,1.08)':d=1:s=1920x1080:fps=24,format=yuv420p",'-an','-c:v','libx264','-pix_fmt','yuv420p',str(dest)]
        subprocess.run(cmd,capture_output=True,text=True,check=True)
