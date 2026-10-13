#!/usr/bin/env bash
# 自前の git サーバ (自己署名証明書の HTTPS) を共有先にする通しテスト
set -euo pipefail
unset GIT_SSL_CAINFO  # 環境変数の CA 指定は --ca-cert (http.sslCAInfo) より優先されるため外す
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE/../plugins/session-share/scripts/ccshare.py"
T="$(cd "$(mktemp -d)" && pwd -P)"
PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; rm -rf "$T"; }
trap cleanup EXIT
command -v openssl >/dev/null || { echo "SKIP: openssl がありません"; exit 0; }
PORT=$((20000 + RANDOM % 20000)); PORT2=$((PORT + 1))
mkdir -p "$T/srv"
git init -q --bare "$T/srv/claude-sessions.git"
git init -q --bare "$T/srv/moved.git"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" \
  -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
  -keyout "$T/key.pem" -out "$T/cert.pem" >/dev/null 2>&1
python3 "$HERE/git_server.py" "$T/srv" "$PORT" "$T/cert.pem" "$T/key.pem" & PIDS+=($!)
python3 "$HERE/git_server.py" "$T/srv" "$PORT2" & PIDS+=($!)
for _ in $(seq 50); do (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break; sleep 0.1; done
URL="https://127.0.0.1:$PORT/claude-sessions.git"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.postBuffer GIT_CONFIG_VALUE_0=104857600  # テスト用サーバ向け
dev() { local n=$1; shift
  CCSHARE_HOME_OVERRIDE="$T/$n/home" CLAUDE_CONFIG_DIR="$T/$n/home/.claude" CCSHARE_DIR="$T/$n/home/.ccshare" \
  GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
mkdir -p "$T/A/home/.claude" "$T/B/home/.claude"
echo '{"theme":"dark"}' > "$T/A/home/.claude/settings.json"

echo "== 証明書を指定しないと、理由と対処を出して止まる"
if dev A python3 "$S" init --remote "$URL" > "$T/err.txt" 2>&1; then echo "FAIL: 接続できてしまった"; exit 1; fi
grep -q "接続できませんでした" "$T/err.txt" && grep -q -- "--ca-cert" "$T/err.txt" || { cat "$T/err.txt"; echo "FAIL: ヒントが無い"; exit 1; }
test ! -e "$T/A/home/.ccshare/config.json" || { echo "FAIL: 失敗したのに設定を保存した"; exit 1; }

echo "== --ca-cert で初期化し、2台目で取り込む"
dev A python3 "$S" init --remote "$URL" --ca-cert "$T/cert.pem" --device devA
(cd "$T/A/home" && dev A python3 "$S" push)
git --git-dir="$T/srv/claude-sessions.git" log --oneline | grep -q "push from devA" || { echo "FAIL: サーバに届いていない"; exit 1; }
dev B python3 "$S" init --remote "$URL" --ca-cert "$T/cert.pem" --device devB
(cd "$T/B/home" && dev B python3 "$S" pull)
grep -q dark "$T/B/home/.claude/settings.json" || { echo "FAIL: B に設定が届かない"; exit 1; }

echo "== 共有先の引っ越し (空のリポジトリへ)"
URL2="http://127.0.0.1:$PORT2/moved.git"
dev A python3 "$S" init --remote "$URL2"
git --git-dir="$T/srv/moved.git" log --oneline | grep "push from devA" >/dev/null || {
  git --git-dir="$T/srv/moved.git" log --oneline --all; git -C "$T/A/home/.ccshare/store" log --oneline -3; git -C "$T/A/home/.ccshare/store" remote -v
  echo "FAIL: 引っ越し先に履歴が無い"; exit 1; }
dev B python3 "$S" init --remote "$URL2"   # 2台目も同じ共有先へ切り替えられる
(cd "$T/B/home" && dev B python3 "$S" pull) >/dev/null
git -C "$T/B/home/.ccshare/store" log --oneline | grep -q "push from devA" || {
  git -C "$T/B/home/.ccshare/store" log --oneline --all --decorate; git -C "$T/B/home/.ccshare/store" status
  git --git-dir="$T/srv/moved.git" log --oneline --all --decorate; echo "FAIL: B が引っ越し先を取り込めない"; exit 1; }
git init -q --bare "$T/srv/other.git"
git clone -q "$T/srv/other.git" "$T/other" 2>/dev/null; (cd "$T/other" && echo x > x && git add x && git -c user.name=t -c user.email=t@t commit -qm x && git push -q origin HEAD)
if dev B python3 "$S" init --remote "http://127.0.0.1:$PORT2/other.git" > "$T/err2.txt" 2>&1; then echo "FAIL: 無関係なリポジトリへの切り替えを許した"; exit 1; fi
grep -q "別の内容" "$T/err2.txt" || { cat "$T/err2.txt"; exit 1; }
git -C "$T/B/home/.ccshare/store" remote get-url origin | grep -q moved.git || { echo "FAIL: 失敗時に元の共有先に戻っていない"; exit 1; }
echo "ALL OK"
