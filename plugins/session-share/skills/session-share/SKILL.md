---
description: Claude Code の会話履歴と設定を Windows / macOS / Linux や別デバイス間で共有・再開する仕組み (session-share プラグイン) の使い方。「別のPCで会話を続けたい」「履歴を同期したい」「デバイス間でファイルが一致しているか確認したい」ときに使う。
---

# session-share

会話履歴 (`~/.claude/projects/` の jsonl) と設定 (`settings.json`, `CLAUDE.md`, `agents/`, `commands/`, `skills/` など) を、git リポジトリやクラウドドライブ経由でデバイス間に共有する。プロジェクトのファイル自体は Git で共有する前提で、ファイルが一致しているかの確認だけを行う。

ユーザーが操作するときは次のコマンドを案内する (自分で実行してよいのは、ユーザーに頼まれたときだけ)。

| コマンド | 内容 |
|---|---|
| `/session-share:setup` | 初期設定 (共有先を設定) |
| `/session-share:pull` | 他のデバイスの会話と設定を取り込む |
| `/session-share:push` | このデバイスの会話と設定を送る |
| `/session-share:list` | 共有されている会話の一覧 |
| `/session-share:verify` | ファイルが他のデバイスと一致しているか |
| `/session-share:items` | 共有する設定項目の追加・削除 (例: `add rules`) |
| `/session-share:auto on` | 起動時 pull / 終了時 push を自動化 |
| `/session-share:secrets` | 秘密情報の扱い (伏せ字 / 警告のみ / 送らない) |
| `/session-share:prune` | 共有先から古い会話を外して容量を減らす |
| `/session-share:status` | 状態の確認 |

スクリプトを直接実行する場合は `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" <サブコマンド>`。

## 仕組み

- 会話の中の絶対パス (プロジェクトの場所、ホーム) を `{{CCSHARE_PROJECT}}` / `{{CCSHARE_HOME}}` に置き換えて保存し、取り込み先のパスに戻す。Claude Code は「作業ディレクトリのパスを変換した名前のフォルダ」から会話を探すため、取り込み先のパスに合わせたフォルダに置き直す。これで OS やパスが違っても `claude --resume` で再開できる。
- プロジェクトは git の `origin` URL で対応付ける。リモートが無ければ `run.sh link --key <共通の名前>` を各デバイスで実行する。
- 同じ会話を両方のデバイスで進めた場合は、片方を別 ID の会話として残す (どちらも消えない)。
- OS ごとに変えたい設定は、共有先の `config/settings.windows.json` / `settings.mac.json` / `settings.linux.json` に書くとその OS でだけ上書きされる。
- Claude Code がプロジェクトごとに書き溜める自動メモリ (`~/.claude/projects/<プロジェクト>/memory/`) も共有する。両方で書き換わった場合は、相手側の版を `*.from-other-device.md` として隣に置く。
- 送る前に API キー・トークン・秘密鍵などを検出し、既定では `[REDACTED:種類]` に置き換える (手元は書き換えない)。
- 認証情報 (`.credentials.json`)、`~/.claude.json`、`settings.local.json` は共有しない。
- ファイル確認では `.gitignore` 対象、`.env*`, `*.local.*`, `.venv/`, `node_modules/` などの環境固有ファイルを除外し、改行コードの差は無視する。プロジェクト直下の `.ccshareignore` で除外を追加できる。
