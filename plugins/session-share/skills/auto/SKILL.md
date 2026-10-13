---
description: 起動時に pull、終了時に push を自動で行うかを切り替える (このデバイス)
argument-hint: "[on|off]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" auto $ARGUMENTS 2>&1 || true`

結果をユーザーの言語で伝える。自動同期は、共有先にリンク済みのプロジェクト (一度 push したもの、または git remote が一致するもの) でだけ動く。いま開いている会話自体は起動時の pull で書き換えない。
