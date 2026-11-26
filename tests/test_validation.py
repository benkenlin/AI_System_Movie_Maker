
import json
from pathlib import Path

import pytest

from ai_content.validation import (
    StoryboardValidationError,
    load_storyboard,
)

EXAMPLE = Path(__file__).parents[1] / "examples" / "storyboard.example.json"


def read_example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def write_json(tmp_path, data):
    path = tmp_path / "storyboard.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_example_storyboard_is_valid():
    storyboard = load_storyboard(EXAMPLE)
    assert storyboard.title == "The Last Coffee Ceremony"
    assert len(storyboard.shots) == 8


def test_duplicate_shot_ids_are_rejected(tmp_path):
    data = read_example()
    data["shots"][1]["id"] = data["shots"][0]["id"]
    with pytest.raises(StoryboardValidationError, match="shot IDs must be unique"):
        load_storyboard(write_json(tmp_path, data))


def test_unknown_character_is_rejected(tmp_path):
    data = read_example()
    data["shots"][0]["characters"] = ["not_in_character_bible"]
    with pytest.raises(StoryboardValidationError, match="undefined character"):
        load_storyboard(write_json(tmp_path, data))


def test_real_person_without_consent_record_is_rejected(tmp_path):
    data = read_example()
    data["characters"]["grandmother"]["origin"] = "real"
    with pytest.raises(StoryboardValidationError, match="consent_record"):
        load_storyboard(write_json(tmp_path, data))


def test_music_must_cover_shot_duration(tmp_path):
    data = read_example()
    data["music"]["duration_s"] = 10
    with pytest.raises(StoryboardValidationError, match="music.duration_s"):
        load_storyboard(write_json(tmp_path, data))


def test_vertical_crop_must_be_between_zero_and_one(tmp_path):
    data = read_example()
    data["shots"][0]["vertical_crop_x"] = 1.5
    with pytest.raises(StoryboardValidationError, match="vertical_crop_x"):
        load_storyboard(write_json(tmp_path, data))


def test_unknown_fields_are_rejected(tmp_path):
    data = read_example()
    data["unexpected_runtime_flag"] = True
    with pytest.raises(StoryboardValidationError, match="Extra inputs are not permitted"):
        load_storyboard(write_json(tmp_path, data))
