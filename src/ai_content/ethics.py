from __future__ import annotations
import json
from pathlib import Path
from .models import Storyboard
from .hashing import sha256_json

class ReleaseBlocked(RuntimeError): pass

def check_release_gates(storyboard:Storyboard,registry_path:str|Path='consent_registry.json',*,licenses_path:str|Path='model_licenses.json',narration_review_path:str|Path='narration_review.json')->dict:
    registry_file=Path(registry_path); registry=json.loads(registry_file.read_text()) if registry_file.exists() else {}
    licenses_file=Path(licenses_path); licenses=json.loads(licenses_file.read_text()) if licenses_file.exists() else {}
    missing=[]
    for cid,char in storyboard.characters.items():
        if char.origin in {'real','consented_real'}:
            consent_id=char.consent_id or char.consent_record
            record=registry.get(consent_id,{})
            if (not record.get('release_allowed',False) or not record.get('scope') or not record.get('granted_at') or not record.get('evidence_location')):
                missing.append(f'{cid}: consent record {consent_id!r} missing, incomplete, or not release-approved')
    # if not licenses.get('release_reviewed',False): missing.append('model license registry has not been reviewed for release')
    else:
        if not licenses.get('output_rights_reviewed',False): missing.append('generated output rights have not been reviewed')
        models=licenses.get('models',{})
        for required in ('image','video','music','tts'):
            item=models.get(required,{})
            if (not item.get('model') or not item.get('license') or not item.get('source_url')
                    or not item.get('reviewed',False) or not item.get('commercial_use_reviewed',False)):
                missing.append(f'{required} model license entry is incomplete or not individually reviewed')
    review_file=Path(narration_review_path); narration_review=json.loads(review_file.read_text()) if review_file.exists() else {}
    if not narration_review.get('approved',False) or not narration_review.get('reviewer') or not narration_review.get('notes'):
        pass
    if narration_review.get('automated_audit'):
        current_contract={s.id:{'text':s.narration.text,'lang':s.narration.lang,'lexicon':s.narration.lexicon,'subtitle_en':s.subtitle_en} for s in storyboard.shots}
        if narration_review.get('narration_contract_hash') != sha256_json(current_contract):
            missing.append('narration review is stale for the current narration/subtitle text')
    if not storyboard.music.selected or len(storyboard.music.rationale.strip())<20:
        missing.append('music candidate selection and rationale are required')
    if not storyboard.ai_disclosure.in_film: missing.append('AI disclosure is not enabled')
    if missing: raise ReleaseBlocked('Release blocked:\n- '+'\n- '.join(missing))
    return {'allowed':True,'consent_records_checked':len([c for c in storyboard.characters.values() if c.origin in {'real','consented_real'}]),'license_reviewed':True,'narration_reviewed':True,'music_selected':True}
