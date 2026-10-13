---
description: session-share の設定状態 (共有先、デバイス名、リンク済みプロジェクト、自動同期)
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" status 2>&1 || true`

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" auto 2>&1 || true`

上の状態をユーザーの言語で短くまとめる。未初期化なら `/session-share:setup` を案内する。
