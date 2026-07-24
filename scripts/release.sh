#!/usr/bin/env bash
#
# Guided release: the whole post-publish flow in one command.
#
#   sync → check → REVIEW (you confirm) → commit → tag-at-HEAD → push
#
# It exists because that sequence is fiddly by hand and the ordering matters:
# tagging before committing pins the tag to the OLD VERSION and the release
# workflow rejects it (the "Tag must match VERSION" guard). This script always
# commits first and tags HEAD, so that failure mode is impossible.
#
# The diff review is kept as a human gate — a release is an outward, immutable
# publish. Everything mechanical around it is automated.
#
# Usage:
#   ENUMS_URL=http://localhost:4100/api/v1/public/enums.json ./scripts/release.sh
#   ./scripts/release.sh --url http://localhost:4100/api/v1/public/enums.json
#
set -euo pipefail

cd "$(dirname "$0")/.."

# ── colours ───────────────────────────────────────────────────────────────────
if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; X=$'\033[0m'; else B= G= Y= R= C= X=; fi
say()  { printf "%b\n" "$*"; }
step() { printf "\n${B}${C}▸ %s${X}\n" "$*"; }
die()  { printf "${R}✗ %s${X}\n" "$*" >&2; exit 1; }

# ── resolve the published-enums URL ───────────────────────────────────────────
URL="${ENUMS_URL:-}"
if [ "${1:-}" = "--url" ]; then URL="${2:-}"; fi
[ -n "$URL" ] || die "no enums URL — set ENUMS_URL or pass --url <url>"

# ── 0 · preflight: clean tree, on a branch ────────────────────────────────────
step "Preflight"
[ -z "$(git status --porcelain)" ] || die "working tree not clean — commit or stash first, so the release commit only contains the sync."
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || say "${Y}⚠ on '$BRANCH', not 'main' — continuing, but releases normally cut from main.${X}"
say "clean tree on ${B}$BRANCH${X}, syncing from ${B}$URL${X}"

# ── 1 · sync ──────────────────────────────────────────────────────────────────
step "Sync"
python3 generate.py --sync --url "$URL"

if [ -z "$(git status --porcelain)" ]; then
  say "\n${G}✓ already up to date — the repo matches the published release. Nothing to do.${X}"
  exit 0
fi

VERSION="$(cat VERSION)"
TAG="v$VERSION"

# refuse to re-release a version that already has a tag
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "tag $TAG already exists — this version was released before. Publish a new version first."
fi

# ── 2 · check ─────────────────────────────────────────────────────────────────
step "Verify generated files"
python3 generate.py --check
say "${G}✓ generated files current${X}"

# ── 3 · review (the human gate) ───────────────────────────────────────────────
step "Review — $TAG"
git --no-pager diff --stat
say ""
git --no-pager diff enums.json VERSION
say ""
printf "${B}Release ${C}%s${X}${B}? This commits, tags, and pushes (triggers publish). [y/N] ${X}" "$TAG"
read -r ans </dev/tty
case "$ans" in [yY]|[yY][eE][sS]) ;; *) die "aborted — nothing pushed. Your synced files are left in the working tree." ;; esac

# ── 4 · commit → tag-at-HEAD → push (the safe order) ──────────────────────────
step "Commit + tag + push"
git add -A
git commit -q -m "chore: sync enums from registry → $VERSION"
git tag "$TAG" HEAD                     # tag HEAD, which now HAS the new VERSION
git push origin "$BRANCH"
git push origin "$TAG"

say "\n${G}${B}✓ Released $TAG${X}"
say "  • release workflow: ${C}gh run watch \$(gh run list --workflow release --limit 1 --json databaseId --jq '.[0].databaseId')${X}"
say "  • once green, upgrade the apps: ${C}make -C .. shared-upgrade${X}  (from the workspace root: ${C}make shared-upgrade${X})"
