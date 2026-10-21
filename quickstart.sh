#!/usr/bin/env bash
# ==============================================================================
# Crewloom Zero-Friction Developer Quickstart Script
# ==============================================================================
# Cross-platform: macOS (Bash 3.2+) and Linux (Bash 3.2+, 4.x, 5.x, POSIX)
# Capabilities:
#   - Detects prerequisites: Python >= 3.9, Git, Docker, Node.js
#   - Validates repository integrity and the installed role catalog
#   - Supports: --dry-run, --demo, --fast, --no-demo, --help
#   - Zero external API keys required; safe and non-destructive
# ==============================================================================

set -euo pipefail

# Anchor to the repository root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

DRY_RUN=0
RUN_DEMO=1
FAST_MODE=0

# Terminal styling (disabled when non-interactive, NO_COLOR is set, or TERM=dumb)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != "dumb" ]; then
  BOLD="\033[1m"
  DIM="\033[2m"
  GREEN="\033[0;32m"
  CYAN="\033[0;36m"
  YELLOW="\033[0;33m"
  RED="\033[0;31m"
  RESET="\033[0m"
else
  BOLD=""
  DIM=""
  GREEN=""
  CYAN=""
  YELLOW=""
  RED=""
  RESET=""
fi

usage() {
  cat <<'EOF'
Crewloom Quickstart — Zero-friction developer onboarding

Usage: ./quickstart.sh [OPTIONS]

Options:
  -n, --dry-run     Validate prerequisites, detected paths, and repo status without running commands (exit 0)
  -d, --demo        Execute interactive 20-second CLI walkthrough after checks (default)
  -f, --fast        Run walkthrough in accelerated mode (bypass sleep pauses, <0.5s)
  --no-demo         Perform environment checks and reporting only (skip walkthrough)
  -h, --help        Show this help message and exit

Prerequisites Detected:
  • Python >= 3.9   Required for CLI and role execution
  • Git             Required for repository tracking and privacy index
  • Docker          Optional (required for verified isolated container execution)
  • Node.js 24+ / npm Optional (required for live web dashboard)

Examples:
  ./quickstart.sh                 # Run checks and interactive walkthrough
  ./quickstart.sh --dry-run       # Check environment without running commands
  ./quickstart.sh --demo --fast   # Run checks and fast walkthrough (ideal for CI)
EOF
}

# Parse command line options
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run)
      DRY_RUN=1
      RUN_DEMO=0
      shift
      ;;
    -d|--demo)
      RUN_DEMO=1
      shift
      ;;
    -f|--fast)
      FAST_MODE=1
      shift
      ;;
    --no-demo)
      RUN_DEMO=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      printf "${RED}Error: Unknown option: %s${RESET}\n" "$1" >&2
      printf "Run '%s --help' for available options.\n" "$0" >&2
      exit 1
      ;;
    *)
      printf "${RED}Error: Unexpected argument: %s${RESET}\n" "$1" >&2
      printf "Run '%s --help' for available options.\n" "$0" >&2
      exit 1
      ;;
  esac
done

# Allow environment variables to configure execution in automated test runners
if [ -n "${DRY_RUN_ENV:-}" ]; then
  DRY_RUN=1
  RUN_DEMO=0
fi

if [ -n "${CREWLOOM_DEMO_FAST:-}" ]; then
  FAST_MODE=1
fi

printf "${BOLD}${CYAN}=== Crewloom Quickstart Environment Check ===${RESET}\n"

# 1. Operating System & Architecture Detection
OS="$(uname -s 2>/dev/null || echo "Unknown")"
ARCH="$(uname -m 2>/dev/null || echo "Unknown")"

