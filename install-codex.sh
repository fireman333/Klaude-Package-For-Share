#!/usr/bin/env bash
# Install skills from this repo into OpenAI Codex (~/.agents/skills).
# Usage: bash install-codex.sh [plugin ...]   (default: all plugins)
# Rewrites ${CLAUDE_SKILL_DIR} to the installed absolute path, since Codex does not expand it.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="${CODEX_SKILLS_DIR:-$HOME/.agents/skills}"
mkdir -p "$DEST"
plugins=("$@")
if [ ${#plugins[@]} -eq 0 ]; then
  plugins=($(ls "$REPO/plugins"))
fi
for p in "${plugins[@]}"; do
  for skill in "$REPO/plugins/$p/skills"/*/; do
    name="$(basename "$skill")"
    target="$DEST/$name"
    if [ -e "$target" ]; then
      echo "skip  $name (already exists at $target)"
      continue
    fi
    cp -R "$skill" "$target"
    find "$target" -type f \( -name '*.md' -o -name '*.txt' \) -print0 |
      xargs -0 perl -pi -e "s#\\\$\\{CLAUDE_SKILL_DIR\\}#$target#g; s#\\\$\\{CLAUDE_PLUGIN_ROOT\\}#$target/..#g"
    echo "ok    $name -> $target"
  done
done
echo "Done. Restart Codex to load the new skills."
