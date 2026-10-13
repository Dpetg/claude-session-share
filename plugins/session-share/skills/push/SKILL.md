---
description: このデバイスの会話履歴と設定を共有先に送る (作業の終わりに)
argument-hint: "[--all] [--no-settings]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
## 実行結果

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" push $ARGUMENTS 2>&1 || true`

上の結果をユーザーの言語で短く伝える。
- 「未初期化」と出たら `/session-share:setup` を案内する。
- 「競合」と出たら、`/session-share:pull` してから再度 push するよう伝える。
- 「未コミットの変更」の注意が出たら、ファイルは Git で別途 commit/push する必要があると伝える。
