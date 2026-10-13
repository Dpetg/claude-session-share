#!/usr/bin/env bash
# Python 3.8+ を探して ccshare.py を実行する (Windows の Git Bash / macOS / Linux 共通)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    PYTHONIOENCODING=utf-8 exec "$py" "$DIR/ccshare.py" "$@"
  fi
done
echo "session-share: Python 3.8 以上が見つかりません。インストールしてから再実行してください。" >&2
[ "$1" = "hook" ] && exit 0
exit 1