case "$OS" in
  Darwin)
    OS_NAME="macOS"
    OS_VER="$(sw_vers -productVersion 2>/dev/null || echo "")"
    if [ -n "$OS_VER" ]; then
      OS_DISPLAY="macOS ${OS_VER}"
    else
      OS_DISPLAY="macOS"
    fi
    ;;
  Linux)
    OS_NAME="Linux"
    if [ -f /etc/os-release ]; then
      DISTRO="$(grep -E '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "")"
      if [ -n "$DISTRO" ]; then
        OS_DISPLAY="Linux (${DISTRO})"
      else
        OS_DISPLAY="Linux"
      fi
    else
      OS_DISPLAY="Linux"
    fi
    ;;
  *)
    OS_NAME="$OS"
    OS_DISPLAY="$OS"
    ;;
esac

printf "${GREEN}[✓]${RESET} Operating System: %s (%s)\n" "$OS_DISPLAY" "$ARCH"

# 2. Python Detection (>= 3.9 required)
PY_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PY_CMD="python"
fi

if [ -z "$PY_CMD" ]; then
  printf "${RED}[✗] Python: not found in PATH${RESET}\n" >&2
  printf "    Crewloom requires Python >= 3.9.\n" >&2
  printf "    Please install Python 3.9 or higher and ensure it is available in PATH.\n" >&2
  exit 1
fi

PY_PATH="$(command -v "$PY_CMD")"
PY_VER="$("$PY_CMD" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo "")"

if [ -z "$PY_VER" ]; then
  printf "${RED}[✗] Python: failed to query version from %s${RESET}\n" "$PY_PATH" >&2
  exit 1
fi

PY_CHECK="$("$PY_CMD" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && echo "OK" || echo "FAIL")"

if [ "$PY_CHECK" != "OK" ]; then
  printf "${RED}[✗] Python: version %s detected at %s${RESET}\n" "$PY_VER" "$PY_PATH" >&2
  printf "    Crewloom requires Python >= 3.9. Found version: %s\n" "$PY_VER" >&2
  printf "    Please upgrade Python to >= 3.9.\n" >&2
  exit 1
fi

printf "${GREEN}[✓]${RESET} Python: %s (v%s, requirement >= 3.9 satisfied)\n" "$PY_PATH" "$PY_VER"

# 3. Git Detection
if command -v git >/dev/null 2>&1; then
  GIT_PATH="$(command -v git)"
  GIT_VER="$(git --version 2>/dev/null | head -n 1 || echo "installed")"
  printf "${GREEN}[✓]${RESET} Git: %s (%s)\n" "$GIT_PATH" "$GIT_VER"
else
  printf "${RED}[✗] Git: not found in PATH${RESET}\n" >&2
  printf "    Crewloom requires Git for repository-native role management and privacy guards.\n" >&2
  printf "    Please install Git to continue.\n" >&2
  exit 1
fi

if [ -d ".git" ] || [ -f ".git" ]; then
  GIT_REPO_STATUS="valid repository"
else
  GIT_REPO_STATUS="standalone tree"
fi

# 4. Docker Detection (Optional / Recommended for Container Isolation)
if command -v docker >/dev/null 2>&1; then
  DOCKER_PATH="$(command -v docker)"
  DOCKER_VER="$(docker --version 2>/dev/null | head -n 1 || echo "installed")"
  if docker info >/dev/null 2>&1; then
    printf "${GREEN}[✓]${RESET} Docker: %s (%s, daemon active)\n" "$DOCKER_PATH" "$DOCKER_VER"
  else
    printf "${YELLOW}[!]${RESET} Docker: %s (daemon inactive - isolated container execution unavailable)\n" "$DOCKER_PATH"
  fi
else
  printf "${YELLOW}[!]${RESET} Docker: not found in PATH (optional - required only for isolated container execution)\n"
fi

# 5. Node.js & npm Detection (Optional for Web Dashboard)
NODE_FOUND=0
NPM_FOUND=0
NODE_INFO=""

if command -v node >/dev/null 2>&1; then
  NODE_FOUND=1
  NODE_PATH="$(command -v node)"
  NODE_VER="$(node --version 2>/dev/null || echo "")"
  NODE_INFO="${NODE_PATH} (${NODE_VER})"
