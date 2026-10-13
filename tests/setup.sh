#!/usr/bin/env bash
# setup (引数なし: gh で private リポジトリを用意) の通しテスト。gh は偽物、GitHub はローカルの bare リポジトリで代用する
set -euo pipefail
S="$(cd "$(dirname "$0")/../plugins/session-share/scripts" && pwd)/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"; trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*"; exit 1; }
mkdir -p "$T/gh/me" "$T/bin"
cat > "$T/bin/gh" <<GH
#!/usr/bin/env bash
echo "\$*" >> "$T/gh.log"
case "\$1 \$2" in
  "auth status") exit 0 ;;
  "auth setup-git") exit 0 ;;
  "api user") echo me ;;
  "repo view") repo="$T/gh/\$3.git"; [ -d "\$repo" ] || exit 1; cat "\$repo/visibility" ;;
  "repo create") repo="$T/gh/\$3.git"; git init -q --bare "\$repo"; [ "\$4" = --private ] && echo PRIVATE > "\$repo/visibility" ;;
  *) exit 2 ;;
esac
GH
chmod +x "$T/bin/gh"
printf '[url "file://%s/gh/"]\n\tinsteadOf = https://github.com/\n' "$T" > "$T/gitconfig"
dev() { local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  CCSHARE_GH="$T/bin/gh" GIT_CONFIG_GLOBAL="$T/gitconfig" \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
mkdir -p "$T/A/home/.claude" "$T/B/home/.claude"
echo '{"theme":"dark"}' > "$T/A/home/.claude/settings.json"

echo "== 1台目: リポジトリを作って送る"
OUT=$(cd "$T/A/home" && dev A python3 "$S" setup 2>&1); echo "$OUT"
echo "$OUT" | grep "private リポジトリ me/claude-sessions を作りました" >/dev/null || fail "リポジトリを作っていない"
echo "$OUT" | grep "1台目" >/dev/null || fail "1台目として送っていない"
echo "$OUT" | grep "自動同期: オン" >/dev/null || fail "自動同期がオンにならない"
grep "repo create me/claude-sessions --private" "$T/gh.log" >/dev/null || fail "private で作っていない"
git --git-dir="$T/gh/me/claude-sessions.git" show HEAD:config/settings.json | grep dark >/dev/null || fail "設定が届いていない"

echo "== 2台目: 同じコマンドで既存のリポジトリから取り込む"
OUT=$(cd "$T/B/home" && dev B python3 "$S" setup 2>&1); echo "$OUT"
echo "$OUT" | grep "既存の private リポジトリ me/claude-sessions を使います" >/dev/null || fail "既存のリポジトリを使っていない"
echo "$OUT" | grep "2台目以降" >/dev/null || fail "2台目として取り込んでいない"
grep dark "$T/B/home/.claude/settings.json" >/dev/null || fail "設定が取り込まれていない"

echo "== 設定済みなら何も作り直さない / public のリポジトリは使わない"
OUT=$(cd "$T/B/home" && dev B python3 "$S" setup --no-auto 2>&1)
echo "$OUT" | grep "設定済み" >/dev/null || fail "設定済みと表示しない"
git init -q --bare "$T/gh/me/open.git"; echo PUBLIC > "$T/gh/me/open.git/visibility"
OUT=$(cd "$T/A/home" && CCSHARE_DIR="$T/C" dev A python3 "$S" setup me/open 2>&1 || true)
echo "$OUT" | grep "private ではありません" >/dev/null || fail "public のリポジトリを拒否しない"
echo "OK: setup"
