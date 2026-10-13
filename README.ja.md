# session-share — Claude Code の会話をデバイス・OS をまたいで続ける

[English](README.md) | 日本語

Windows / macOS / Linux、デュアルブートや複数の PC の間で、Claude Code の**会話履歴と設定**を共有し、別のデバイスで `claude --resume` して続きから作業できるようにする Claude Code プラグインです。

## できること

- `/session-share:push` / `/session-share:pull` で会話と設定を送受信
- プロジェクトの場所が OS ごとに違っても再開できる (会話の中のパスを自動で置き換え)
- 同じ会話を2台で進めてしまっても、どちらも消さずに別の会話として残す
- プロジェクトのファイルが他のデバイスと一致しているかを確認 (`.env` や `node_modules/` などの環境固有ファイルと改行コードの差は無視)
- `/session-share:auto on` で、起動時に pull・終了時に push を自動化
- Claude Code がプロジェクトごとに書き溜める自動メモリ (`~/.claude/projects/<プロジェクト>/memory/`) も共有
- 送る前に API キー・トークン・秘密鍵を検出し、`[REDACTED:種類]` に置き換える (手元は書き換えない)
- `/session-share:prune` で共有先から古い会話を外し、git の履歴を作り直して容量を減らせる

プロジェクトのファイル自体は Git で共有する前提です。このプラグインが共有するのは Claude Code 側のデータだけです。

## 必要なもの

- Claude Code
- Python 3.8 以上 (標準ライブラリのみ使用。Windows は `py` でも可)
- git と、共有先にする **private** の git リポジトリ (GitHub、GitLab、自分でホストしている git サーバなど)。または OneDrive / Dropbox / Google Drive などの同期フォルダ
- Windows では Git for Windows (Git Bash)

## インストール

```
/plugin marketplace add Dpetg/claude-session-share
/plugin install session-share@claude-session-share
```

## 使い方

