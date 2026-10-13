---
description: 共有先から古い会話を外して容量を減らす (各デバイスの手元の会話は消さない)
argument-hint: "[--older-than 日数] [--squash]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
共有先 (git リポジトリ) の容量を減らす。スクリプトは `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"` (以下 RUN)。

## 現在の状態

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" status 2>&1 || true`

## 手順

1. 引数 `$ARGUMENTS` が無ければ、何日より前の会話を外すか (例: 90 日) と、git の履歴も作り直すか (`--squash`) をユーザーに尋ねる。
2. まず `RUN prune <引数> --dry-run` を実行し、対象の件数と減る容量を見せる。
3. ユーザーが実行してよいと答えたら、`--dry-run` を外して実行する。確認なしに実行しない。
4. 伝えること:
   - 外した会話は各デバイスの手元には残り、その会話を続けると再び共有される。
   - `--squash` は共有先の git の履歴を1つにまとめる (強制 push)。他のデバイスは次の同期で自動的に合わせる。GitHub などでブランチ保護により強制 push が禁止されていると失敗する。
