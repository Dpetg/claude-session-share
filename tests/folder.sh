#!/usr/bin/env bash
# クラウドドライブ (同期フォルダ) を共有先にするテスト。同期フォルダは 2 台のホームから同じディレクトリへのリンクで代用する
set -euo pipefail
S="$(cd "$(dirname "$0")/../plugins/session-share/scripts" && pwd)/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"; trap 'rm -rf "$T"' EXIT
dev() { local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  OneDrive= OneDriveConsumer= OneDriveCommercial= \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
enc() { python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-',sys.argv[1]))" "$1"; }
fail() { echo "FAIL: $*"; exit 1; }
git init -q "$T/origin" && (cd "$T/origin" && echo hi > a.txt && git add a.txt && git -c user.name=t -c user.email=t@t commit -qm i)
mkdir -p "$T/cloud"
for n in A B C; do mkdir -p "$T/$n/home/.claude"; ln -s "$T/cloud" "$T/$n/home/Dropbox"; done
PA="$T/A/home/work/demo"; PB="$T/B/home/src/demo"; PC="$T/C/home/demo"
for d in "$PA" "$PB" "$PC"; do git clone -q "$T/origin" "$d"; git -C "$d" remote set-url origin git@example.com:me/demo.git; done
DA="$T/A/home/.claude/projects/$(enc "$PA")"; DB="$T/B/home/.claude/projects/$(enc "$PB")"; DC="$T/C/home/.claude/projects/$(enc "$PC")"
ID=11111111-2222-3333-4444-555555555555
mkdir -p "$DA"
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"'$ID'","message":{"role":"user","content":"hello from A"},"timestamp":"2026-10-14T00:00:00Z"}' > "$DA/$ID.jsonl"
echo '{"theme":"dark"}' > "$T/A/home/.claude/settings.json"

echo "== 同期フォルダを見つける"
(dev A python3 "$S" drives) | grep "Dropbox" >/dev/null || fail "Dropbox が見つからない"

echo "== 1台目: setup dropbox"
OUT=$(cd "$PA" && dev A python3 "$S" setup dropbox 2>&1); echo "$OUT"
echo "$OUT" | grep "1台目" >/dev/null || fail "1台目として送っていない"
STORE="$T/cloud/claude-sessions"
test -f "$STORE/config/settings.json" || fail "設定が同期フォルダに無い"
ls "$STORE/projects/"*/sessions/$ID.jsonl >/dev/null || fail "会話が同期フォルダに無い"
test ! -e "$STORE/.git" || fail "同期フォルダに git リポジトリを作った"
ls -a "$STORE/projects/"*/sessions | grep ccshare-tmp >/dev/null && fail "一時ファイルが残っている"

echo "== 2台目: setup dropbox で取り込む"
OUT=$(cd "$PB" && dev B python3 "$S" setup dropbox 2>&1); echo "$OUT"
echo "$OUT" | grep "2台目以降" >/dev/null || fail "2台目として取り込んでいない"
grep "hello from A" "$DB/$ID.jsonl" >/dev/null || fail "会話が届かない"
grep "\"cwd\":\"$PB\"" "$DB/$ID.jsonl" >/dev/null || fail "パスが変換されていない"
grep dark "$T/B/home/.claude/settings.json" >/dev/null || fail "設定が届かない"

echo "== 同期の途中のファイルは取り込まない"
ID2=22222222-2222-3333-4444-555555555555
SD=$(echo "$STORE"/projects/*/sessions)
printf '{"type":"user","cwd":"{{CCSHARE_PROJECT}}","sessionId":"%s","message":{"role":"user","content":"partial"}' "$ID2" > "$SD/$ID2.jsonl"
(cd "$PB" && dev B python3 "$S" pull --no-settings) >/dev/null
test ! -e "$DB/$ID2.jsonl" || fail "書きかけの会話を取り込んだ"
rm "$SD/$ID2.jsonl"

echo "== クラウドドライブの競合コピーは別セッションとして取り込む"
sed 's/hello from A/edited elsewhere/' "$SD/$ID.jsonl" > "$SD/$ID (1).jsonl"
OUT=$(cd "$PB" && dev B python3 "$S" pull --no-settings); echo "$OUT"
echo "$OUT" | grep "競合: $ID" >/dev/null || fail "競合コピーを報告しない"
grep -l "edited elsewhere" "$DB"/*.jsonl | grep -v "$ID.jsonl" >/dev/null || fail "競合コピーが別セッションになっていない"
grep "hello from A" "$DB/$ID.jsonl" >/dev/null || fail "元の会話が書き換わった"
OUT=$(cd "$PB" && dev B python3 "$S" pull --no-settings)
echo "$OUT" | grep "競合" >/dev/null && fail "同じ競合コピーを何度も取り込む"
(cd "$PB" && dev B python3 "$S" list) | grep "$ID (1)" >/dev/null && fail "競合コピーが一覧に出る"
rm "$SD/$ID (1).jsonl"

echo "== GitHub 等の git から同期フォルダへ引っ越す"
rm -rf "$T/cloud/claude-sessions"
git init -q --bare "$T/remote.git"
mkdir -p "$DC"
echo '{"type":"user","cwd":"'"$PC"'","sessionId":"'$ID'","message":{"role":"user","content":"from C via git"},"timestamp":"2026-10-14T00:00:00Z"}' > "$DC/$ID.jsonl"
(cd "$PC" && dev C python3 "$S" setup "file://$T/remote.git" --no-auto) >/dev/null
OUT=$(cd "$PC" && dev C python3 "$S" setup dropbox --no-auto 2>&1); echo "$OUT"
echo "$OUT" | grep "前の共有先 ($T/C/home/.ccshare/store)" >/dev/null || fail "引っ越しを報告しない"
grep "from C via git" "$T/cloud/claude-sessions/projects/"*/sessions/$ID.jsonl >/dev/null || fail "会話が引っ越していない"
OUT=$(cd "$PC" && dev C python3 "$S" status); echo "$OUT" | grep "folder" >/dev/null || fail "共有先が切り替わっていない"
echo "OK: folder"
