#!/bin/sh
# Prepare this project for GitHub: fill in your details, run safety checks, make the first commit,
# and (optionally) create the GitHub repository and push.
#
#   scripts/publish.sh "Your Name" your-github-username [repo-name] [--push]
#
# Without --push it only prepares the repo locally and prints the commands for the rest.
# With --push it uses the GitHub CLI (`gh`, already logged in) to create a public repo and push.
set -eu

PUSH=0
# Pull --push out of the arguments while keeping the others intact (names may contain spaces).
for a in "$@"; do
  shift
  if [ "$a" = "--push" ]; then PUSH=1; else set -- "$@" "$a"; fi
done

if [ "$#" -lt 2 ]; then
  echo 'Usage: scripts/publish.sh "Your Name" your-github-username [repo-name] [--push]' >&2
  exit 2
fi
NAME="$1"; USER_NAME="$2"; REPO="${3:-verity}"

cd "$(dirname "$0")/.."
say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---- 1. fill in the placeholders (README badge + LICENSE only) ---------------------------------
for f in README.md LICENSE; do
  [ -f "$f" ] || die "$f is missing"
  sed -i.bak -e "s#YOUR_USERNAME/verity#$USER_NAME/$REPO#g" -e "s#YOUR_USERNAME#$USER_NAME#g" -e "s#YOUR NAME#$NAME#g" "$f"
  rm -f "$f.bak"
done
if grep -n "YOUR_USERNAME\|YOUR NAME" README.md LICENSE >/dev/null 2>&1; then die "placeholders are still present in README.md or LICENSE"; fi
say "[1/4] Filled in your name and username (README badge, LICENSE)."

# ---- 2. safety checks: never publish a secret --------------------------------------------------
# a) anything shaped like an API key in files that would be committed
LEAKS=$(grep -rIlE "sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}" . \
        --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude=.env 2>/dev/null || true)
[ -z "$LEAKS" ] || die "something that looks like a secret key was found in: $LEAKS"
say "[2/4] No API-key-shaped strings found."

# ---- 3. git: init, verify what would be committed, commit -------------------------------------
[ -d .git ] || git init -q -b main
if ! git config user.name >/dev/null 2>&1; then git config user.name "$NAME"; fi
if ! git config user.email >/dev/null 2>&1; then git config user.email "$USER_NAME@users.noreply.github.com"; fi
git add -A
BAD=$(git ls-files | grep -E '(^|/)\.env$|(^|/)node_modules/|(^|/)dist/|\.zip$' || true)
if [ -n "$BAD" ]; then git rm -rq --cached . >/dev/null 2>&1 || true; die "these files must not be committed: $BAD"; fi
COUNT=$(git ls-files | wc -l | tr -d ' ')
if git diff --cached --quiet; then
  say "[3/4] Nothing new to commit ($COUNT files already tracked)."
else
  git commit -q -m "Verity: AI data analyst that executes and verifies SQL"
  say "[3/4] Committed $COUNT files on branch main."
fi

# ---- 4. GitHub --------------------------------------------------------------------------------
if [ "$PUSH" -eq 1 ]; then
  command -v gh >/dev/null 2>&1 || die "--push needs the GitHub CLI: https://cli.github.com  (then run: gh auth login)"
  gh auth status >/dev/null 2>&1 || die "the GitHub CLI is not logged in. Run: gh auth login"
  gh repo create "$USER_NAME/$REPO" --public --source . --remote origin --push \
     --description "AI data analyst that writes SQL, runs it read-only, and verifies the answer against a known result."
  gh repo edit "$USER_NAME/$REPO" \
     --add-topic text-to-sql --add-topic llm --add-topic fastapi --add-topic react --add-topic postgresql \
     --add-topic sqlglot --add-topic evaluation --add-topic ai-safety >/dev/null 2>&1 || say "  (could not set topics automatically; add them in the repo settings)"
  say "[4/4] Pushed: https://github.com/$USER_NAME/$REPO"
else
  say "[4/4] Local repo is ready. To publish, either re-run this script with --push, or:"
  say "      git remote add origin git@github.com:$USER_NAME/$REPO.git"
  say "      git push -u origin main"
fi

say ""
say "Still manual (see docs/PUSH_TO_GITHUB.md): confirm the first CI run is green, add repo topics if they were"
say "not set, and optionally set the social preview image to docs/screenshots/03-answer-and-proof.png."
