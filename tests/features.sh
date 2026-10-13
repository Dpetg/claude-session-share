#!/usr/bin/env bash
# 秘密情報の検出・メモリの共有・古い会話の整理 (prune) の通しテスト
set -euo pipefail
S="$(cd "$(dirname "$0")/../plugins/session-share/scripts" && pwd)/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"; trap 'rm -rf "$T"' EXIT
dev() { local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
enc() { python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-',sys.argv[1]))" "$1"; }
fail() { echo "FAIL: $*"; exit 1; }
git init -q --bare "$T/remote.git"
git init -q "$T/origin" && (cd "$T/origin" && echo hi > a.txt && git add a.txt && git -c user.name=t -c user.email=t@t commit -qm i)
PA="$T/A/home/work/demo"; PB="$T/B/home/src/demo"
mkdir -p "$T/A/home/.claude" "$T/B/home/.claude"
for d in "$PA" "$PB"; do git clone -q "$T/origin" "$d"; git -C "$d" remote set-url origin git@example.com:me/demo.git; done
DA="$T/A/home/.claude/projects/$(enc "$PA")"; DB="$T/B/home/.claude/projects/$(enc "$PB")"
mkdir -p "$DA/memory"
TOKEN="ghp_$(printf 'a%.0s' $(seq 36))"
cat > "$DA/s1.jsonl" <<J
{"type":"user","cwd":"$PA","sessionId":"s1","message":{"role":"user","content":"use token $TOKEN please"},"timestamp":"2026-10-01T00:00:00Z"}
J
cat > "$DA/old.jsonl" <<J
{"type":"user","cwd":"$PA","sessionId":"old","message":{"role":"user","content":"old talk"},"timestamp":"2020-01-01T00:00:00Z"}
J
printf '# memo\n- build: make -C %s\n' "$PA" > "$DA/memory/MEMORY.md"
echo '{"env":{"API_KEY":"'"$TOKEN"'"},"theme":"dark"}' > "$T/A/home/.claude/settings.json"

dev A python3 "$S" init --remote "$T/remote.git" --device devA >/dev/null
OUT=$(cd "$PA" && dev A python3 "$S" push)
echo "$OUT"
echo "$OUT" | grep "秘密情報: s1" >/dev/null || fail "秘密情報の報告が無い"
STORE="$T/A/home/.ccshare/store"
grep -rq "$TOKEN" "$STORE/projects" "$STORE/config" && fail "トークンが共有先に残っている"
grep -q "REDACTED:GitHub" "$STORE/projects/"*/sessions/s1.jsonl || fail "伏せ字になっていない"
grep -q "$TOKEN" "$DA/s1.jsonl" || fail "手元の会話まで書き換えた"
OUT=$(cd "$PA" && dev A python3 "$S" push); echo "$OUT" | grep "セッション 0 件" >/dev/null || fail "伏せ字のせいで毎回送り直している"
(cd "$PA" && dev A python3 "$S" pull) >/dev/null
grep -q "$TOKEN" "$T/A/home/.claude/settings.json" || fail "pull で手元の設定の秘密が伏せ字に置き換わった"

echo "== メモリの共有"
dev B python3 "$S" init --remote "$T/remote.git" --device devB >/dev/null
(cd "$PB" && dev B python3 "$S" pull) | tee "$T/b.txt"
grep -q "メモリ 1 件" "$T/b.txt" || fail "メモリが届かない"
grep -q "make -C $PB" "$DB/memory/MEMORY.md" || fail "メモリのパスが変換されていない"
echo "- from B" >> "$DB/memory/MEMORY.md"
(cd "$PB" && dev B python3 "$S" push --no-settings) >/dev/null
(cd "$PA" && dev A python3 "$S" pull --no-settings) >/dev/null
grep -q "from B" "$DA/memory/MEMORY.md" || fail "B のメモリ追記が A に届かない"
echo "- A side" >> "$DA/memory/MEMORY.md"; echo "- B side" >> "$DB/memory/MEMORY.md"
(cd "$PB" && dev B python3 "$S" push --no-settings) >/dev/null
(cd "$PA" && dev A python3 "$S" pull --no-settings) | grep "メモリが両方で更新" >/dev/null || fail "メモリの競合を報告しない"
test -f "$DA/memory/MEMORY.from-other-device.md" || fail "相手側の版が置かれない"
grep -q "A side" "$DA/memory/MEMORY.md" || fail "手元のメモリが消えた"

echo "== 秘密情報: block"
dev A python3 "$S" secrets block >/dev/null
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"s3","message":{"role":"user","content":"key AKIAABCDEFGHIJKLMNOP"},"timestamp":"2026-10-02T00:00:00Z"}' > "$DA/s3.jsonl"
(cd "$PA" && dev A python3 "$S" push --no-settings) | grep "s3 に AWS アクセスキー 1件 が含まれていたため、送りませんでした" >/dev/null || fail "block で報告しない"
test ! -e "$STORE/projects/"*/sessions/s3.jsonl || fail "block なのに送った"
dev A python3 "$S" secrets mask >/dev/null

echo "== 古い会話の整理"
(cd "$PA" && dev A python3 "$S" prune --older-than 365 --dry-run) | grep "1 件" >/dev/null || fail "dry-run の対象が違う"
ls "$STORE/projects/"*/sessions/old.jsonl >/dev/null || fail "dry-run で消した"
(cd "$PA" && dev A python3 "$S" prune --older-than 365) >/dev/null
ls "$STORE/projects/"*/sessions/old.jsonl >/dev/null 2>&1 && fail "prune で消えていない"
test -f "$DA/old.jsonl" || fail "手元の会話まで消した"
(cd "$PA" && dev A python3 "$S" push --no-settings) >/dev/null
ls "$STORE/projects/"*/sessions/old.jsonl >/dev/null 2>&1 && fail "整理した会話を送り直した"
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"old","message":{"role":"user","content":"resumed"},"timestamp":"2026-10-12T00:00:00Z"}' >> "$DA/old.jsonl"
(cd "$PA" && dev A python3 "$S" push --no-settings) >/dev/null
ls "$STORE/projects/"*/sessions/old.jsonl >/dev/null || fail "続きを書いた会話が共有されない"

echo "== 履歴の作り直し (squash) と他デバイスの追従"
(cd "$PA" && dev A python3 "$S" prune --squash) | tee "$T/sq.txt"
test "$(git -C "$STORE" rev-list --count HEAD)" = 1 || fail "履歴が1つになっていない"
test "$(git --git-dir="$T/remote.git" rev-list --count HEAD)" = 1 || fail "共有先の履歴が作り直されていない"
(cd "$PB" && dev B python3 "$S" pull --no-settings) | tee "$T/b2.txt"
grep -q "履歴が整理されていた" "$T/b2.txt" || fail "B が作り直しに追従しない"
echo "- after squash" >> "$DB/memory/MEMORY.md"
(cd "$PB" && dev B python3 "$S" push --no-settings) >/dev/null
(cd "$PA" && dev A python3 "$S" pull --no-settings) >/dev/null
test "$(git --git-dir="$T/remote.git" rev-list --count HEAD)" -ge 2 || fail "作り直し後に B から送れない"
dev A python3 "$S" status
echo "ALL OK"
