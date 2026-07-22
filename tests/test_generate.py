"""Tests for the enum generator's name derivation, validation and idempotency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate  # noqa: E402
from generate import SpecError, load_enums, python_member, typescript_member  # noqa: E402


@pytest.mark.parametrize(
    ("value", "py", "ts"),
    [
        ("indoor", "INDOOR", "Indoor"),
        ("in_progress", "IN_PROGRESS", "InProgress"),
        ("in-progress", "IN_PROGRESS", "InProgress"),
        ("in progress", "IN_PROGRESS", "InProgress"),
        ("inProgress", "IN_PROGRESS", "InProgress"),
        ("HTTPServer", "HTTP_SERVER", "HttpServer"),
        ("cancelled-v2", "CANCELLED_V2", "CancelledV2"),
        ("2fa", "VALUE_2FA", "Value2fa"),
    ],
)
def test_member_derivation(value: str, py: str, ts: str) -> None:
    assert python_member(value) == py
    assert typescript_member(value) == ts


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "enums.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_object_form_with_description(tmp_path: Path) -> None:
    path = _write(tmp_path, {"EventType": {"description": "Kind of event.", "values": ["indoor"]}})
    (spec,) = load_enums(path)
    assert spec.description == "Kind of event."
    assert spec.values == ("indoor",)


def test_metadata_keys_are_ignored(tmp_path: Path) -> None:
    path = _write(tmp_path, {"$schema": "./schema.json", "EventType": ["indoor"]})
    assert [spec.name for spec in load_enums(path)] == ["EventType"]


@pytest.mark.parametrize(
    "payload",
    [
        {"eventType": ["indoor"]},  # not PascalCase
        {"EventType": []},  # empty
        {"EventType": ["indoor", "indoor"]},  # duplicate value
        {"EventType": ["indoor", ""]},  # empty value
        {"EventType": ["in_progress", "in-progress"]},  # colliding member names
        {"EventType": ["!!!"]},  # no derivable name
        {"EventType": {"vals": ["indoor"]}},  # unknown key
    ],
)
def test_rejects_bad_specs(tmp_path: Path, payload: object) -> None:
    with pytest.raises(SpecError):
        load_enums(_write(tmp_path, payload))


def test_repo_generation_is_idempotent() -> None:
    """The checked-in generated files must already match enums.json."""
    assert generate.main(["--check"]) == 0
