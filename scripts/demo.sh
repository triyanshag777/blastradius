#!/bin/sh
REPO=${REPO_PATH:-../demo_repos/requests}
case "$1" in
  break) python scripts/demo_break.py "$REPO" ;;
  fix)   git -C "$REPO" apply --check "$PWD/blastradius_fixes.patch" && git -C "$REPO" apply "$PWD/blastradius_fixes.patch" && echo "Suggested fixes applied" ;;
  reset) git -C "$REPO" checkout -- . && echo "Demo repo reset" ;;
  *)     echo "usage: scripts/demo.sh break|fix|reset" ;;
esac
