---
description: 共有する設定項目の確認・追加・削除 (例: rules を追加)
argument-hint: "[add|remove] [名前]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" items $ARGUMENTS 2>&1 || true`

結果をユーザーの言語で伝える。追加・削除は共有先に保存され、全デバイスに効く。追加した項目を実際に送るには `/session-share:push` を実行する。
