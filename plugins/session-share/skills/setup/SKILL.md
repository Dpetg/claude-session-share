---
description: session-share の初期設定 (共有先の git リポジトリまたはクラウドドライブのフォルダを設定)
argument-hint: "[git リモート URL | フォルダのパス]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
session-share の初期設定を行う。スクリプトは `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"` (以下 RUN) で実行する。

## 現在の状態

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" status 2>&1 || true`

## 手順

1. 共有先を決める。引数 `$ARGUMENTS` があればそれを使う。無ければユーザーに次のどちらかを尋ねる。
   - git リポジトリ (推奨): 会話にはコードや秘密情報が含まれ得るので、必ず **private** のリポジトリにする。例: `https://github.com/<user>/claude-sessions` (空のリポジトリを先に作ってもらう)。
   - クラウドドライブ (OneDrive / Dropbox / Google Drive など) の同期フォルダ内のパス。
2. 実行する。
   - git: `RUN init --remote <URL>` (共有先の手元コピーは `~/.ccshare/store`)
   - フォルダ: `RUN init --backend folder --store "<パス>"`
   既に初期化済みで同じ共有先なら、この手順は飛ばす。
3. 共有先に既にデータがある (2台目以降の) 場合は、自分の設定で上書きしないよう、先に `RUN pull` を実行する。初めての1台目なら `RUN push` で設定を送る。どちらもユーザーのホームディレクトリで実行すると設定だけが対象になる。
4. 結果を短く伝え、次の使い方を案内する:
   - 作業の始めに `/session-share:pull`、終わりに `/session-share:push` (プロジェクトのディレクトリで)
   - 自動化するなら `/session-share:auto on`
   - git の認証に失敗した場合は、`gh auth login` などで git がこのリポジトリに push できる状態にしてもらう。
