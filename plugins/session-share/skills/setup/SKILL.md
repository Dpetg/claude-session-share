---
description: session-share の初期設定 (共有先の用意・取り込みまたは送信・自動同期オンまでをまとめて行う)
argument-hint: "[onedrive|dropbox|gdrive|icloud|box | git リモート URL | owner/repo | フォルダのパス] (省略時は gh で private リポジトリを用意)"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
session-share の初期設定を行う。スクリプトは `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"` (以下 RUN) で実行する。

## 現在の状態

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" status 2>&1 || true`

## 手順

1. `RUN setup $ARGUMENTS` を Bash で実行する (会話が多いと最初の送信に数分かかるので、タイムアウトは 10 分にする)。これだけで次をまとめて行う。
   - 共有先の用意: 引数が無ければ GitHub CLI (gh) で private リポジトリ `<自分>/claude-sessions` を探し、無ければ作る。`owner/repo` を渡すとその名前で同じことをする。URL (https / ssh / `user@host:path`) ならその git リポジトリを使う。
     - `onedrive` / `dropbox` / `gdrive` / `icloud` / `box` なら、このデバイスでそのクラウドドライブの同期フォルダを探し、その中の `claude-sessions` フォルダを共有先にする。それ以外の文字列はフォルダのパスとして使う。
     - ユーザーが共有先を決めかねているなら、先に `RUN drives` で見つかったクラウドドライブを示し、GitHub (gh) とどちらにするか尋ねる。目安: クラウドドライブは git や GitHub のアカウントが要らず手軽。git は履歴が残り、同時に書き込んでも壊れにくい。
     - 既に別の共有先で設定済みなら、新しい共有先が空のときは手元の内容をそこへ移す (GitHub からクラウドドライブへの引っ越しなど)。
   - 共有先が空なら、このデバイスの設定と (今のディレクトリが git プロジェクトなら) その会話を送る。データがあれば取り込む。
   - 自動同期 (起動時に pull、終了時に push) をオンにする。オンにしたくないと言われたら `--no-auto` を付ける。
   - 自前の git サーバで専用の SSH 鍵を使うなら `--ssh-key <秘密鍵のパス>`、自己署名証明書の HTTPS なら `--ca-cert <CA 証明書のパス>` を付ける。
2. 失敗したら、スクリプトが表示した理由と対処をそのまま短く伝える。よくあるもの:
   - gh が無い / ログインしていない: gh をインストールして `gh auth login` してもらうか、共有先の URL を指定してもらう。
   - 指定したリポジトリが public: 会話にはコードや秘密情報が含まれ得るので private にしてもらう。
   - 接続できない: SSH 鍵や git の credential helper で、git がそのリポジトリに push できる状態にしてもらう。
3. 結果を短く伝え、次を案内する。
   - 他のデバイスでも、プラグインを入れて同じ `/session-share:setup` (同じ引数) を実行すれば取り込まれる。
   - 自動同期は、一度 push したプロジェクト (または git remote が一致するプロジェクト) で動く。新しいプロジェクトは、そのディレクトリで一度 `/session-share:push` する。
   - 会話を開くには `claude --resume`。
