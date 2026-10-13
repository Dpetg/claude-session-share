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
   - git リポジトリ (推奨): 会話にはコードや秘密情報が含まれ得るので、必ず **private** のリポジトリにする。空のリポジトリを先に作ってもらう。GitHub / GitLab などのほか、自分でホストしている git サーバ (Gitea、GitLab、SSH で入れるサーバ上の bare リポジトリなど) も使える。URL の例:
     - `https://github.com/<user>/claude-sessions`
     - `git@git.example.com:<user>/claude-sessions.git`、`ssh://git@git.example.com:2222/<user>/claude-sessions.git`
     - `<user>@nas.local:/srv/git/claude-sessions.git` (サーバで `git init --bare /srv/git/claude-sessions.git` しておく)
     - `https://git.example.com/<user>/claude-sessions.git`
   - クラウドドライブ (OneDrive / Dropbox / Google Drive など) の同期フォルダ内のパス。
2. 実行する。
   - git: `RUN init --remote <URL>` (共有先の手元コピーは `~/.ccshare/store`)
     - SSH で専用の鍵を使うなら `--ssh-key <秘密鍵のパス>`、自己署名証明書の HTTPS サーバなら `--ca-cert <CA 証明書のパス>` を付ける (このデバイスだけの設定)。
     - 接続に失敗するとスクリプトが理由と確認点を表示するので、それをユーザーに伝えて直してもらう。
     - 既に別の共有先で初期化済みで、共有先を引っ越す場合も `RUN init --remote <新しいURL>` でよい。新しい共有先が空なら手元の内容を送り、他のデバイスが引っ越し済みならその内容を取り込む。
   - フォルダ: `RUN init --backend folder --store "<パス>"`
   既に初期化済みで同じ共有先なら、この手順は飛ばす。
3. 共有先に既にデータがある (2台目以降の) 場合は、自分の設定で上書きしないよう、先に `RUN pull` を実行する。初めての1台目なら `RUN push` で設定を送る。どちらもユーザーのホームディレクトリで実行すると設定だけが対象になる。
4. 結果を短く伝え、次の使い方を案内する:
   - 作業の始めに `/session-share:pull`、終わりに `/session-share:push` (プロジェクトのディレクトリで)
   - 自動化するなら `/session-share:auto on`
   - git の認証に失敗した場合は、SSH 鍵や git の credential helper (GitHub なら `gh auth login`) で、git がこのリポジトリに push できる状態にしてもらう。
