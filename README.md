# localoy-shared

Single source of truth for the enums shared across the Localoy microservices —
authored once in [`enums.json`](enums.json), generated into a **Python** package
and a **TypeScript** package, and released under one version number.

```
enums.json  ──▶  generate.py  ──┬──▶  python/localoy_shared/enums.py   (pip install from tag)
   +VERSION                     └──▶  js/src/enums.ts                  (npm @localoy-dhk/shared)
```

Why: `EventStatus` must mean the same thing in the FastAPI auth service, the
Express partner backend and the Next.js portals. Hand-maintaining three copies
guarantees they drift.

---

## Consuming the packages

### Python (FastAPI / pydantic services)

Installed straight from a git tag — there is no PyPI publish.

```bash
pip install "git+https://github.com/localoy-dhk/localoy-shared@v0.1.0#subdirectory=python"
```

`requirements.txt`:

```
localoy-shared @ git+https://github.com/localoy-dhk/localoy-shared@v0.1.0#subdirectory=python
```

`pyproject.toml` (poetry):

```toml
[tool.poetry.dependencies]
localoy-shared = { git = "https://github.com/localoy-dhk/localoy-shared.git", tag = "v0.1.0", subdirectory = "python" }
```

> **Always pin a tag, never a branch.** `@main` reinstalls a different thing on
> every `pip install` and silently changes behaviour between a passing CI run
> and a production deploy. Tags in this repo are immutable by convention — a
> mistake gets a new tag, never a force-push.

Usage:

```python
from localoy_shared import EventStatus, EventType

class EventCreate(BaseModel):
    type: EventType          # FastAPI renders this as an enum in the OpenAPI schema
    status: EventStatus = EventStatus.DRAFT

EventStatus.PUBLISHED.value   # "published"
EventStatus("draft")          # EventStatus.DRAFT — raises ValueError on unknown input
```

Every enum subclasses `str`, so pydantic/FastAPI serialize members to their raw
string with no custom encoder, and `json.dumps` works directly.

### TypeScript / JavaScript (Next.js portals, Express backends)

Published to **GitHub Packages** as `@localoy-dhk/shared`.

`.npmrc` in the consuming repo (commit this file):

```
@localoy-dhk:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

`GITHUB_TOKEN` needs the `read:packages` scope. Locally that is a personal
access token exported in your shell; in GitHub Actions the built-in
`secrets.GITHUB_TOKEN` is enough (add `permissions: packages: read` to the job).

```bash
npm install @localoy-dhk/shared@0.1.0
```

Usage:

```ts
import { EventStatus, EventType } from '@localoy-dhk/shared';

const status: EventStatus = EventStatus.Published; // "published"
```

### Pinning policy

| | Recommended range | Lockfile |
| --- | --- | --- |
| Python | exact tag (`@vX.Y.Z`) | `requirements.txt` / `poetry.lock` committed |
| JS | `^X.Y.Z` | `package-lock.json` committed |

Use `^` on the JS side plus a committed lockfile: the caret documents "minor
upgrades are safe", the lockfile means nothing actually moves until someone
commits a new one. Wire **[Renovate](https://docs.renovatebot.com/)** up in each
consuming repo so upgrades arrive as reviewable PRs with CI attached rather than
as a surprise on the next `npm install`.

Minimal `renovate.json` for a consumer:

```json
{
  "extends": ["config:recommended"],
  "packageRules": [
    {
      "matchPackageNames": ["@localoy-dhk/shared", "localoy-shared"],
      "groupName": "localoy-shared",
      "automerge": false
    }
  ]
}
```

### ⚠️ Always give exhaustive switches a default arm

Adding a value is a **minor** release here, which means a consumer can receive a
value its pinned copy has never heard of — from a newer service, or from a row
written after its own upgrade. Code that assumes it has seen every member will
break on a release that this repo considers backwards compatible.

```ts
// ✅ survives a minor bump
switch (event.status) {
  case EventStatus.Draft:      return renderDraft();
  case EventStatus.Published:  return renderPublished();
  case EventStatus.Cancelled:  return renderCancelled();
  default:                     return renderUnknown(event.status);
}
```

```python
# ✅ survives a minor bump
match event.status:
    case EventStatus.DRAFT:      return render_draft()
    case EventStatus.PUBLISHED:  return render_published()
    case EventStatus.CANCELLED:  return render_cancelled()
    case _:                      return render_unknown(event.status)