1. 各デバイスでプラグインを入れ、共有したいプロジェクトのディレクトリで `/session-share:setup` を実行する。
   - [GitHub CLI (gh)](https://cli.github.com/) にログイン済みなら、private リポジトリ `<you>/claude-sessions` を作り (2台目以降は既存のものを使い)、1台目なら送信、2台目以降なら取り込み、自動同期 (起動時 pull・終了時 push) のオンまでをまとめて行います。
   - gh を使わない場合は、空の **private** リポジトリの URL か、クラウドドライブのフォルダを渡します: `/session-share:setup https://github.com/<you>/claude-sessions`
2. ほかのプロジェクトは、そのディレクトリで一度 `/session-share:push` すれば、以後は自動で同期されます。
3. 取り込んだ会話は `claude --resume` (または `/resume`) から開く。

| コマンド | 内容 |
|---|---|
| `/session-share:setup [URL\|owner/repo\|フォルダ]` | 初期設定 (省略時は gh で private リポジトリを用意) |
| `/session-share:pull` | 他のデバイスの会話と設定を取り込む |
| `/session-share:push` | このデバイスの会話と設定を送る |
| `/session-share:list` | 共有されている会話の一覧 |
| `/session-share:verify` | ファイルが最後に push したデバイスと一致しているか |
| `/session-share:items [add\|remove] <名前>` | 共有する設定項目の追加・削除 (例: `add rules`) |
| `/session-share:auto [on\|off]` | 起動時 pull / 終了時 push の自動化 (デバイスごと) |
| `/session-share:secrets [mask\|warn\|block]` | 会話に含まれる秘密情報の扱い |
| `/session-share:slim [hooks\|images] [on\|off]` | 共有先のコピーからフックの出力・画像を削る |
| `/session-share:prune [--older-than 日数] [--squash]` | 共有先から古い会話を外す / 履歴を作り直す |
| `/session-share:status` | 状態の確認 |

## 自分の git サーバを使う

`git` が接続できるリモートなら何でも使えます (Gitea、GitLab、SSH で入れるサーバ上の bare リポジトリ、NAS など)。

```
# サーバ側 (SSH で入れるサーバの場合)
git init --bare /srv/git/claude-sessions.git

# 各デバイスの Claude Code で
/session-share:setup me@myserver:/srv/git/claude-sessions.git
/session-share:setup ssh://git@git.example.com:2222/me/claude-sessions.git
/session-share:setup https://git.example.com/me/claude-sessions.git
```

- 初期設定の最初に接続を確かめ、失敗したら理由と確認点を表示して止まります。
- 専用の SSH 鍵や、自己署名証明書の HTTPS サーバ用の CA 証明書を使う場合は、スクリプトの `init` に `--ssh-key <秘密鍵>` / `--ca-cert <CA 証明書>` を付けます。設定はそのデバイスにだけ保存されます (`/session-share:setup` でその旨を伝えれば付けて実行します)。
- 別のサーバへ引っ越すときは、新しい URL でもう一度 setup します。新しいリポジトリが空なら全体をコピーし、他のデバイスも同じコマンドで切り替えて続きから使えます。
- プロジェクトは git の `origin` URL で対応付けます。SSH と HTTPS の違いやポート番号は無視するので、`git@host:me/app.git` と `https://host/me/app` は同じプロジェクトとして扱います。

## 共有されるもの・されないもの

| 共有する | 共有しない |
|---|---|
| 会話履歴 (`~/.claude/projects/` のうち、リンクしたプロジェクトのもの) | 認証情報 (`.credentials.json`) |
| プロジェクトごとの自動メモリ (`~/.claude/projects/<プロジェクト>/memory/`) | |
| `settings.json`, `CLAUDE.md`, `keybindings.json` | `~/.claude.json` (アカウント情報など) |
| `agents/`, `commands/`, `skills/`, `output-styles/`, `hooks/` | `settings.local.json` |
| `rules/` など (`items add` で追加したもの) | シェルのスナップショットや一時ファイル |

OS ごとに変えたい設定 (statusLine のコマンドなど) は、共有先リポジトリの `config/settings.windows.json` / `settings.mac.json` / `settings.linux.json` に書くと、その OS でだけ上書きされます。

## 秘密情報

送る前に、会話・メモリ・`settings.json` から API キー (Anthropic、OpenAI、Google、AWS、Stripe)、GitHub / GitLab / Slack のトークン、JWT、秘密鍵、`password=` のような代入を検出します。

- `mask` (既定): 共有先に送る版だけ `[REDACTED:種類]` に置き換えます。手元のファイルは書き換えず、`settings.json` の伏せ字が本物の値を持つデバイスの設定を上書きすることもありません。
- `warn`: そのまま送り、見つかったものを報告します。
- `block`: 秘密情報を含む会話は送りません。

設定は共有先に保存され、全デバイスに効きます。パターンによる検出なので、すべてを見つけられるわけではありません。

> **注意**: 会話履歴にはコードや秘密情報が含まれることがあります。共有先は必ず private にしてください。

## 共有先の容量を抑える

push のたびに、変わった会話の最新版がコミットされるので、共有先は少しずつ大きくなります。

- 共有先に送るコピーでは、フックが標準出力に返した内容を 500 文字に切り詰めます (`/session-share:slim hooks off` で無効)。ツールの入力をそのまま返すフックがあると、これだけで会話の半分近くを占めることがあります。手元の会話は書き換えません。
- `/session-share:slim images on` で、会話に貼った画像も「画像を省略」に置き換えて送ります。再開した会話では Claude がその画像を見られなくなります。
- `/session-share:prune --older-than 90` で、90 日以上触っていない会話を共有先から外します。各デバイスの手元には残り、その会話を続けると再び共有されます。
- 40MB を超える会話は、共有先では行単位で `<ID>.jsonl.001`, `.002` ... に分けて置きます (GitHub は 100MB を超えるファイルを受け付けないため)。取り込むときは 1 つの会話に戻します。
- `/session-share:prune --squash` で、共有先の git の履歴を1つのコミットにまとめて容量を減らします (強制 push)。他のデバイスは次の同期で自動的に合わせます。ブランチ保護で強制 push が禁止されていると失敗します。
- 使用量は `/session-share:status` で確認できます。

## 仕組み

Claude Code は会話を `~/.claude/projects/<作業ディレクトリのパスを変換した名前>/<セッションID>.jsonl` に保存し、`--resume` は今のディレクトリに対応するフォルダから会話を探します。そのため、パスの違う別のデバイスに単純にコピーしても会話は見つかりません。

session-share は、送るときに会話の中の絶対パス (プロジェクトのルートとホーム) を `{{CCSHARE_PROJECT}}` / `{{CCSHARE_HOME}}` に置き換え、受け取るときにそのデバイスのパスに戻して正しいフォルダに置きます。プロジェクトはデバイス間で git の `origin` URL によって対応付けます (リモートが無い場合は `link --key` で名前を付ける)。

同期の状態はセッションごとに「最後に同期した版」のハッシュで管理します。片方だけが進んでいれば上書きし、両方で進んでいれば相手側の版を別 ID の会話として取り込みます。

## テスト

```
python3 tests/test_paths.py   # Windows / macOS / Linux のパス変換
bash tests/e2e.sh             # 2台のデバイスを模した push / pull / 競合 / 自動同期
bash tests/self_hosted.sh     # 自己署名証明書の HTTPS git サーバと、共有先の引っ越し
bash tests/features.sh        # 秘密情報の伏せ字、メモリの共有、prune と squash
bash tests/setup.sh           # 引数なしの setup (gh でリポジトリを用意)
bash tests/large.sh           # 大きな会話の分割と、push を拒否されたときの立ち直り
```

## ライセンス

MIT
