# localoy-shared — Claude Context

Canonical enum definitions for the Localoy microservices, generated into a
Python package and a TypeScript package from one JSON file.

Consumer-facing docs (install/upgrade instructions): [`README.md`](README.md).
This file is the working contract for editing **this** repo.

---

## The one rule

**`enums.json` is the ONLY place enum values are authored.** Everything else
that contains an enum value is generated output. Never hand-edit:

| Generated file | Written by |
| --- | --- |
| `python/localoy_shared/enums.py` | `generate.py` |
| `python/localoy_shared/__init__.py` | `generate.py` |
| `js/src/enums.ts` | `generate.py` |
| the `version` field in `js/package.json` | `generate.py` |

Each generated file starts with `AUTO-GENERATED FROM enums.json — DO NOT EDIT`.
If you are about to add an enum member to a `.py` or `.ts` file, stop: add it to
`enums.json` and run `python generate.py`.

CI enforces this. `validate.yml` regenerates on every PR and fails if the working
tree is dirty, so a hand-edit is caught rather than merged.

The second authored file is **`VERSION`** — the single version number shared by
both packages. Nothing else declares a version:
`pyproject.toml` uses `dynamic = ["version"]` and reads `__version__` out of the
generated `__init__.py`; `js/package.json`'s version field is overwritten by the
generator.

---

## Making a change

```bash
vi enums.json          # 1. edit values
vi VERSION             # 2. bump per the SemVer table below
make generate          # 3. regenerate (or: python generate.py)
make test              # 4. generator tests
git add -A && git commit
```

Then open a PR. After merge, tag `v$(cat VERSION)` to release.

### SemVer — non-negotiable

| Change | Bump |
| --- | --- |
| add an enum, or add a value | **MINOR** |
| remove a value, remove an enum | **MAJOR** |
| rename a value (= remove + add) | **MAJOR** |
| reorder values, edit a description | none |

Renames must be done as two releases: add the new value (minor) → migrate every
producer and consumer → remove the old one (major). Never rename in place; a
pinned consumer is still emitting the old string.

`scripts/semver_check.py` classifies the diff against the PR base and comments
the verdict, including whether `VERSION` was bumped enough. It **warns**, it does
not block — the merge decision stays human.

---

## Code map

| Path | Role |
| --- | --- |
| `enums.json` | authored values (short list form, or `{description, values}`) |
| `VERSION` | authored `X.Y.Z`, the only version declaration |
| `generate.py` | load → validate → render → write-if-changed; `--check` for CI |
| `scripts/semver_check.py` | major/minor/none classification + PR comment body |
| `tests/test_generate.py` | name derivation, spec validation, idempotency |
| `js/src/index.ts` | hand-written entry point — put helpers here, not in `enums.ts` |
| `.github/workflows/validate.yml` | dirty-tree check, tests, both builds, semver comment |
| `.github/workflows/release.yml` | on `v*` tag: verify → build → publish JS → GitHub Release |

---

## generate.py invariants

Preserve these when touching the generator:

1. **Idempotent.** Files are written only when content changes; a second run
   produces no diff. `sync()` is where that lives — don't replace it with an
   unconditional write, or every run would dirty mtimes and confuse `--check`.
2. **Deterministic ordering.** Enums and members are emitted in `enums.json`
   order. Never sort — a reorder would show up as a diff for no semantic reason.
3. **Python enums are `class X(str, Enum)`.** Not `StrEnum` (needs 3.11+ *and*
   changes `str()` output), not plain `Enum`. Consumers rely on pydantic/FastAPI
   serializing members to the raw string and on `json.dumps` working directly.
4. **Fail loudly.** Invalid spec → `SpecError` → exit 2. Colliding member names
   are an error, not a silently-deduped member.
5. **Member derivation is documented in the README.** If you change the
   tokenizer, you are changing every consumer's symbol names — that is a
   **major** bump, and the README table plus `tests/test_generate.py` must be
   updated in the same commit.

Member names: tokenize on non-alphanumeric runs and camelCase boundaries →
Python `UPPER_SNAKE`, TypeScript `PascalCase`; a leading digit gets a `VALUE_` /
`Value` prefix.

## Adding a new output language

Add a renderer function plus an entry in the `outputs` dict in `main()`, and add
the new file to the generated-files table above and in the README. Keep the
DO-NOT-EDIT header — that header is what makes the CI dirty-tree check
comprehensible to whoever trips it.

## Testing

`make test` runs `tests/test_generate.py` (pytest). Anything touching name
derivation needs a case added there — that test is the spec for the mapping.

## What lives elsewhere

This repo holds **enums only** — no shared DTOs, no client SDKs, no utils. It is
depended on by every service, so its blast radius is wide and its release
cadence should stay boring. Shared request/response types belong in the owning
service, not here.
