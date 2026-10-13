---
description: 他のデバイスの会話履歴と設定を取り込む (作業の始めに)
argument-hint: "[--all] [--no-settings]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
## 実行結果

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" pull $ARGUMENTS 2>&1 || true`

上の結果をユーザーの言語で短く伝える。
- 取り込んだ会話は、Claude Code を開き直して `claude --resume` (または `/resume`) から続けられると伝える。一覧は `/session-share:list`。
- ファイル確認で差がある場合は、どのファイルが違うかと、git の pull/commit が済んでいるかの確認を促す。
- 「競合」で別 ID として取り込んだ会話があれば、その ID を伝える。
- 設定を反映した場合は、新しい設定は次に起動したセッションから効くと伝える。
