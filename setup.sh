#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# setup.sh · open Claude Code in the hyline-intelligence repo
# Run from inside the repo:  bash setup.sh
# ─────────────────────────────────────────────────────────────

set -e

YELLOW="\033[33m"
GREEN="\033[32m"
RED="\033[31m"
BOLD="\033[1m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}HYLINE Intelligence · Claude Code setup${RESET}"
echo "────────────────────────────────────────"

# 1. Node.js check
if ! command -v node &> /dev/null; then
  echo -e "${RED}✗ Node.js not found.${RESET}"
  echo "  Install from https://nodejs.org (version 18 or later)."
  exit 1
fi

NODE_MAJOR=$(node -v | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo -e "${RED}✗ Node.js 18+ required (you have $(node -v)).${RESET}"
  exit 1
fi
echo -e "${GREEN}✓${RESET} Node.js $(node -v)"

# 2. npm prefix check (avoids the EACCES sudo trap)
NPM_PREFIX=$(npm config get prefix)
if [ "$NPM_PREFIX" = "/usr/local" ] || [ "$NPM_PREFIX" = "/usr" ]; then
  echo -e "${YELLOW}⚠${RESET} npm global prefix is system-wide ($NPM_PREFIX)."
  echo "  Fixing to use ~/.npm-global (no sudo needed)..."
  mkdir -p ~/.npm-global
  npm config set prefix ~/.npm-global
  case ":$PATH:" in
    *":$HOME/.npm-global/bin:"*) ;;
    *)
      echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.zshrc 2>/dev/null || true
      echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc 2>/dev/null || true
      export PATH="$HOME/.npm-global/bin:$PATH"
      echo -e "${GREEN}✓${RESET} Added ~/.npm-global/bin to PATH"
      ;;
  esac
fi

# 3. Install or upgrade Claude Code
if ! command -v claude &> /dev/null; then
  echo "Installing @anthropic-ai/claude-code..."
  npm install -g @anthropic-ai/claude-code@latest
else
  CURRENT=$(claude --version 2>/dev/null || echo "unknown")
  echo -e "${GREEN}✓${RESET} Claude Code already installed ($CURRENT)"
  read -p "  Upgrade to latest? [y/N] " yn
  case $yn in
    [Yy]*) npm install -g @anthropic-ai/claude-code@latest ;;
  esac
fi

CLAUDE_VERSION=$(claude --version)
echo -e "${GREEN}✓${RESET} Claude Code: $CLAUDE_VERSION"

# 4. Verify CLAUDE.md is present
if [ ! -f "CLAUDE.md" ]; then
  echo -e "${RED}✗ CLAUDE.md missing in $(pwd).${RESET}"
  echo "  Make sure you ran this from the repo root."
  exit 1
fi
echo -e "${GREEN}✓${RESET} CLAUDE.md present"

# 5. Done — print the first prompt and open Claude Code
echo ""
echo "────────────────────────────────────────"
echo -e "${BOLD}Ready.${RESET} Copy this as the first message:"
echo ""
echo -e "${YELLOW}┌─${RESET}"
echo -e "${YELLOW}│${RESET} Read CLAUDE.md and STRATEGY.md fully before anything else."
echo -e "${YELLOW}│${RESET} Confirm you understood the 15 hard limits in CLAUDE.md §3."
echo -e "${YELLOW}│${RESET} Then reply with ONLY:"
echo -e "${YELLOW}│${RESET}     \"CLAUDE.md read · 17 sections · STRATEGY.md read · ready.\""
echo -e "${YELLOW}└─${RESET}"
echo ""
echo "Opening Claude Code in $(pwd)..."
echo ""

claude
