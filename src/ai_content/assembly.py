from __future__ import annotations
import json, shutil, subprocess, tempfile
from pathlib import Path
from .models import Storyboard
from .ethics import check_release_gates

class AssemblyError(RuntimeError): pass

def _run(cmd:list[str]):
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode: raise AssemblyError(f"Command failed: {' '.join(cmd[:5])}\n{p.stderr[-2500:]}")

def _probe(path:Path)->dict:
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(path)],capture_output=True,text=True)
    if p.returncode: raise AssemblyError(f'ffprobe failed for {path}: {p.stderr[-1000:]}')
    return json.loads(p.stdout)

def _srt_time(seconds:float)->str:
    ms=round(seconds*1000); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

class FilmAssembler:
    TRANSITION_SECONDS=0.4
    def __init__(self,root:str|Path='outputs',*,width:int=1280,height:int=720):
        if width<=height or width%2 or height%2 or width*9!=height*16: raise ValueError('horizontal export dimensions must be even and exactly 16:9')
        self.root=Path(root); self.width=width; self.height=height; self.vertical_height=((width*16//9)+1)//2*2; self.subtitle_scale=max(8,int(width/37.6))
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): raise AssemblyError('FFmpeg and ffprobe must be installed and on PATH')
    def assemble(self,storyboard:Storyboard,*,music:Path|None=None,release_check:bool=True,registry_path:str|Path='consent_registry.json',licenses_path:str|Path='model_licenses.json',narration_review_path:str|Path='narration_review.json')->dict[str,Path]:
        if release_check: check_release_gates(storyboard,registry_path,licenses_path=licenses_path,narration_review_path=narration_review_path)
        clips=self.root/'clips'; narration=self.root/'narration'; assembled=self.root/'assembly'; assembled.mkdir(parents=True,exist_ok=True)
        srt=assembled/'subtitles_en.srt'; entries=[]; cursor=0.0; segment_durations=[]
        end_card=assembled/'ai_disclosure.txt'; end_card.write_text(storyboard.ai_disclosure.end_card_text.replace(':','\\:'),encoding='utf-8')
        with tempfile.TemporaryDirectory(prefix='film-assembly-') as td:
            normalized=[]; vertical=[]
            for shot in storyboard.shots:
                clip=clips/f'{shot.id}.mp4'
                if not clip.exists(): clip=clips/f'{shot.id}_fallback.mp4'
                voice=narration/f'{shot.id}.wav'
                if not clip.exists() or not voice.exists(): raise AssemblyError(f'Missing media for {shot.id}: clip={clip.exists()}, narration={voice.exists()}')
                voice_duration=float(_probe(voice)['format']['duration']); duration=max(shot.duration_s,voice_duration)
                subtitle=shot.subtitle_en or shot.narration.subtitle_text or shot.narration.text
                entries.append(f'{len(entries)+1}\n{_srt_time(cursor)} --> {_srt_time(cursor+duration)}\n{subtitle}\n')
                cursor+=duration; segment_durations.append(duration)
                tailpad=self.TRANSITION_SECONDS if len(segment_durations)<len(storyboard.shots) and storyboard.shots[len(segment_durations)].transition!='cut' else 0.0
                segment_total=duration+tailpad
                base=Path(td)/f'{shot.id}_base.mp4'
                _run(['ffmpeg','-y','-i',str(clip),'-vf',f'scale={self.width}:{self.height}:force_original_aspect_ratio=increase,crop={self.width}:{self.height},setsar=1,fps=24,tpad=stop_mode=clone:stop_duration={segment_total},format=yuv420p','-t',str(segment_total),'-an','-c:v','libx264','-preset','ultrafast',str(base)])
                normalized.append(base)
                # Per-shot vertical crop uses the storyboard's horizontal focal point.
                v=Path(td)/f'{shot.id}_vertical.mp4'; x=shot.vertical_crop_x
                vf=f"scale=-2:{self.width}:force_original_aspect_ratio=increase,crop={self.height}:{self.width}:x='max(0,min(iw-{self.height},(iw-{self.height})*{x}))':y=0,setsar=1,fps=24,tpad=stop_mode=clone:stop_duration={segment_total},format=yuv420p"
                _run(['ffmpeg','-y','-i',str(clip),'-vf',vf,'-t',str(segment_total),'-an','-c:v','libx264','-preset','ultrafast',str(v)])
                vertical.append(v)
            srt.write_text('\n'.join(entries),encoding='utf-8')
            # Narration track: concatenate per-shot voice tracks with silence to align to shot durations.
            voice_list=Path(td)/'voice.txt'; voice_parts=[]
            for shot in storyboard.shots:
                src=narration/f'{shot.id}.wav'; d=float(_probe(src)['format']['duration']); target=max(shot.duration_s,d)
                part=Path(td)/f'{shot.id}_voice.wav'
                _run(['ffmpeg','-y','-i',str(src),'-af',f'apad=pad_dur={max(0,target-d)}','-t',str(target),'-ar','48000','-ac','2',str(part)])
                voice_parts.append(part)
            def concat(parts: list[Path], output:Path):
                listing=Path(td)/(output.stem+'_list.txt'); listing.write_text(''.join(f"file '{p.as_posix()}'\n" for p in parts),encoding='utf-8')
                _run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(output)])
            hvideo=Path(td)/'horizontal.mp4'; vvideo=Path(td)/'vertical.mp4'
            self._join_video(normalized,storyboard.shots,segment_durations,hvideo)
            self._join_video(vertical,storyboard.shots,segment_durations,vvideo)
            voice=Path(td)/'voice.wav'; concat(voice_parts,voice)
            outputs={}
            for label,video,subtitle_style in [('horizontal',hvideo,f'Alignment=2,FontSize={max(8, int(self.subtitle_scale * 0.78))},MarginV={max(10, int(self.subtitle_scale * 0.55))}'),('vertical',vvideo,f'FontSize={max(8,int(self.subtitle_scale*.82))},MarginV={max(20,self.subtitle_scale*2)}')]:
                out=assembled/f'{label}.mp4'; subtitle_filter=f"subtitles={srt.as_posix()}:force_style='{subtitle_style}',tpad=stop_mode=clone:stop_duration=3,drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,{cursor})',drawtext=textfile={end_card.as_posix()}:fontcolor=white:fontsize={self.subtitle_scale}:x=(w-text_w)/2:y=(h-text_h)/2:enable='gte(t,{cursor})'"
                if music and music.exists():
                    _run(['ffmpeg','-y','-i',str(video),'-i',str(voice),'-stream_loop','-1','-i',str(music),'-filter_complex',f"[2:a]volume=1.4[m];[m][1:a]sidechaincompress=threshold=0.06:ratio=3.5:attack=30:release=400:makeup=1.2[duck];[1:a][duck]amix=inputs=2:duration=first:weights=1.0 1.25:normalize=0[mix];[mix]apad,loudnorm=I=-16:TP=-1.5:LRA=11[a]",'-vf',subtitle_filter,'-map','0:v','-map','[a]','-t',str(cursor+3),'-c:v','libx264','-preset','ultrafast','-c:a','aac','-movflags','+faststart',str(out)])
                else:
                    _run(['ffmpeg','-y','-i',str(video),'-i',str(voice),'-vf',subtitle_filter,'-map','0:v','-map','1:a','-t',str(cursor+3),'-c:v','libx264','-c:a','aac','-af','apad,loudnorm=I=-16:TP=-1.5:LRA=11','-movflags','+faststart',str(out)])
                outputs[label]=out
            return outputs


    def _join_video(self,parts:list[Path],shots:list,durations:list[float],output:Path)->None:
        current=parts[0]; running=durations[0]
        for i in range(1,len(parts)):
            next_part=parts[i]; transition=shots[i].transition
            stage_output=output.parent/f"{output.stem}_join_{i}.mp4"
            if transition=='cut':
                listing=output.parent/f"{output.stem}_join_{i}.txt"
                listing.write_text(f"file '{current.as_posix()}'\nfile '{next_part.as_posix()}'\n",encoding='utf-8')
                _run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(stage_output)])
            else:
                effect={'crossfade':'fade','fade':'fade','fade_black':'fadeblack'}[transition]
                graph=f'[0:v][1:v]xfade=transition={effect}:duration={self.TRANSITION_SECONDS}:offset={running},format=yuv420p[v]'
                _run(['ffmpeg','-y','-i',str(current),'-i',str(next_part),'-filter_complex',graph,'-map','[v]','-an','-r','24','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(stage_output)])
            current=stage_output; running+=durations[i]
        output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(current,output)


def final_quality_check(outputs:dict[str,Path])->dict:
    report={}
    for label,path in outputs.items():
        info=_probe(path); streams=info.get('streams',[]); video=next((s for s in streams if s.get('codec_type')=='video'),{})
        audio=any(s.get('codec_type')=='audio' for s in streams)
        duration=float(info['format']['duration']); width=int(video.get('width') or 0); height=int(video.get('height') or 0)
        ratio_ok=(width*9==height*16) if label=='horizontal' else (width*16==height*9)
        duration_ok=60 <= duration <= 93
        report[label]={'exists':path.exists(),'bytes':path.stat().st_size,'duration_s':duration,'width':width,'height':height,'has_audio':audio,'ratio_ok':ratio_ok,'duration_ok':duration_ok,'passed':audio and ratio_ok and duration_ok and path.stat().st_size>100_000}
    if set(outputs)!={'horizontal','vertical'}: raise AssemblyError('Both horizontal and vertical exports are required')
    base=next(iter(outputs.values())).parent
    subtitles=(base/'subtitles_en.srt').exists() and (base/'subtitles_en.srt').stat().st_size>0
    disclosure=(base/'ai_disclosure.txt').exists() and (base/'ai_disclosure.txt').stat().st_size>0
    for item in report.values(): item['subtitles_file_present']=subtitles; item['ai_disclosure_source_present']=disclosure; item['passed']=item['passed'] and subtitles and disclosure
    if not all(x['passed'] for x in report.values()): raise AssemblyError(f'Final QC failed: {report}')
    return report
