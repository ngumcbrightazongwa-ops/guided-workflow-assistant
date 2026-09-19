#!/usr/bin/env sh
# Installs the Guided Workflow Assistant skill for Claude Code (macOS / Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/ngumcbrightazongwa-ops/guided-workflow-assistant/main/install.sh | sh
#
# Or, from a clone of the repository:   ./install.sh
# For one project only:                 ./install.sh /path/to/project
#
# Created by Aneta Prime. MIT licence.

set -eu

NAME="guided-workflow-assistant"
TARBALL="https://github.com/ngumcbrightazongwa-ops/$NAME/archive/refs/heads/main.tar.gz"

if [ "${1:-}" != "" ]; then
    TARGET="$1/.claude/skills"
else
    TARGET="$HOME/.claude/skills"
fi
mkdir -p "$TARGET"

# Use the copy next to this script when run from a clone; otherwise download it.
HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
TEMP=""

if [ -n "$HERE" ] && [ -f "$HERE/$NAME/SKILL.md" ]; then
    SOURCE="$HERE/$NAME"
else
    TEMP="$(mktemp -d)"
    curl -fsSL "$TARBALL" | tar -xz -C "$TEMP"
    SOURCE="$TEMP/$NAME-main/$NAME"
fi

rm -rf "$TARGET/$NAME"
cp -R "$SOURCE" "$TARGET/$NAME"

[ -n "$TEMP" ] && rm -rf "$TEMP"

echo "Installed $NAME to $TARGET/$NAME"
echo "Restart Claude Code, then ask for a guided workflow assistant or run /$NAME."
