"""Provider contracts and concrete HTTP/local adapters. Secrets are read only from env."""
from __future__ import annotations
import base64, json, os, subprocess, time, wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class ProviderError(RuntimeError): pass

@dataclass
class ProviderConfig:
    image_provider: str = 'cloudflare'
    cloudflare_account_id: str = ''
    cloudflare_token: str = ''
    cloudflare_image_model: str = '@cf/black-forest-labs/flux-2-klein-9b'
    gemini_api_key: str = ''
    gemini_tts_model: str = 'gemini-3.8-flash-tts'
    gemini_tts_voice: str = 'Kore'
    gemini_tts_style: str = 'Warm, clear, natural documentary narration; measured pace and gentle emotional restraint.'
    video_command: str = ''
    video_worker_url: str = ''
    video_worker_token: str = ''
    music_command: str = 'python scripts/local_music_worker.py --input {input_json} --output {output}'
    output_dir: str = 'outputs'
    request_timeout_s: int = 180

    @classmethod
    def from_env(cls) -> 'ProviderConfig':
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        return cls(
            image_provider=os.getenv('IMAGE_PROVIDER','cloudflare'),
            cloudflare_account_id=os.getenv('CLOUDFLARE_ACCOUNT_ID',''),
            cloudflare_token=os.getenv('CLOUDFLARE_API_TOKEN',''),
            cloudflare_image_model=os.getenv('CLOUDFLARE_IMAGE_MODEL','@cf/black-forest-labs/flux-2-klein-9b'),
            gemini_api_key=os.getenv('GEMINI_API_KEY',''),
            gemini_tts_model=os.getenv('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'),
            gemini_tts_voice=os.getenv('GEMINI_TTS_VOICE','Kore'),
            gemini_tts_style=os.getenv('GEMINI_TTS_STYLE','Warm, clear, natural documentary narration; measured pace and gentle emotional restraint.'),
            video_command=os.getenv('VIDEO_GENERATION_COMMAND',''),
            video_worker_url=os.getenv('VIDEO_WORKER_URL',''),
            video_worker_token=os.getenv('VIDEO_WORKER_TOKEN',''),
            music_command=os.getenv('MUSIC_GENERATION_COMMAND',''),
            output_dir=os.getenv('AI_CONTENT_OUTPUT_DIR','outputs'),
            request_timeout_s=int(os.getenv('PROVIDER_TIMEOUT_S','180')))

class ImageProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, destination: Path, *, seed: int | None = None, reference_images: list[Path] | None = None, width:int=1024, height:int=768) -> Path: ...
class SpeechProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, language: str, destination: Path, *, voice: str, lexicon: dict[str,str] | None=None, model: str | None=None) -> Path: ...
class MediaGenerationProvider(ABC):
    @abstractmethod
    def generate(self, payload: dict[str,Any], destination: Path) -> Path: ...

def _post_json(url: str, payload: dict, headers: dict[str,str], timeout: int) -> dict:
    data=json.dumps(payload).encode()
    req=Request(url,data=data,headers={'Content-Type':'application/json',**headers},method='POST')
    try:
        with urlopen(req,timeout=timeout) as response: return json.loads(response.read())
    except (HTTPError,URLError,TimeoutError) as exc:
        detail=''
        if isinstance(exc,HTTPError):
            try: detail=exc.read().decode(errors='replace')[:1000]
            except Exception: pass
        raise ProviderError(f'Provider request failed: {exc}. {detail}') from exc

