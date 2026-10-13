---
description: プロジェクトのファイルが、最後に push したデバイスと一致しているか確認する
argument-hint: "[--all]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" verify $ARGUMENTS 2>&1 || true`

結果をユーザーの言語で伝える。差がある場合は、ファイルの共有は Git で行う前提なので、どちらかのデバイスで commit/push・pull が必要かを一緒に整理する。環境固有で比較したくないファイルは、プロジェクト直下の `.ccshareignore` に1行1パターンで書けば除外できる。
