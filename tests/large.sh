#!/usr/bin/env bash
# 大きな会話の分割と、push を拒否されたコミットからの立ち直りのテスト
# (GitHub の 100MB 上限を、小さな上限の pre-receive フックで再現する)
set -euo pipefail
S="$(cd "$(dirname "$0")/../plugins/session-share/scripts" && pwd)/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"; trap 'rm -rf "$T"' EXIT
dev() { local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
enc() { python3 -c "import re,sys;print(re.sub(r'[^A-Za-z0-9]','-',sys.argv[1]))" "$1"; }
fail() { echo "FAIL: $*"; exit 1; }
LIMIT=3000
git init -q --bare "$T/remote.git"
cat > "$T/remote.git/hooks/pre-receive" <<HOOK
#!/usr/bin/env bash
z=0000000000000000000000000000000000000000
while read old new ref; do
  range=\$new; [ "\$old" != "\$z" ] && range="\$old..\$new"
  git rev-list --objects \$range | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' |
    awk '\$1=="blob" && \$2>$LIMIT {print "error: File " \$3 " exceeds limit"; bad=1} END {exit bad}'
done
HOOK
chmod +x "$T/remote.git/hooks/pre-receive"
git init -q "$T/origin" && (cd "$T/origin" && echo hi > a.txt && git add a.txt && git -c user.name=t -c user.email=t@t commit -qm i)
PA="$T/A/home/work/demo"; PB="$T/B/home/src/demo"
mkdir -p "$T/A/home/.claude" "$T/B/home/.claude"
for d in "$PA" "$PB"; do git clone -q "$T/origin" "$d"; git -C "$d" remote set-url origin git@example.com:me/demo.git; done
DA="$T/A/home/.claude/projects/$(enc "$PA")"; DB="$T/B/home/.claude/projects/$(enc "$PB")"
mkdir -p "$DA"
line() { echo '{"type":"user","cwd":"'"$PA"'","sessionId":"big","message":{"role":"user","content":"'"$1 $(printf 'x%.0s' $(seq 200))"'"},"timestamp":"2026-10-01T00:00:00Z"}'; }
for i in $(seq 1 30); do line "msg$i"; done > "$DA/big.jsonl"
STORE="$T/A/home/.ccshare/store"

echo "== 分割しない古い版の動きを再現: 大きなファイルの push が拒否される"
dev A python3 "$S" init --remote "$T/remote.git" --device devA >/dev/null
OUT=$(cd "$PA" && CCSHARE_PART_LIMIT=100000000 dev A python3 "$S" push --no-settings 2>&1)
echo "$OUT" | grep "push に失敗" >/dev/null || fail "拒否されたのに警告が出ない"
echo "$OUT" | grep "exceeds limit" >/dev/null || fail "git のエラー内容が表示されない"
git -C "$T/remote.git" log --all --name-only --format= | grep big >/dev/null && fail "拒否されたはずの push が届いている"

echo "== 新しい版で再実行: 分割し直して、拒否されたコミットごとまとめ直して送れる"
OUT=$(cd "$PA" && CCSHARE_PART_LIMIT=2000 dev A python3 "$S" push --no-settings 2>&1)
echo "$OUT"
echo "$OUT" | grep "push に失敗" >/dev/null && fail "分割後も push に失敗した"
SD=$(echo "$STORE"/projects/*/sessions)
test ! -e "$SD/big.jsonl" || fail "分割前のファイルが残っている"
test -f "$SD/big.jsonl.001" && test -f "$SD/big.jsonl.002" || fail "分割されていない"
git -C "$T/remote.git" rev-list --objects --all | git -C "$T/remote.git" cat-file --batch-check='%(objecttype) %(objectsize)' |
  awk -v l=$LIMIT '$1=="blob" && $2>l {exit 1}' || fail "上限を超えるファイルが共有先の履歴にある"
P1=$(git -C "$STORE" rev-parse HEAD:"projects/$(basename "$(dirname "$SD")")/sessions/big.jsonl.001")

echo "== 別のデバイスでは 1 つの会話に戻る"
dev B python3 "$S" init --remote "$T/remote.git" --device devB >/dev/null
(cd "$PB" && CCSHARE_PART_LIMIT=2000 dev B python3 "$S" pull --no-settings) >/dev/null
DBF="$DB/big.jsonl"; test -f "$DBF" || fail "B に会話が届かない"
test "$(wc -l < "$DBF")" -eq 30 || fail "行数が合わない"
grep -q "msg30" "$DBF" && grep -q "\"cwd\":\"$PB\"" "$DBF" || fail "中身かパスがおかしい"
(cd "$PB" && CCSHARE_PART_LIMIT=2000 dev B python3 "$S" list) | grep "big" >/dev/null || fail "list に出ない"

echo "== 追記しても前の分割ファイルは変わらない"
line "msg31" >> "$DA/big.jsonl"
(cd "$PA" && CCSHARE_PART_LIMIT=2000 dev A python3 "$S" push --no-settings) >/dev/null
test "$(git -C "$STORE" rev-parse HEAD:"projects/$(basename "$(dirname "$SD")")/sessions/big.jsonl.001")" = "$P1" || fail "001 が書き換わった"
(cd "$PB" && CCSHARE_PART_LIMIT=2000 dev B python3 "$S" pull --no-settings) >/dev/null
grep -q "msg31" "$DBF" || fail "追記が B に届かない"

echo "== 1 行だけで上限を超えるファイルは送らずに警告する"
python3 -c "print('{\"type\":\"user\",\"cwd\":\"$PA\",\"sessionId\":\"huge\",\"message\":{\"content\":\"' + 'y'*5000 + '\"}}')" > "$DA/huge.jsonl"
OUT=$(cd "$PA" && CCSHARE_PART_LIMIT=2000 CCSHARE_HARD_LIMIT=$LIMIT dev A python3 "$S" push --no-settings 2>&1)
echo "$OUT" | grep "上限を超えるので送りません" >/dev/null || fail "大きすぎるファイルを警告しない"
echo "$OUT" | grep "push に失敗" >/dev/null && fail "大きすぎるファイルのせいで push 全体が失敗した"
echo "OK: large"
