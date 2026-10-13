---
description: 会話を送るときの秘密情報 (API キー・トークン・秘密鍵など) の扱いを確認・変更する
argument-hint: "[mask|warn|block]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" secrets $ARGUMENTS 2>&1 || true`

結果をユーザーの言語で伝える。
- mask (既定): 見つけた値を `[REDACTED:種類]` に置き換えて送る。手元の会話や設定は書き換えない。
- warn: そのまま送り、警告だけ出す。
- block: 秘密情報を含む会話は送らない。
設定は共有先に保存され、全デバイスに効く。検出はパターンによるもので、すべての秘密情報を見つけられるわけではないので、共有先は必ず private にするよう添える。
