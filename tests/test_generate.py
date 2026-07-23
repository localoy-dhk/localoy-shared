"""Tests for the enum generator's name derivation, validation and idempotency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate  # noqa: E402
from generate import (  # noqa: E402
    SpecError,
    fetch_remote_enums,
    load_enums,
    python_member,
    typescript_member,
)


class _FakeResponse:
    """Minimal stand-in for the urlopen() context manager generate.py uses."""

    def __init__(self, payload: bytes, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _stub_urlopen(monkeypatch: pytest.MonkeyPatch, body: object, status: int = 200) -> None:
    payload = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
    monkeypatch.setattr(generate, "urlopen", lambda _req, timeout=None: _FakeResponse(payload, status))


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


# --------------------------------------------------------------------------
# Remote sync (--sync / --url / ENUMS_URL)
# --------------------------------------------------------------------------


def test_fetch_remote_enums_splits_version_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_urlopen(
        monkeypatch,
        {
            "$schema": "./schema.json",
            "$version": "1.2.0",
            "EventType": ["indoor", "outdoor"],
        },
    )
    enum_map, version = fetch_remote_enums("http://enums.test/enums.json")
    assert version == "1.2.0"
    # "$"-prefixed metadata is stripped from the enum map; the version rides out separately.
    assert enum_map == {"EventType": ["indoor", "outdoor"]}


def test_fetch_remote_enums_requires_valid_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_urlopen(monkeypatch, {"EventType": ["indoor"]})  # no $version
    with pytest.raises(SpecError):
        fetch_remote_enums("http://enums.test/enums.json")


@pytest.mark.parametrize("body", ["[]", "not json", '{"$version": "1.0.0"}'])
def test_fetch_remote_enums_rejects_bad_bodies(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    # non-object, unparseable, and a body with a version but no enums all fail loudly.
    _stub_urlopen(monkeypatch, body)
    with pytest.raises(SpecError):
        fetch_remote_enums("http://enums.test/enums.json")


def test_check_and_sync_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        generate.main(["--check", "--sync", "--url", "http://enums.test/enums.json"])


def test_sync_needs_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENUMS_URL", raising=False)
    assert generate.main(["--sync"]) == 2  # SpecError → exit 2


def _point_generate_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect every file generate.py writes into tmp_path (never the real repo)."""
    paths = {
        "ENUMS_JSON": tmp_path / "enums.json",
        "VERSION_FILE": tmp_path / "VERSION",
        "PY_ENUMS": tmp_path / "python" / "localoy_shared" / "enums.py",
        "PY_INIT": tmp_path / "python" / "localoy_shared" / "__init__.py",
        "TS_ENUMS": tmp_path / "js" / "src" / "enums.ts",
        "JS_PACKAGE_JSON": tmp_path / "js" / "package.json",
    }
    # ROOT too, so main()'s `path.relative_to(ROOT)` progress lines resolve.
    monkeypatch.setattr(generate, "ROOT", tmp_path)
    for name, path in paths.items():
        monkeypatch.setattr(generate, name, path)
    # render_js_package_json reads the existing manifest, so give it a minimal one.
    paths["JS_PACKAGE_JSON"].parent.mkdir(parents=True, exist_ok=True)
    paths["JS_PACKAGE_JSON"].write_text('{\n  "name": "@localoy-dhk/shared",\n  "version": "0.0.0"\n}\n')
    return paths


def test_sync_round_trips_the_committed_enums(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Publishing today's enums.json and syncing it back preserves values, order and version."""
    repo_root = Path(__file__).resolve().parent.parent
    committed_enums = json.loads((repo_root / "enums.json").read_text(encoding="utf-8"))
    committed_version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()

    body = {"$schema": "./schema.json", "$version": committed_version, **committed_enums}
    _stub_urlopen(monkeypatch, body)
    paths = _point_generate_at(tmp_path, monkeypatch)

    assert generate.main(["--sync", "--url", "http://enums.test/enums.json"]) == 0

    synced_enums = json.loads(paths["ENUMS_JSON"].read_text(encoding="utf-8"))
    assert synced_enums == committed_enums  # same values
    assert list(synced_enums) == list(committed_enums)  # same enum order
    assert paths["VERSION_FILE"].read_text(encoding="utf-8").strip() == committed_version
    # A second sync against the same body is a no-op — proves idempotency.
    assert generate.main(["--sync", "--url", "http://enums.test/enums.json"]) == 0


def test_sync_refuses_version_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _point_generate_at(tmp_path, monkeypatch)
    paths["VERSION_FILE"].write_text("2.0.0\n", encoding="utf-8")
    _stub_urlopen(monkeypatch, {"$version": "1.0.0", "EventType": ["indoor"]})

    # Older published version than the committed one is refused by default…
    assert generate.main(["--sync", "--url", "http://enums.test/enums.json"]) == 2
    # …but the escape hatch lets it through.
    assert generate.main(
        ["--sync", "--url", "http://enums.test/enums.json", "--allow-version-downgrade"]
    ) == 0
    assert paths["VERSION_FILE"].read_text(encoding="utf-8").strip() == "1.0.0"