fi

if command -v npm >/dev/null 2>&1; then
  NPM_FOUND=1
  NPM_VER="$(npm --version 2>/dev/null || echo "")"
fi

if [ "$NODE_FOUND" -eq 1 ] && [ "$NPM_FOUND" -eq 1 ]; then
  NODE_MAJOR="${NODE_VER#v}"
  NODE_MAJOR="${NODE_MAJOR%%.*}"
  case "$NODE_MAJOR" in
    ''|*[!0-9]*)
      printf "${YELLOW}[!]${RESET} Node.js: %s (version unknown; dashboard requires Node 24+)\n" "$NODE_INFO"
      ;;
    *)
      if [ "$NODE_MAJOR" -ge 24 ]; then
        printf "${GREEN}[✓]${RESET} Node.js: %s, npm v%s (dashboard ready)\n" "$NODE_INFO" "$NPM_VER"
      else
        printf "${YELLOW}[!]${RESET} Node.js: %s (dashboard requires Node 24+; core CLI remains available)\n" "$NODE_INFO"
      fi
      ;;
  esac
elif [ "$NODE_FOUND" -eq 1 ]; then
  printf "${GREEN}[✓]${RESET} Node.js: %s (npm not found)\n" "$NODE_INFO"
else
  printf "${YELLOW}[!]${RESET} Node.js: not found in PATH (optional - required only for 'crewloom dashboard')\n"
fi

# 6. Repository Integrity & Role Catalog Verification
if [ ! -f "scripts/crewloom.py" ]; then
  printf "${RED}[✗] Repository Error: scripts/crewloom.py not found at %s${RESET}\n" "$PWD" >&2
  exit 1
fi

if [ ! -f "REPOSITORY_SCOPE.json" ]; then
  printf "${RED}[✗] Repository Error: REPOSITORY_SCOPE.json not found${RESET}\n" >&2
  exit 1
fi

ROLE_COUNT="$("$PY_CMD" scripts/crewloom.py list 2>/dev/null | grep -c '^[a-z]' || echo "0")"
if [ "$ROLE_COUNT" -gt 0 ]; then
  printf "${GREEN}[✓]${RESET} Role Catalog: %s specialist roles available (.agents/skills)\n" "$ROLE_COUNT"
else
  printf "${YELLOW}[!]${RESET} Role Catalog: could not enumerate catalog roles\n"
fi

# 7. Dry-Run Handling
if [ "$DRY_RUN" -eq 1 ]; then
  printf "\n${BOLD}${GREEN}=== Dry-Run Completed Successfully ===${RESET}\n"
  printf "Prerequisites and repository validation passed. No modifications were made.\n"
  printf "Repository Root:  %s\n" "$PWD"
  printf "Python Binary:    %s\n" "$PY_PATH"
  printf "Roles Verified:   %s roles\n" "$ROLE_COUNT"
  printf "Git Status:       %s\n" "$GIT_REPO_STATUS"
  exit 0
fi

# 8. Interactive Demo Launch
if [ "$RUN_DEMO" -eq 1 ]; then
  printf "\n${BOLD}${CYAN}=== Launching Crewloom Interactive Demo ===${RESET}\n"
  if [ "$FAST_MODE" -eq 1 ]; then
    exec "$PY_CMD" scripts/crewloom.py demo --fast
  else
    exec "$PY_CMD" scripts/crewloom.py demo
  fi
fi

# 9. Clean Exit for --no-demo Mode
printf "\n${BOLD}${GREEN}=== Crewloom is Ready ===${RESET}\n"
printf "Run the interactive CLI demo:  ./quickstart.sh --demo\n"
printf "Run the fast demo (CI mode):   ./quickstart.sh --demo --fast\n"
printf "Explore specialist roles:      %s scripts/crewloom.py list\n" "$PY_CMD"
printf "Validate repository gates:     %s scripts/check_repository.py\n" "$PY_CMD"
exit 0
