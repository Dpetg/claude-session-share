#!/usr/bin/env bash
# 2台のデバイス (ホーム・プロジェクトのパスが異なる) を模した通しテスト
set -euo pipefail
S="$(cd "$(dirname "$0")/../plugins/session-share/scripts" && pwd)/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"; trap 'rm -rf "$T"' EXIT
git init -q --bare "$T/remote.git"
git init -q "$T/origin" && (cd "$T/origin" && echo hello > a.txt && echo 'SECRET=1' > .env && git add a.txt && git -c user.name=t -c user.email=t@t commit -qm init && git remote add origin https://github.com/Dpetg/demo.git)
dev() { # dev <name> <cmd...>
  local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"
}
PA="$T/A/home/work/demo"; PB="$T/B/home/src/demo-checkout"
mkdir -p "$T/A/home" "$T/B/home/src"
git clone -q "$T/origin" "$PA"; git clone -q "$T/origin" "$PB"
for d in "$PA" "$PB"; do git -C "$d" remote set-url origin https://github.com/Dpetg/demo.git; done
# デバイスAで会話を1つ作る
ENC=$(python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-',sys.argv[1]))" "$PA")
mkdir -p "$T/A/home/.claude/projects/$ENC/s1/subagents"
cat > "$T/A/home/.claude/projects/$ENC/s1.jsonl" <<J
{"type":"user","cwd":"$PA","sessionId":"s1","message":{"role":"user","content":"read $PA/a.txt and $PA-old/x"},"timestamp":"2026-10-13T00:00:00Z"}
{"type":"assistant","cwd":"$PA","sessionId":"s1","message":{"role":"assistant","content":[{"type":"tool_use","input":{"file_path":"$PA/a.txt"}}]},"timestamp":"2026-10-13T00:00:01Z"}
J
echo '{"cwd":"'"$PA"'","sessionId":"s1"}' > "$T/A/home/.claude/projects/$ENC/s1/subagents/agent-1.jsonl"
echo '{"model":"opus","statusLine":{"type":"command","command":"'"$T/A/home"'/bin/sl.sh"}}' > "$T/A/home/.claude/settings.json"
mkdir -p "$T/A/home/.claude/agents"; echo "# reviewer" > "$T/A/home/.claude/agents/reviewer.md"

echo "== A: init / push"
dev A python3 "$S" init --store "$T/A/home/.ccshare/store" --remote "$T/remote.git" --device devA
(cd "$PA" && dev A python3 "$S" push)
echo "== B: init / pull"
dev B python3 "$S" init --store "$T/B/home/.ccshare/store" --remote "$T/remote.git" --device devB
echo changed > "$PB/a.txt"; echo 'SECRET=2' > "$PB/.env"
(cd "$PB" && dev B python3 "$S" pull) | tee "$T/pull.txt"
ENCB=$(python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-',sys.argv[1]))" "$PB")
F="$T/B/home/.claude/projects/$ENCB/s1.jsonl"
test -f "$F" || { echo "FAIL: B にセッションが無い"; exit 1; }
grep -q "\"cwd\":\"$PB\"" "$F" || { echo "FAIL: cwd 未変換"; exit 1; }
grep -q "$PB/a.txt" "$F" || { echo "FAIL: パス未変換"; exit 1; }
grep -q "$PA-old/x" "$F" && { echo "FAIL: 別パスまで置換"; exit 1; } || true
! grep -q "$PA" "$F" || { echo "FAIL: A のパスが残る"; grep "$PA" "$F"; exit 1; }
test -f "$T/B/home/.claude/projects/$ENCB/s1/subagents/agent-1.jsonl" || { echo "FAIL: subagents"; exit 1; }
grep -q "$T/B/home/bin/sl.sh" "$T/B/home/.claude/settings.json" || { echo "FAIL: settings ホーム置換"; exit 1; }
test -f "$T/B/home/.claude/agents/reviewer.md" || { echo "FAIL: agents"; exit 1; }
grep -q "内容が異なる (1件): a.txt" "$T/pull.txt" || { echo "FAIL: 差分検出"; exit 1; }
grep -q ".env" "$T/pull.txt" && { echo "FAIL: .env を比較している"; exit 1; } || true
echo hello > "$PB/a.txt"

echo "== B: 会話を続けて push、A で pull"
echo '{"type":"user","cwd":"'"$PB"'","sessionId":"s1","message":{"role":"user","content":"continue on B"},"timestamp":"2026-10-13T01:00:00Z"}' >> "$F"
(cd "$PB" && dev B python3 "$S" push)
(cd "$PA" && dev A python3 "$S" pull)
grep -q "continue on B" "$T/A/home/.claude/projects/$ENC/s1.jsonl" || { echo "FAIL: A に反映されない"; exit 1; }

echo "== 両方で続けた場合 (競合)"
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"s1","message":{"role":"user","content":"A only"}}' >> "$T/A/home/.claude/projects/$ENC/s1.jsonl"
echo '{"type":"user","cwd":"'"$PB"'","sessionId":"s1","message":{"role":"user","content":"B only"}}' >> "$F"
(cd "$PB" && dev B python3 "$S" push)
(cd "$PA" && dev A python3 "$S" push) | tee "$T/c.txt"
grep -q "競合" "$T/c.txt" || { echo "FAIL: 競合を検出しない"; exit 1; }
(cd "$PA" && dev A python3 "$S" pull --no-settings) | tee "$T/c2.txt"
grep -q "取り込みました。" "$T/c2.txt" || true
ls "$T/A/home/.claude/projects/$ENC/"*.jsonl | wc -l | grep -q 2 || { echo "FAIL: 分岐が作られない"; exit 1; }
(cd "$PA" && dev A python3 "$S" push --no-settings)
(cd "$PB" && dev B python3 "$S" pull --no-settings)
grep -q "A only" "$F" || { echo "FAIL: B に A の版が届かない"; exit 1; }
ls "$T/B/home/.claude/projects/$ENCB/"*.jsonl | xargs grep -l "B only" >/dev/null || { echo "FAIL: B の版が失われた"; exit 1; }
(cd "$PB" && dev B python3 "$S" list)
echo "== rules/ は既定では共有せず、items add で共有する"
mkdir -p "$T/A/home/.claude/rules"; echo "# style" > "$T/A/home/.claude/rules/style.md"
(cd "$PA" && dev A python3 "$S" push)
(cd "$PB" && dev B python3 "$S" pull)
test ! -e "$T/B/home/.claude/rules" || { echo "FAIL: 既定で rules を共有した"; exit 1; }
dev A python3 "$S" items add rules
dev A python3 "$S" items add ../x >/dev/null 2>&1 && { echo "FAIL: 不正な名前を受け付けた"; exit 1; } || true
(cd "$PA" && dev A python3 "$S" push)
(cd "$PB" && dev B python3 "$S" pull)
test -f "$T/B/home/.claude/rules/style.md" || { echo "FAIL: items add 後に rules が届かない"; exit 1; }
echo "== 自動同期フック: 起動時 pull は今開いている会話を書き換えない"
dev B python3 "$S" auto on >/dev/null
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"s2","message":{"role":"user","content":"new on A"}}' > "$T/A/home/.claude/projects/$ENC/s2.jsonl"
echo '{"type":"user","cwd":"'"$PA"'","sessionId":"s1","message":{"role":"user","content":"A again"}}' >> "$T/A/home/.claude/projects/$ENC/s1.jsonl"
(cd "$PA" && dev A python3 "$S" push --no-settings) >/dev/null
OUT=$(echo '{"session_id":"s1","cwd":"'"$PB"'"}' | dev B python3 "$S" hook start 2>"$T/hook.err"); cat "$T/hook.err" >&2
echo "$OUT" | grep -q "取り込みました" || { echo "FAIL: フックの要約が出ない"; exit 1; }
test -f "$T/B/home/.claude/projects/$ENCB/s2.jsonl" || { echo "FAIL: フックで新しい会話が届かない"; exit 1; }
grep -q "A again" "$F" && { echo "FAIL: 開いている会話を書き換えた"; exit 1; } || true
echo '{"cwd":"'"$PB"'"}' | dev B python3 "$S" auto off >/dev/null
echo '{}' | dev B python3 "$S" hook end || { echo "FAIL: フックが 0 以外で終了"; exit 1; }
echo "ALL OK"
