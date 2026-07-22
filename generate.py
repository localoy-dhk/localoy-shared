#!/usr/bin/env python3
"""Generate the Python and TypeScript enum packages from ``enums.json``.

``enums.json`` and ``VERSION`` are the only hand-authored inputs in this repo.
Everything this script writes carries a DO-NOT-EDIT header and is checked into
git so that consumers can install straight from a tag without a build step.

Outputs
-------
* ``python/localoy_shared/enums.py``  — one ``class Name(str, Enum)`` per enum
* ``python/localoy_shared/__init__.py`` — re-exports + ``__version__``
* ``js/src/enums.ts``                 — one ``export enum Name`` per enum
* ``js/package.json``                 — only the ``version`` field is rewritten

Determinism / idempotency
-------------------------
Enums and members are emitted in the exact order they appear in ``enums.json``.
Files are only written when their content actually changes, so running this
script twice in a row produces no diff on the second run.

Usage
-----
    python generate.py            # write the generated files
    python generate.py --check    # exit 1 if anything would change (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENUMS_JSON = ROOT / "enums.json"
VERSION_FILE = ROOT / "VERSION"
PY_ENUMS = ROOT / "python" / "localoy_shared" / "enums.py"
PY_INIT = ROOT / "python" / "localoy_shared" / "__init__.py"
TS_ENUMS = ROOT / "js" / "src" / "enums.ts"
JS_PACKAGE_JSON = ROOT / "js" / "package.json"

PY_HEADER = "# AUTO-GENERATED FROM enums.json — DO NOT EDIT"
TS_HEADER = "// AUTO-GENERATED FROM enums.json — DO NOT EDIT"
REGEN_HINT = "Regenerate with `python generate.py` from the repo root."

# Enum type names must be PascalCase identifiers, e.g. `EventStatus`.
ENUM_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9]*")

# Semantic version, no pre-release / build metadata — keep releases boring.
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")

# Value tokenizer. Splits on any non-alphanumeric run and on camelCase
# boundaries, keeping acronym runs together:
#   "indoor"        -> ["indoor"]
#   "in_progress"   -> ["in", "progress"]
#   "inProgress"    -> ["in", "Progress"]
#   "HTTPServer"    -> ["HTTP", "Server"]
#   "cancelled-v2"  -> ["cancelled", "v2"]
TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")


class SpecError(Exception):
    """Raised when enums.json (or VERSION) is malformed."""


@dataclass(frozen=True)
class EnumSpec:
    name: str
    values: tuple[str, ...]
    description: str | None


# --------------------------------------------------------------------------
# Member-name derivation (deterministic and documented — see README)
# --------------------------------------------------------------------------


def tokenize(value: str) -> list[str]:
    tokens = TOKEN_RE.findall(value)
    if not tokens:
        raise SpecError(
            f"value {value!r} contains no alphanumeric characters, so no member "
            "name can be derived from it"
        )
    return tokens


def python_member(value: str) -> str:
    """`"in_progress"` -> `IN_PROGRESS`. A leading digit gets a `VALUE_` prefix."""
    name = "_".join(token.upper() for token in tokenize(value))
    return f"VALUE_{name}" if name[0].isdigit() else name


def typescript_member(value: str) -> str:
    """`"in_progress"` -> `InProgress`. A leading digit gets a `Value` prefix."""
    name = "".join(token[:1].upper() + token[1:].lower() for token in tokenize(value))
    return f"Value{name}" if name[0].isdigit() else name


# --------------------------------------------------------------------------
# Input loading + validation
# --------------------------------------------------------------------------


def load_version() -> str:
    if not VERSION_FILE.exists():
        raise SpecError(f"{VERSION_FILE.name} is missing")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not VERSION_RE.fullmatch(version):
        raise SpecError(f"{VERSION_FILE.name} must contain a bare X.Y.Z version, got {version!r}")
    return version


def load_enums(path: Path = ENUMS_JSON) -> list[EnumSpec]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise SpecError(f"{path.name} is not valid JSON: {err}") from err
    if not isinstance(raw, dict):
        raise SpecError(f"{path.name} must be a JSON object mapping enum name -> values")

    specs: list[EnumSpec] = []
    for name, body in raw.items():
        # Keys starting with "$" are reserved for metadata (e.g. "$schema").
        if name.startswith("$"):
            continue
        if not ENUM_NAME_RE.fullmatch(name):
            raise SpecError(f"enum name {name!r} must be PascalCase, e.g. 'EventStatus'")

        description: str | None = None
        if isinstance(body, list):
            values = body
        elif isinstance(body, dict):
            unknown = sorted(set(body) - {"values", "description"})
            if unknown:
                raise SpecError(f"enum {name!r} has unknown key(s): {', '.join(unknown)}")
            values = body.get("values")
            description = body.get("description")
            if description is not None and not isinstance(description, str):
                raise SpecError(f"enum {name!r}: 'description' must be a string")
        else:
            raise SpecError(
                f"enum {name!r} must be a list of values, or an object with "
                "'values' (and optionally 'description')"
            )

        specs.append(EnumSpec(name=name, values=tuple(_validate_values(name, values)), description=description))

    if not specs:
        raise SpecError(f"{path.name} defines no enums")
    return specs


def _validate_values(name: str, values: object) -> list[str]:
    if not isinstance(values, list) or not values:
        raise SpecError(f"enum {name!r} must have a non-empty list of values")

    seen: set[str] = set()
    py_names: dict[str, str] = {}
    ts_names: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise SpecError(f"enum {name!r}: every value must be a non-empty string, got {value!r}")
        if value in seen:
            raise SpecError(f"enum {name!r}: duplicate value {value!r}")
        seen.add(value)

        for derived, taken, lang in (
            (python_member(value), py_names, "Python"),
            (typescript_member(value), ts_names, "TypeScript"),
        ):
            if derived in taken:
                raise SpecError(
                    f"enum {name!r}: values {taken[derived]!r} and {value!r} both derive the "
                    f"{lang} member name {derived!r} — rename one of them"
                )
            taken[derived] = value
    return values


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_python_enums(specs: list[EnumSpec]) -> str:
    lines = [
        PY_HEADER,
        f"# {REGEN_HINT}",
        "",
        '"""Canonical Localoy enums.',
        "",
        "Each enum subclasses ``str`` so pydantic/FastAPI serialize members to their",
        "raw string value with no custom encoder.",
        '"""',
        "",
        "from enum import Enum",
        "",
        "__all__ = [",
    ]
    lines += [f'    "{spec.name}",' for spec in specs]
    lines.append("]")

    for spec in specs:
        lines += ["", "", f"class {spec.name}(str, Enum):"]
        lines.append(f'    """{spec.description}"""' if spec.description else f'    """{spec.name}."""')
        lines.append("")
        for value in spec.values:
            lines.append(f'    {python_member(value)} = "{value}"')

    return "\n".join(lines) + "\n"


