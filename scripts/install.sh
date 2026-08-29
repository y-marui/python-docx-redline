#!/usr/bin/env bash
# dev-charter quick installer
#
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/y-marui/dev-charter/main/scripts/install.sh)
#
# Environment variables (all optional):
#   CHARTER_REMOTE   git remote name          (default: dev-charter)
#   CHARTER_URL      repository URL           (default: https://github.com/y-marui/dev-charter)
#   CHARTER_PREFIX   install directory        (default: docs/dev-charter)
#   CHARTER_BRANCH   branch to install from   (default: main)

set -euo pipefail

REMOTE_NAME="${CHARTER_REMOTE:-dev-charter}"
REMOTE_URL="${CHARTER_URL:-https://github.com/y-marui/dev-charter}"
PREFIX="${CHARTER_PREFIX:-docs/dev-charter}"
BRANCH="${CHARTER_BRANCH:-main}"

# 1. Verify we are inside a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: not in a git repository. Run this script from your project root." >&2
    exit 1
fi

# 2. Skip if already installed
if [ -d "$PREFIX" ]; then
    # Detect the already-installed variant from CHARTER_INDEX.md instead of
    # trusting CHARTER_BRANCH (defaults to "main"), so re-running this script
    # against an existing lite install without re-passing CHARTER_BRANCH=lite
    # doesn't print instructions that would silently switch it to full.
    INSTALLED_BRANCH="main"
    if [ -f "$PREFIX/CHARTER_INDEX.md" ] && grep -q '(lite)' "$PREFIX/CHARTER_INDEX.md"; then
        INSTALLED_BRANCH="lite"
    fi
    if [ -n "${CHARTER_BRANCH:-}" ] && [ "$CHARTER_BRANCH" != "$INSTALLED_BRANCH" ]; then
        echo "Warning: $PREFIX looks like the '$INSTALLED_BRANCH' variant, but CHARTER_BRANCH=$CHARTER_BRANCH was given." >&2
        echo "  Using '$INSTALLED_BRANCH' (the installed variant) to avoid an accidental full/lite switch." >&2
    fi
    BRANCH="$INSTALLED_BRANCH"

    echo "dev-charter is already installed at $PREFIX ($BRANCH)."
    echo "To update, run:"
    printf "  git remote | grep -q '%s' || git remote add '%s' '%s'\n" \
        "$REMOTE_NAME" "$REMOTE_NAME" "$REMOTE_URL"
    printf "  git subtree pull --prefix=%s %s %s --squash\n" \
        "$PREFIX" "$REMOTE_NAME" "$BRANCH"
    exit 0
fi

# 3. Add remote if not present
if ! git remote get-url "$REMOTE_NAME" > /dev/null 2>&1; then
    echo "Adding remote '$REMOTE_NAME'..."
    git remote add "$REMOTE_NAME" "$REMOTE_URL"
fi

# 4. Fetch
echo "Fetching $REMOTE_NAME..."
git fetch "$REMOTE_NAME"

# 5. Install via git subtree
echo "Installing dev-charter to $PREFIX..."
git subtree add --prefix="$PREFIX" "$REMOTE_NAME" "$BRANCH" --squash

# 6. Success message + prompt examples
# lite には INSTALL_CHECKLIST.md がない（full 専用ファイルのため
# scripts/lite-manifest.txt で除外）ので、branch ごとにプロンプトを変える。
if [ "$BRANCH" = "main" ]; then
    NEXT_PROMPT="${PREFIX}/INSTALL_CHECKLIST.md を実行して"
    NEXT_PROMPT_EN="Run ${PREFIX}/INSTALL_CHECKLIST.md"
else
    NEXT_PROMPT="${PREFIX}/CHARTER_INDEX.md を読み、このプロジェクトに合わせて AI_CONTEXT.md 等を構成して"
    NEXT_PROMPT_EN="Read ${PREFIX}/CHARTER_INDEX.md and set up AI_CONTEXT.md etc. for this project"
fi

cat <<EOF

dev-charter installed at $PREFIX

Next — paste this prompt into your AI tool (Claude Code, Copilot, Gemini, etc.):

  $NEXT_PROMPT
  (English: $NEXT_PROMPT_EN)

EOF

# 7. Offer to launch Claude Code if available
if command -v claude > /dev/null 2>&1; then
    if [ -t 0 ]; then
        printf "Launch Claude Code now to run the setup? [Y/n] "
        read -r answer
        case "${answer:-Y}" in
            [Yy]*|"")
                exec claude "$NEXT_PROMPT"
                ;;
            *)
                printf "\nTo start setup later, run:\n"
                printf "  claude \"%s\"\n" "$NEXT_PROMPT"
                ;;
        esac
    else
        printf "Tip: launch Claude Code to start setup:\n"
        printf "  claude \"%s\"\n" "$NEXT_PROMPT"
    fi
fi
