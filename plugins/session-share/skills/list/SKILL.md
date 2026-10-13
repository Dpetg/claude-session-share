---
description: 共有されている会話の一覧 (このプロジェクト)
argument-hint: "[--all] [--limit N]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" list $ARGUMENTS 2>&1 || true`

上の一覧をそのまま表で見せ、再開するには `claude --resume <ID>` をこのプロジェクトのディレクトリで実行すると伝える。手元にまだ無い会話は先に `/session-share:pull` が必要。