def render_python_init(specs: list[EnumSpec], version: str) -> str:
    names = [spec.name for spec in specs]
    lines = [
        PY_HEADER,
        f"# {REGEN_HINT}",
        "",
        '"""Shared Localoy enums, generated from the canonical enums.json."""',
        "",
        "from .enums import (",
    ]
    lines += [f"    {name}," for name in names]
    lines += [
        ")",
        "",
        f'__version__ = "{version}"',
        "",
        "__all__ = [",
        '    "__version__",',
    ]
    lines += [f'    "{name}",' for name in names]
    lines.append("]")
    return "\n".join(lines) + "\n"


def render_typescript(specs: list[EnumSpec]) -> str:
    lines = [
        TS_HEADER,
        f"// {REGEN_HINT}",
    ]
    for spec in specs:
        lines.append("")
        if spec.description:
            lines += ["/**", f" * {spec.description}", " */"]
        lines.append(f"export enum {spec.name} {{")
        for value in spec.values:
            lines.append(f"  {typescript_member(value)} = '{value}',")
        lines.append("}")
    return "\n".join(lines) + "\n"


def render_js_package_json(version: str) -> str:
    """Rewrite only the ``version`` field so js and python can never drift."""
    manifest = json.loads(JS_PACKAGE_JSON.read_text(encoding="utf-8"))
    manifest["version"] = version
    return json.dumps(manifest, indent=2) + "\n"


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def sync(path: Path, content: str, *, check: bool) -> bool:
    """Return True when ``path`` differs from ``content`` (writing it unless --check)."""
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if any generated file is out of date",
    )
    args = parser.parse_args(argv)

    try:
        version = load_version()
        specs = load_enums()
        outputs = {
            PY_ENUMS: render_python_enums(specs),
            PY_INIT: render_python_init(specs, version),
            TS_ENUMS: render_typescript(specs),
            JS_PACKAGE_JSON: render_js_package_json(version),
        }
    except SpecError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    changed = [path for path, content in outputs.items() if sync(path, content, check=args.check)]

    if args.check:
        if changed:
            print("Generated files are out of date:", file=sys.stderr)
            for path in changed:
                print(f"  - {path.relative_to(ROOT)}", file=sys.stderr)
            print(f"\n{REGEN_HINT}", file=sys.stderr)
            return 1
        print(f"up to date — {len(specs)} enum(s), version {version}")
        return 0

    if changed:
        for path in changed:
            print(f"wrote {path.relative_to(ROOT)}")
    else:
        print("no changes")
    print(f"{len(specs)} enum(s), version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