```

TypeScript's `never`-assertion exhaustiveness trick is a *compile-time* check
against your pinned version — it does not protect the running service from a
string a newer producer sent. Keep the `default` arm as well.

Also: parse untrusted input defensively. `EventStatus('made_up')` raises
`ValueError` in Python; in TypeScript, a plain cast will happily let an unknown
string through, so validate at the boundary (zod, or an `Object.values(...)`
membership check).

---

## Changing an enum

Values are normally authored in the **Enum Registry** admin UI and published to
`GET /api/v1/public/enums.json`; this repo then pulls that release in:

```bash
ENUMS_URL=https://<admin-backend>/api/v1/public/enums.json make sync
# (= python generate.py --sync — fetches the published body, rewrites enums.json
#    + VERSION from it, then regenerates. Only --sync touches the network.)
```

Review the `enums.json` / `VERSION` diff, commit, open a PR, then tag (below).
`--sync` refuses to move `VERSION` backwards unless you pass
`--allow-version-downgrade`. Because CI still runs `generate.py --check` against
the **committed** files and `semver_check.py` still re-derives the bump from the
git diff, the release gate stays exactly where it was — in git.

To edit offline instead (no registry):

1. Edit **`enums.json`** — the file the generator reads values from.
2. Bump **`VERSION`** per the rules below.
3. Run `python generate.py` (or `make generate`) and commit the generated files.
4. Open a PR. `validate.yml` re-generates and fails if your tree is dirty, then
   comments with the change classification and whether `VERSION` is sufficient.
5. Merge, then tag:

   ```bash
   git tag v0.2.0 && git push origin v0.2.0
   ```

   `release.yml` verifies the tag matches `VERSION`, rebuilds, publishes the JS
   package to GitHub Packages and attaches the Python sdist/wheel to the Release.

### SemVer rules

| Change | Bump | Why |
| --- | --- | --- |
| New enum, or new value on an existing enum | **MINOR** | Old consumers keep working; they just don't know the new value yet. |
| Removing a value | **MAJOR** | Consumers still emit and match the old string. |
| Renaming a value | **MAJOR** | A rename is a removal plus an addition. |
| Reordering values, editing a description | none | No wire-format change. |

The version lives in exactly one place — the root `VERSION` file. `generate.py`
writes it into `python/localoy_shared/__init__.py` (which hatchling reads via
`[tool.hatch.version]`) and into `js/package.json`, so the two packages cannot
drift.

### Renaming a value safely

Never rename in one release. Add the new value (minor), migrate every producer
and consumer, then remove the old one (major) once nothing references it.

---

## `enums.json` format

Short form — a list of values:

```json
{ "EventType": ["indoor", "outdoor"] }
```

Long form, when the enum deserves a docstring (rendered into both outputs):

```json
{
  "EventType": {
    "description": "Whether the event happens indoors or outdoors.",
    "values": ["indoor", "outdoor"]
  }
}
```

Rules enforced by the generator (it exits non-zero on any violation):

- enum names are PascalCase identifiers; values are non-empty, unique strings
- keys starting with `$` are reserved for metadata (e.g. `$schema`) and skipped
- two values may not derive the same member name in either language

### Member-name derivation

Values are tokenized by splitting on non-alphanumeric runs and camelCase
boundaries, keeping acronym runs whole. Python joins the tokens with `_` and
upper-cases; TypeScript PascalCases them. A name that would start with a digit
gets a `VALUE_` (Python) / `Value` (TypeScript) prefix.

| value | Python | TypeScript |
| --- | --- | --- |
| `indoor` | `INDOOR` | `Indoor` |
| `in_progress` / `in-progress` / `inProgress` | `IN_PROGRESS` | `InProgress` |
| `HTTPServer` | `HTTP_SERVER` | `HttpServer` |
| `cancelled-v2` | `CANCELLED_V2` | `CancelledV2` |
| `2fa` | `VALUE_2FA` | `Value2fa` |

Note the collisions this implies: `in_progress` and `in-progress` cannot coexist
in one enum. The generator rejects that rather than silently emitting a
duplicate member.

---

## Repo layout

```
localoy-shared/
├── enums.json                        ← the only place values are authored
├── VERSION                           ← the only place the version is authored
├── generate.py                       ← emits both packages; --check for CI
├── Makefile
├── scripts/semver_check.py           ← classifies a diff as major/minor/none
├── tests/test_generate.py
├── python/
│   ├── pyproject.toml                (hatchling; version read from __init__.py)
│   └── localoy_shared/
│       ├── __init__.py               GENERATED
│       ├── enums.py                  GENERATED
│       └── py.typed
├── js/
│   ├── package.json                  (version field is GENERATED)
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts                  hand-written entry point
│       └── enums.ts                  GENERATED
└── .github/workflows/{validate,release}.yml
```

## Local development

```bash
make generate   # regenerate both packages
make check      # fail if anything is out of date (what CI runs)
make test       # generator test suite (pytest)
make build      # build both packages
```
