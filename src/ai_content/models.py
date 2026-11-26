from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class AIDisclosure(StrictModel):
    in_film: Literal[True]
    end_card_text: str = Field(min_length=5, max_length=240)

class Character(StrictModel):
    descriptor: str = Field(min_length=20, max_length=1200)
    ref_sheet: str | None = None
    origin: Literal['fictional', 'consented_real', 'real']
    consent_id: str | None = None
    consent_record: str | None = None

    @model_validator(mode='after')
    def require_consent(self):
        if self.origin in {'real', 'consented_real'} and not (self.consent_id or self.consent_record):
            raise ValueError('real-person characters require consent_id or consent_record')
        return self

class MusicCue(StrictModel):
    at_shot: str = Field(pattern=r'^s[0-9]{2}$')
    action: Literal['fade_in','swell','drop','fade_out']
    note: str | None = None

class Music(StrictModel):
    prompt: str = Field(min_length=20, max_length=2000)
    instrumental: bool
    duration_s: float = Field(ge=10, le=600)
    candidates: list[str] = Field(default_factory=list)
    selected: str | None = None
    rationale: str = ''
    cues: list[MusicCue] = Field(default_factory=list)

    @model_validator(mode='after')
    def selected_candidate_must_exist(self):
        if self.selected is not None and self.selected not in self.candidates:
            raise ValueError('music.selected must match one item in music.candidates')
        if self.selected is not None and len(self.rationale.strip()) < 20:
            raise ValueError('music.rationale must explain the selection (at least 20 characters)')
        return self

class Narration(StrictModel):
    text: str = Field(min_length=1, max_length=3000)
    lang: str = Field(pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]+)?$')
    subtitle_text: str | None = Field(default=None, min_length=1, max_length=3000)
    lexicon: dict[str, str] = Field(default_factory=dict)

class Shot(StrictModel):
    id: str = Field(pattern=r'^s[0-9]{2}$')
    duration_s: float = Field(ge=3, le=30)
    image_prompt: str = Field(min_length=20, max_length=2000)
    motion_prompt: str = Field(min_length=10, max_length=1200)
    camera: Literal['static','push_in','pull_out','pan_left','pan_right','tilt_up','tilt_down']
    characters: list[str] = Field(default_factory=list, max_length=2)
    vertical_crop_x: float = Field(ge=0.0, le=1.0)
    seed: int | None = Field(default=None, ge=0)
    narration: Narration
    subtitle_en: str = Field(min_length=1, max_length=3000)
    transition: Literal['cut', 'crossfade', 'fade', 'fade_black']

    @model_validator(mode='after')
    def subtitle_present(self):
        if not (self.subtitle_en or self.narration.subtitle_text):
            raise ValueError('each shot requires English subtitle text (subtitle_en or narration.subtitle_text)')
        return self

class StyleConfig(StrictModel):
    block: str = Field(min_length=10, max_length=2000)
    negative: str | None = None

class NarrationVoice(StrictModel):
    model: str = Field(min_length=2, max_length=160)
    voice: str = Field(min_length=1, max_length=120)
    style_prompt: str | None = None

class Storyboard(StrictModel):
    schema_version: Literal['1.0']
    storyboard_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    logline: str = Field(min_length=20, max_length=500)
    language: str = Field(pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]+)?$')
    subtitle_language: str
    target_runtime_s: float = Field(ge=60, le=90)
    shot_count: int = Field(ge=8, le=12)
    aspect_ratios: list[Literal['16:9','9:16']]
    style: 'StyleConfig'
    narration_voice: 'NarrationVoice'
    ai_disclosure: AIDisclosure
    characters: dict[str, Character] = Field(min_length=1)
    music: Music
    shots: list[Shot] = Field(min_length=8, max_length=12)

    @field_validator('characters')
    @classmethod
    def character_keys_are_safe(cls, value):
        import re
        for key in value:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', key):
                raise ValueError('character keys must match ^[a-z][a-z0-9_]*$')
        return value

    @model_validator(mode='after')
    def validate_storyboard_relationships(self):
        if self.subtitle_language != 'en':
            raise ValueError('the delivery specification requires English subtitles')
        if set(self.aspect_ratios) != {'16:9','9:16'}:
            raise ValueError('both 16:9 and 9:16 aspect ratios are required')
        if self.shot_count != len(self.shots):
            raise ValueError('shot_count must equal the number of shots')
        ids = [s.id for s in self.shots]
        if len(ids) != len(set(ids)):
            raise ValueError('shot IDs must be unique')
        expected = [f's{i:02d}' for i in range(1, len(ids)+1)]
        if ids != expected:
            raise ValueError(f'shot IDs must be sequential: expected {expected}')
        known = set(self.characters)
        for shot in self.shots:
            unknown = set(shot.characters) - known
            if unknown:
                raise ValueError(f'{shot.id} references undefined character(s): {", ".join(sorted(unknown))}')
            words = len(shot.narration.text.split())
            # Conservative language-specific speech-rate check; TTS duration remains authoritative.
            rate = 1.8 if shot.narration.lang.startswith(('am','om','ti')) else 2.3
            if words / max(shot.duration_s, 0.1) > rate * 1.35:
                raise ValueError(f'{shot.id} narration is probably too long for {shot.duration_s:g}s')
            if shot.narration.lang != self.language:
                raise ValueError(f'{shot.id}.narration.lang must match storyboard.language')
            if not shot.subtitle_en.strip():
                raise ValueError(f'{shot.id} is missing English subtitles')
        total = sum(s.duration_s for s in self.shots)
        if not 60 <= total <= 90:
            raise ValueError(f'total film duration must be 60-90 seconds; got {total:g}s')
        if abs(total - self.target_runtime_s) > max(2.0, self.target_runtime_s * .15):
            raise ValueError(f'total shot duration ({total:g}s) differs from target_runtime_s ({self.target_runtime_s:g}s) by more than 15%')
        if self.music.duration_s < total:
            raise ValueError(f'music.duration_s must cover the film ({total:g}s)')
        for cue in self.music.cues:
            if cue.at_shot not in set(ids):
                raise ValueError(f'music cue references unknown shot: {cue.at_shot}')
        return self