def _post_multipart(url:str,fields:dict[str,str],files:list[tuple[str,Path]],headers:dict[str,str],timeout:int)->bytes:
    import uuid
    boundary='----ai-film-'+uuid.uuid4().hex
    chunks=[]
    for name,value in fields.items():
        chunks.extend([f'--{boundary}\r\n'.encode(),f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),str(value).encode(),b'\r\n'])
    for name,path in files:
        mime='image/png' if path.suffix.lower()=='.png' else 'image/jpeg'
        chunks.extend([f'--{boundary}\r\n'.encode(),f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode(),f'Content-Type: {mime}\r\n\r\n'.encode(),path.read_bytes(),b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    req=Request(url,data=b''.join(chunks),headers={'Content-Type':f'multipart/form-data; boundary={boundary}',**headers},method='POST')
    try:
        with urlopen(req,timeout=timeout) as response: return response.read()
    except (HTTPError,URLError,TimeoutError) as exc:
        detail=''
        if isinstance(exc,HTTPError):
            try: detail=exc.read().decode(errors='replace')[:1000]
            except Exception: pass
        raise ProviderError(f'Provider request failed: {exc}. {detail}') from exc

class CloudflareImageProvider(ImageProvider):
    def __init__(self, config: ProviderConfig): self.c=config
    def generate(self,prompt:str,destination:Path,*,seed:int|None=None,reference_images:list[Path]|None=None,width:int=1024,height:int=768)->Path:
        if not self.c.cloudflare_account_id or not self.c.cloudflare_token:
            raise ProviderError('Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN')
        url=f'https://api.cloudflare.com/client/v4/accounts/{self.c.cloudflare_account_id}/ai/run/{self.c.cloudflare_image_model}'
        fields={'prompt':prompt,'width':str(width),'height':str(height)}
        if seed is not None: fields['seed']=str(seed)
        files=[]
        for index,reference in enumerate((reference_images or [])[:4]):
            ref=Path(reference)
            if not ref.exists(): raise ProviderError(f'Reference image not found: {ref}')
            files.append((f'input_image_{index}',ref))
        raw=_post_multipart(url,fields,files,{'Authorization':f'Bearer {self.c.cloudflare_token}'},self.c.request_timeout_s)
        try:
            result=json.loads(raw)
            if result.get('success') is False: raise ProviderError(f'Cloudflare image generation failed: {result.get("errors",result)}')
            encoded=result.get('result',{}).get('image') or result.get('result',{}).get('data')
            if isinstance(encoded,list): encoded=encoded[0] if encoded else None
            if not encoded: raise ProviderError(f'Image provider returned no image: {str(result)[:500]}')
            if encoded.startswith('data:'): encoded=encoded.split(',',1)[1]
            image_bytes=base64.b64decode(encoded)
        except (json.JSONDecodeError,UnicodeDecodeError):
            # Some Workers AI deployments return the image bytes directly.
            image_bytes=raw
        if not image_bytes: raise ProviderError('Image provider returned an empty image')
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(image_bytes)
        return destination

class GeminiTTSProvider(SpeechProvider):
    def __init__(self,config:ProviderConfig): self.c=config
    def synthesize(self,text:str,language:str,destination:Path,*,voice:str,lexicon:dict[str,str]|None=None,model:str|None=None,style_prompt:str|None=None)->Path:
        if not self.c.gemini_api_key: raise ProviderError('Set GEMINI_API_KEY')
        spoken=text
        for term,pronunciation in (lexicon or {}).items():
            # Inline pronunciation hints without changing the visible subtitle text.
            spoken=spoken.replace(term,pronunciation)
        target_model=model or self.c.gemini_tts_model
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent'
        style=style_prompt or self.c.gemini_tts_style
        part_obj={'text':spoken}
        if target_model.endswith('-tts') and style:
            part_obj['speechMetadata']={'style':style}
        voice_name=voice or self.c.gemini_tts_voice
        speech_cfg={'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':voice_name}}}
        if language:
            speech_cfg['languageCode']=language
        payload={'contents':[{'role':'user','parts':[part_obj]}],
                 'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':speech_cfg}}
        result=_post_json(url,payload,{'x-goog-api-key':self.c.gemini_api_key},self.c.request_timeout_s)
        try:
            part=result['candidates'][0]['content']['parts'][0]['inlineData']
            audio=base64.b64decode(part['data']); mime=part.get('mimeType','audio/wav')
        except (KeyError,IndexError,TypeError) as exc: raise ProviderError(f'TTS response contained no audio: {str(result)[:500]}') from exc
        destination.parent.mkdir(parents=True,exist_ok=True)
        if mime.startswith(('audio/pcm','audio/l16')):
            # Gemini raw PCM is signed 16-bit mono; parse the advertised rate when present.
            import re
            match=re.search(r'rate[=\s](\d+)',mime)
            sample_rate=int(match.group(1)) if match else 24000
            with wave.open(str(destination),'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate); wf.writeframes(audio)
        else: destination.write_bytes(audio)
        return destination

class CommandMediaProvider(MediaGenerationProvider):
    """Runs a local/Kaggle worker command. Use {input_json} and {output} placeholders."""
    def __init__(self,command:str,timeout:int=3600): self.command=command; self.timeout=timeout
    def generate(self,payload:dict[str,Any],destination:Path)->Path:
        if not self.command: raise ProviderError('Worker command is not configured')
        import shlex, tempfile
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ai-film-worker-') as td:
            inp=Path(td)/'input.json'; inp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            argv=[x.replace('{input_json}',str(inp)).replace('{output}',str(destination)) for x in shlex.split(self.command)]
            try: proc=subprocess.run(argv,capture_output=True,text=True,timeout=self.timeout,check=False)
            except (OSError,subprocess.TimeoutExpired) as exc: raise ProviderError(f'Worker execution failed: {exc}') from exc
            if proc.returncode: raise ProviderError(f'Worker exited {proc.returncode}: {proc.stderr[-2000:]}')
        if not destination.exists(): raise ProviderError('Worker completed but did not create its output file')
        return destination


class HTTPVideoProvider(MediaGenerationProvider):
    """Uploads a keyframe to a remote authenticated Wan worker and downloads MP4."""
    def __init__(self, base_url: str, token: str = '', timeout: int = 7200):
        self.base_url=base_url.rstrip('/'); self.token=token; self.timeout=timeout
    def generate(self,payload:dict[str,Any],destination:Path)->Path:
        import uuid
        image=Path(payload.get('image',''))
        if not image.exists(): raise ProviderError(f'Video keyframe does not exist: {image}')
        boundary='----ai-video-'+uuid.uuid4().hex
        meta={k:v for k,v in payload.items() if k!='image'}
        chunks=[f'--{boundary}\r\nContent-Disposition: form-data; name="payload"\r\n\r\n'.encode(),json.dumps(meta).encode(),b'\r\n',
                f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{image.name}"\r\nContent-Type: image/png\r\n\r\n'.encode(),image.read_bytes(),b'\r\n',f'--{boundary}--\r\n'.encode()]
        headers={'Content-Type':f'multipart/form-data; boundary={boundary}'}
        if self.token: headers['Authorization']=f'Bearer {self.token}'
        req=Request(self.base_url+'/generate',data=b''.join(chunks),headers=headers,method='POST')
        try:
            with urlopen(req,timeout=self.timeout) as r: video=r.read()
        except (HTTPError,URLError,TimeoutError) as exc:
            detail=''
            if isinstance(exc,HTTPError):
                try: detail=exc.read().decode(errors='replace')[:1500]
                except Exception: pass
            raise ProviderError(f'Remote Wan worker failed: {exc}. {detail}') from exc
        if not video or len(video)<100_000:
            raise ProviderError('Remote Wan worker returned an empty/invalid MP4')
        destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(video); return destination

class ProviderRegistry:
    def __init__(self,config:ProviderConfig|None=None): self.config=config or ProviderConfig.from_env()
    def image(self)->ImageProvider:
        if self.config.image_provider=='cloudflare': return CloudflareImageProvider(self.config)
        raise ProviderError(f'Unsupported image provider: {self.config.image_provider}')
    def speech(self)->SpeechProvider: return GeminiTTSProvider(self.config)
    def video(self)->MediaGenerationProvider:
        if self.config.video_worker_url: return HTTPVideoProvider(self.config.video_worker_url,self.config.video_worker_token,timeout=int(os.getenv('VIDEO_WORKER_TIMEOUT_S','7200')))
        return CommandMediaProvider(self.config.video_command,timeout=int(os.getenv('VIDEO_WORKER_TIMEOUT_S','7200')))
    def music(self)->MediaGenerationProvider: return CommandMediaProvider(self.config.music_command)

class GeminiTextPlanner:
    """Structured JSON storyboard planner using Gemini's generateContent API."""
    name='gemini-text-planner'
    def __init__(self,config:ProviderConfig): self.c=config
    def plan(self,idea:str,*,title:str,language:str,subtitle_language:str)->dict[str,Any]:
        if not self.c.gemini_api_key: raise ProviderError('Set GEMINI_API_KEY')
        prompt=("Create a production storyboard as JSON only. Return an object with schema_version='1.0', "
          "storyboard_version=1, title, logline, language, subtitle_language, target_runtime_s, shot_count, "
          "aspect_ratios=['16:9','9:16'], style:{block}, narration_voice:{model,voice}, characters, music, "
          "ai_disclosure:{in_film:true,end_card_text}, and 8-12 sequential shots. Each shot needs id s01..., "
          "duration_s, image_prompt, motion_prompt, camera, characters, vertical_crop_x, narration:{text,lang,lexicon}, "
          "subtitle_en, transition. Use fictional characters, no real-person likenesses. Make total duration 60-90s, "
          "Amharic narration when requested, accurate concise English subtitles, and instrumental music. Music must include 3-5 timed cues tied to valid shot IDs (fade_in, swell, drop, fade_out), with notes that track the emotional arc. Keep music instrumental with no lyrics or vocals.\n"
          f"Title: {title}\nNarration language: {language}\nSubtitle language: {subtitle_language}\nIdea: {idea}")
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{os.getenv("GEMINI_TEXT_MODEL","gemini-3.8-flash-tts")}:generateContent'
        from .observability import log_model_call
        result=log_model_call(Path(self.c.output_dir).parent/'runs.jsonl',stage='story_planning',provider='Google Gemini',model=os.getenv('GEMINI_TEXT_MODEL','gemini-3.8-flash'),inputs={'idea':idea,'title':title,'language':language,'subtitle_language':subtitle_language},output=None,call=lambda:_post_json(url,{'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json'}},{'x-goog-api-key':self.c.gemini_api_key},self.c.request_timeout_s))
        try:
            raw=result['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw[raw.find('{'):raw.rfind('}')+1])
        except Exception as exc: raise ProviderError(f'Gemini did not return valid storyboard JSON: {str(result)[:1000]}') from exc
    def repair(self,storyboard:dict,issues:list[str],*,idea:str)->dict[str,Any]:
        if not self.c.gemini_api_key: raise ProviderError('Set GEMINI_API_KEY')
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{os.getenv("GEMINI_TEXT_MODEL","gemini-3.8-flash-tts")}:generateContent'
        prompt='Repair this storyboard JSON. Fix only these validation issues and preserve all other content. Return JSON only.\nIssues:'+json.dumps(issues)+'\nStoryboard:'+json.dumps(storyboard,ensure_ascii=False)
        from .observability import log_model_call
        result=log_model_call(Path(self.c.output_dir).parent/'runs.jsonl',stage='story_repair',provider='Google Gemini',model=os.getenv('GEMINI_TEXT_MODEL','gemini-3.8-flash'),inputs={'issues':issues,'storyboard':storyboard},output=None,call=lambda:_post_json(url,{'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json'}},{'x-goog-api-key':self.c.gemini_api_key},self.c.request_timeout_s))
        raw=result['candidates'][0]['content']['parts'][0]['text']; return json.loads(raw[raw.find('{'):raw.rfind('}')+1])
