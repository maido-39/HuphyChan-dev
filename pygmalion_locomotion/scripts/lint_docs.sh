#!/bin/bash
# lint_docs.sh — LLM Wiki health check (docs/SCHEMA.md): dangling [[links]], orphan pages, inventory.
# Excludes assets/ (auto-generated analysis sidecars, not wiki pages) and template placeholders
# ([[<run>]], [[<slug>]], [[{...}]], example text). Run after ingest / periodically.
# Usage: bash scripts/lint_docs.sh [docs_dir]
set -u
DOCS="${1:-/home/syaro/MikuchanRemote/Human-Pygmalion/docs}"
cd "$DOCS" || exit 1
echo "=== LLM Wiki lint: $DOCS ==="

mapfile -t FILES < <(find . -name '*.md' -not -path './assets/*' | sed 's|^\./||' | sort)
declare -A EXISTS INBOUND
for f in "${FILES[@]}"; do EXISTS["$(basename "$f" .md)"]=1; done
echo "wiki pages: ${#FILES[@]} (assets/ sidecars excluded)"

dangling=0
while IFS= read -r raw; do
  src="${raw%%:::*}"; link="${raw##*:::}"; link="${link%%|*}"; link="${link%%#*}"
  case "$link" in *"<"*|*">"*|*"{"*|*"..."*|링크|slug|run) continue ;; esac   # skip template placeholders
  key="$(basename "$link")"
  if [ -n "${EXISTS[$key]:-}" ]; then INBOUND["$key"]=1
  else echo "  ⚠ DANGLING [[$link]]  (in $src)"; dangling=$((dangling + 1)); fi
done < <(grep -rEoH '\[\[[^]]+\]\]' . --exclude-dir=assets 2>/dev/null | sed -E 's|^\./||; s|:\[\[|:::|; s|\]\]$||')
echo "dangling links: $dangling"

orphans=0
for f in "${FILES[@]}"; do
  b="$(basename "$f" .md)"
  case "$b" in index|log|SCHEMA|README|INDEX) continue ;; esac
  [ -z "${INBOUND[$b]:-}" ] && { echo "  · orphan (no inbound [[link]]): $f"; orphans=$((orphans + 1)); }
done
echo "orphans: $orphans"
[ "$dangling" -eq 0 ] && [ "$orphans" -eq 0 ] && echo "✅ clean" || echo "→ fix: dangling = rename/create target; orphan = add an inbound [[link]] from [[index]] or a related page"
