#!/usr/bin/env python3
"""Classify an enums.json change as MAJOR / MINOR / none, and check VERSION.

The SemVer contract for this repo:

* adding an enum, or adding a value to an existing enum  -> MINOR
* removing or renaming a value, or removing an enum      -> MAJOR
  (a rename is a removal plus an addition, so it lands in MAJOR)
* reordering values or editing a description             -> no bump required

Used by ``.github/workflows/validate.yml`` to comment on PRs. It prints a
markdown report and always exits 0 — it advises, it does not block.

    python scripts/semver_check.py \
        --base-enums /tmp/base-enums.json --head-enums enums.json \
        --base-version /tmp/base-VERSION  --head-version VERSION \
        --markdown /tmp/report.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate import SpecError, load_enums  # noqa: E402


def read_enums(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        return {spec.name: list(spec.values) for spec in load_enums(path)}
    except SpecError:
        # A malformed *base* revision should not crash the report; the head
        # revision is validated separately by generate.py in its own job.
        return {}


def parse_version(text: str) -> tuple[int, int, int]:
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return (0, 0, 0)
    major, minor, patch = (int(p) for p in parts)
    return (major, minor, patch)


def classify(base: dict[str, list[str]], head: dict[str, list[str]]) -> tuple[str, list[str], list[str]]:
    """Return (bump, breaking_lines, additive_lines)."""
    breaking: list[str] = []
    additive: list[str] = []

    for name, values in base.items():
        if name not in head:
            breaking.append(f"**`{name}`** removed entirely ({len(values)} value(s))")
            continue
        removed = [v for v in values if v not in head[name]]
        if removed:
            breaking.append(f"**`{name}`** lost value(s): {', '.join(f'`{v}`' for v in removed)}")

    for name, values in head.items():
        if name not in base:
            joined = ", ".join(f"`{v}`" for v in values)
            additive.append(f"**`{name}`** added ({joined})")
            continue
        added = [v for v in values if v not in base[name]]
        if added:
            additive.append(f"**`{name}`** gained value(s): {', '.join(f'`{v}`' for v in added)}")

    if breaking:
        return "major", breaking, additive
    if additive:
        return "minor", breaking, additive
    return "none", breaking, additive


def version_is_sufficient(bump: str, base: tuple[int, int, int], head: tuple[int, int, int]) -> bool:
    if bump == "major":
        return head[0] > base[0]
    if bump == "minor":
        return head[0] > base[0] or (head[0] == base[0] and head[1] > base[1])
    return head >= base


def render(bump: str, breaking: list[str], additive: list[str], base_v: str, head_v: str, ok: bool) -> str:
    heading = {
        "major": "### 🚨 Breaking enum change — **MAJOR** bump required",
        "minor": "### ✨ Additive enum change — **MINOR** bump required",
        "none": "### ✅ No enum value changes",
    }[bump]

    lines = ["<!-- localoy-shared-semver -->", heading, ""]

    if breaking:
        lines += ["**Removed / renamed (breaking):**", ""]
        lines += [f"- {line}" for line in breaking]
        lines.append("")
    if additive:
        lines += ["**Added (backwards compatible):**", ""]
        lines += [f"- {line}" for line in additive]
        lines.append("")
    if bump == "none":
        lines += [
            "`enums.json` values are unchanged relative to the base branch "
            "(reordering and description edits do not require a bump).",
            "",
        ]

    lines += [f"`VERSION`: `{base_v}` → `{head_v}`", ""]
    if ok:
        lines.append("The version bump in this PR satisfies the required change level. 👍")
    else:
        lines.append(
            f"⚠️ **`VERSION` has not been bumped enough.** This change needs a **{bump}** bump "
            f"but `VERSION` went `{base_v}` → `{head_v}`. Update `VERSION`, re-run "
            "`python generate.py`, and commit the result."
        )
        if bump == "major":
            lines.append(
                "\nRemoving or renaming a value breaks every consumer that still sends or "
                "matches the old string — coordinate the rollout before merging."
            )

    lines += ["", "<sub>Posted by `scripts/semver_check.py`.</sub>"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-enums", type=Path, required=True)
    parser.add_argument("--head-enums", type=Path, required=True)
    parser.add_argument("--base-version", type=Path, required=True)
    parser.add_argument("--head-version", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, help="also write the report to this file")
    args = parser.parse_args(argv)

    base_enums = read_enums(args.base_enums)
    head_enums = read_enums(args.head_enums)
    base_v_raw = args.base_version.read_text(encoding="utf-8").strip() if args.base_version.exists() else "0.0.0"
    head_v_raw = args.head_version.read_text(encoding="utf-8").strip()

    bump, breaking, additive = classify(base_enums, head_enums)
    ok = version_is_sufficient(bump, parse_version(base_v_raw), parse_version(head_v_raw))
    report = render(bump, breaking, additive, base_v_raw, head_v_raw, ok)

    print(report)
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"bump={bump}\n")
            handle.write(f"version_ok={'true' if ok else 'false'}\n")

    if not ok:
        print(f"::warning::enums.json requires a {bump} bump; VERSION is {head_v_raw}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
