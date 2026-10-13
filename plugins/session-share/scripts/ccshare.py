#!/usr/bin/env python3
"""ccshare: Claude Code の会話履歴と設定を、デバイス・OS をまたいで共有する。

標準ライブラリのみ (Python 3.8+)。Windows / macOS / Linux 共通。

ストア (共有先) の構成:
    <store>/
      .gitattributes            改行変換を無効化 (* -text)
      config/                   ~/.claude の共有対象 (settings.json, CLAUDE.md, agents/ ...)
      config/settings.<os>.json OS ごとの上書き (任意, 手で作る)
      projects/<key>/project.json
      projects/<key>/manifest.json         最後に push したデバイスのファイル一覧とハッシュ
      projects/<key>/sessions/<id>.jsonl   パスをプレースホルダ化した会話履歴
      projects/<key>/sessions/<id>.jsonl.001, .002 ...
                                           40MB を超える会話は行単位で分割して置く
      projects/<key>/sessions/<id>/        サブエージェント等の付随ファイル

ローカル設定 (同期しない): ~/.ccshare/config.json, ~/.ccshare/state.json
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

PH_PROJECT = "{{CCSHARE_PROJECT}}"
PH_HOME = "{{CCSHARE_HOME}}"
FORK_NS = uuid.UUID("6c2b8e8e-6f0a-4d38-9a43-5b8d3c1e7a10")
# GitHub は 50MB を超えるファイルで警告し、100MB を超えると push を拒否する
PART_LIMIT = int(os.environ.get("CCSHARE_PART_LIMIT") or 40 * 1024 * 1024)
HARD_LIMIT = int(os.environ.get("CCSHARE_HARD_LIMIT") or 95 * 1024 * 1024)

CONFIG_ITEMS = ["settings.json", "CLAUDE.md", "keybindings.json",
                "agents", "commands", "skills", "output-styles", "hooks"]
# 追加で共有できる (Claude Code が既定では作らない) もの。`ccshare.py items add <名前>` で有効化する
OPTIONAL_ITEMS = ["rules"]
# 認証情報や端末固有のデータなので共有しない
NEVER_ITEMS = [".credentials.json", "settings.local.json", "projects", "sessions", "session-env",
               "shell-snapshots", "statsig", "todos", "ide", "file-history", "backups", "plugins"]
# 環境固有なので比較しない (プロジェクトの .ccshareignore で追加できる)
DEFAULT_IGNORES = [".env", ".env.*", "*.local.*", ".claude/settings.local.json",
                   ".venv/", "venv/", "node_modules/", "__pycache__/", "*.pyc",
                   ".DS_Store", "Thumbs.db", "desktop.ini", ".idea/", ".vscode/"]


# ---------------------------------------------------------------- 基本情報

def os_name():
    s = platform.system().lower()
    return {"darwin": "mac", "windows": "windows"}.get(s, "linux" if s == "linux" else s)


def is_windows():
    return os_name() == "windows"


def home_dir():
    return Path(os.environ.get("CCSHARE_HOME_OVERRIDE") or Path.home())


def claude_dir():
    d = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(d) if d else home_dir() / ".claude"


def ccshare_dir():
    d = os.environ.get("CCSHARE_DIR")
    return Path(d) if d else home_dir() / ".ccshare"


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def load_config():
    cfg = load_json(ccshare_dir() / "config.json", None)
    if not cfg:
        sys.exit("ccshare: 未初期化です。先に初期設定 (/session-share:setup または `ccshare.py init`) を行ってください。")
    return cfg


def save_config(cfg):
    save_json(ccshare_dir() / "config.json", cfg)


def same_path(a, b):
    a, b = str(a).replace("\\", "/").rstrip("/"), str(b).replace("\\", "/").rstrip("/")
    return a.lower() == b.lower() if is_windows() else a == b


def under(child, root):
    c = str(child).replace("\\", "/").rstrip("/")
    r = str(root).replace("\\", "/").rstrip("/")
    if is_windows():
        c, r = c.lower(), r.lower()
    return c == r or c.startswith(r + "/")


def encode_project_dir(cwd):
    """Claude Code が ~/.claude/projects/ 以下に使うディレクトリ名 (英数字以外を - に置換)。"""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def run(cmd, cwd=None, check=True):
    # 認証の入力待ちで止まらないようにする (フックから呼ばれることもある)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if check and r.returncode != 0:
        raise RuntimeError("{} 失敗:\n{}{}".format(" ".join(cmd), r.stdout, r.stderr))
    return r


# ---------------------------------------------------------------- パスの置換

class PathMapper:
    """デバイス固有の絶対パスとプレースホルダを相互変換する。"""

    def __init__(self, project_root=None, home=None, windows=None, aliases=()):
        self.windows = is_windows() if windows is None else windows
        self.project = str(project_root) if project_root else None
        self.home = str(home or home_dir())
        groups = []
        if self.project:
            # aliases: シンボリックリンク経由など、同じプロジェクトを指す別の表記 (macOS の /var と /private/var 等)
            groups.append(([self.project] + [str(a) for a in aliases], PH_PROJECT))
        groups.append(([self.home, os.path.realpath(self.home)], PH_HOME))
        self.out_patterns = []
        for reals, ph in groups:
            variants = set()
            for real in reals:
                variants |= {real, real.replace("\\", "/"), real.replace("/", "\\")}
            alts = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
            flags = re.IGNORECASE if self.windows else 0
            # 直後がパス区切りか、パスに使われない文字であるときだけ置換 (/proj が /project2 に当たらないように)
            self.out_patterns.append((re.compile("(?:%s)(?=[/\\\\]|$|[^A-Za-z0-9._\\-])" % alts, flags), ph))

    def to_store(self, s):
        for pat, ph in self.out_patterns:
            s = pat.sub(lambda m, ph=ph: ph, s)
        return s

    def to_local(self, s):
        if "{{CCSHARE_" not in s:
            return s

        def repl(m):
            real = self.project if m.group(1) == PH_PROJECT else self.home
            tail = m.group(2) or ""
            if not self.windows:
                tail = tail.replace("\\", "/")  # Windows で書かれたパスの続きを / に直す
            return (real or m.group(1)) + tail
        return re.sub(r"(%s|%s)((?:[/\\][^\s\"'<>|*?`]*)?)" % (re.escape(PH_PROJECT), re.escape(PH_HOME)), repl, s)

    def walk(self, obj, fn, key=None):
        if isinstance(obj, str):
            v = fn(obj)
            if key == "cwd" and fn == self.to_local:
                v = v.replace("/", "\\") if self.windows else v.replace("\\", "/")
            return v
        if isinstance(obj, list):
            return [self.walk(x, fn) for x in obj]
        if isinstance(obj, dict):
            return {k: self.walk(v, fn, k) for k, v in obj.items()}
        return obj


def convert_jsonl(text, fn_obj):
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.dumps(fn_obj(json.loads(line)), ensure_ascii=False, separators=(",", ":")))
        except ValueError:
            out.append(line)  # 壊れた行はそのまま
    return "\n".join(out) + ("\n" if out else "")


def read_text(p):
    with open(p, encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def sha(s):
    return hashlib.sha256(s.encode("utf-8", "surrogateescape")).hexdigest()


# ストア内の会話ファイル。p は論理パス (<id>.jsonl)。大きいものは <id>.jsonl.001 ... に分かれている

def part_files(p):
    p = Path(p)
    return sorted(f for f in p.parent.glob(p.name + ".*") if re.fullmatch(r"\.\d{3}", f.suffix))


def stored_exists(p):
    return Path(p).exists() or bool(part_files(p))


def read_stored(p):
    p = Path(p)
    return read_text(p) if p.exists() else "".join(read_text(f) for f in part_files(p))


def stored_size(p):
    p = Path(p)
    return sum(f.stat().st_size for f in ([p] if p.exists() else part_files(p)))


def remove_stored(p):
    p = Path(p)
    for f in ([p] if p.exists() else []) + part_files(p):
        f.unlink()


def write_stored(p, s):
    """PART_LIMIT を超える会話は行単位で分割する。会話は追記されていくので、
    前の方の分割ファイルは中身が変わらず、git の履歴も増えない。"""
    p = Path(p)
    old = part_files(p)
    if len(s.encode("utf-8", "surrogateescape")) <= PART_LIMIT:
        for f in old:
            f.unlink()
        write_text(p, s)
        return
    if p.exists():
        p.unlink()
    chunks, cur, size = [], [], 0
    for line in s.splitlines(True):
        n = len(line.encode("utf-8", "surrogateescape"))
        if cur and size + n > PART_LIMIT:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += n
    if cur:
        chunks.append("".join(cur))
    keep = set()
    for i, c in enumerate(chunks, 1):
        f = p.with_name("{}.{:03d}".format(p.name, i))
        keep.add(f.name)
        write_text(f, c)
    for f in old:
        if f.name not in keep:
            f.unlink()


def stored_sessions(d):
    """ストアの sessions/ にある会話: {id: 論理パス}"""
    d = Path(d)
    if not d.is_dir():
        return {}
    out = {f.stem: f for f in d.glob("*.jsonl")}
    for f in d.glob("*.jsonl.001"):
        out.setdefault(f.name[: -len(".jsonl.001")], f.with_name(f.name[:-4]))
    return out


# ---------------------------------------------------------------- 秘密情報

SECRET_PATTERNS = [
    ("秘密鍵", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
    ("Anthropic API キー", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API キー", re.compile(r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}")),
    ("GitHub トークン", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("GitLab トークン", re.compile(r"glpat-[A-Za-z0-9_\-]{20,}")),
    ("AWS アクセスキー", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API キー", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Slack トークン", re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("Stripe キー", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]
# KEY=値 / "password": "値" のような代入。値がコードらしいもの (関数呼び出しや変数参照) は除く
SECRET_ASSIGN = re.compile(
    r"(?i)((?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password|passwd)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"'`,;(){}\[\]$<>]{12,})")
REDACTED = "[REDACTED:{}]"


class SecretFilter:
    """共有先に送る文字列から秘密情報を探す。mode: mask (伏せ字にする) / warn (警告のみ) / block (送らない)"""

    def __init__(self, mode="mask"):
        self.mode = mode if mode in ("mask", "warn", "block") else "mask"
        self.found = {}

    def __call__(self, s):
        if len(s) < 16:
            return s
        for kind, pat in SECRET_PATTERNS:
            if pat.search(s):
                self.found[kind] = self.found.get(kind, 0) + len(pat.findall(s))
                if self.mode == "mask":
                    s = pat.sub(REDACTED.format(kind), s)

        def assign(m):
            v = m.group(2)
            if v.startswith("[REDACTED") or not (re.search(r"\d", v) and re.search(r"[A-Za-z]", v)) \
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+", v):
                return m.group(0)  # 英字だけ・数字だけの値や process.env.X のような参照は秘密とみなさない
            self.found["パスワード等の代入"] = self.found.get("パスワード等の代入", 0) + 1
            return m.group(1) + REDACTED.format("secret") if self.mode == "mask" else m.group(0)
        return SECRET_ASSIGN.sub(assign, s)

    def summary(self):
        return ", ".join("{} {}件".format(k, v) for k, v in sorted(self.found.items()))


def secret_mode(cfg):
    return store_options(cfg).get("secrets", "mask")


def store_converter(mapper, filt):
    """ローカル -> 共有先の変換 (パスのプレースホルダ化 + 秘密情報の処理)。"""
    return lambda o: mapper.walk(o, lambda s: filt(mapper.to_store(s)))


# ---------------------------------------------------------------- ストア / バックエンド

def store_path(cfg):
    return Path(cfg["store"]).expanduser()


def git_store(cfg):
    return cfg.get("backend", "git") == "git"


def store_has_remote(st):
    return bool(run(["git", "remote"], cwd=st, check=False).stdout.strip())


def store_fetch(cfg):
    st = store_path(cfg)
    if git_store(cfg) and store_has_remote(st):
        if not run(["git", "ls-remote", "--heads", "origin"], cwd=st, check=False).stdout.strip():
            return  # リモートが空 (最初の push 前)
        if follow_squash(st):
            return
        r = run(["git", "pull", "--rebase", "--autostash"], cwd=st, check=False)
        unmerged = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=st, check=False).stdout.strip()
        if unmerged or "CONFLICT" in r.stdout + r.stderr:
            # 競合したまま進むと、競合マーカー入りのファイルを push してしまう
            sys.exit("ccshare: ストアの git pull で競合しました。{} を確認してから再実行してください:\n{}".format(
                st, unmerged or r.stderr.strip()))
        if r.returncode != 0:
            print("警告: ストアの git pull に失敗しました:\n" + r.stderr.strip())


def follow_squash(st):
    """別のデバイスが prune --squash で履歴を作り直していたら、手元のストアをそれに合わせる。
    ストアの中身は各デバイスの ~/.claude から作り直せるので、手元の未送信分は次の push で送り直される。"""
    run(["git", "fetch", "-q", "origin"], cwd=st, check=False)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=st).stdout.strip()
    remote = "origin/" + branch
    if run(["git", "rev-parse", "--verify", "-q", remote], cwd=st, check=False).returncode != 0:
        return False
    theirs = run(["git", "show", remote + ":ccshare.json"], cwd=st, check=False).stdout
    try:
        their_epoch = json.loads(theirs).get("history_epoch") if theirs else None
    except ValueError:
        their_epoch = None
    mine = load_json(st / "ccshare.json", {}).get("history_epoch")
    if their_epoch and their_epoch != mine and \
            run(["git", "merge-base", "--is-ancestor", "HEAD", remote], cwd=st, check=False).returncode != 0:
        run(["git", "reset", "-q", "--hard", remote], cwd=st)
        print("共有先の履歴が整理されていたので、手元のコピーを合わせました。")
        return True
    return False


def store_commit(cfg, message):
    st = store_path(cfg)
    if not git_store(cfg):
        return
    # まだ送れていないコミットは 1 つにまとめ直す。push を拒否されたファイル
    # (大きすぎる会話など) が履歴に残ったままだと、何度やり直しても送れないため
    up = run(["git", "rev-parse", "--verify", "-q", "@{u}"], cwd=st, check=False).stdout.strip()
    if up and run(["git", "merge-base", "--is-ancestor", up, "HEAD"], cwd=st, check=False).returncode == 0:
        run(["git", "reset", "-q", "--soft", up], cwd=st)
    elif not up and store_has_remote(st) and \
            run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=st, check=False).returncode == 0 and \
            not run(["git", "ls-remote", "--heads", "origin"], cwd=st, check=False).stdout.strip():
        run(["git", "update-ref", "-d", "HEAD"], cwd=st)  # 共有先が空: 最初のコミットから作り直す
    # ccshare が書くものだけをコミットする (tools/ など手で編集したものは巻き込まない)
    paths = [p for p in ("config", "projects", "ccshare.json") if (st / p).exists()]
    if paths:
        run(["git", "add", "-A", "--"] + paths, cwd=st)
    staged = run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=AM"], cwd=st).stdout.split("\0")
    for name in filter(None, staged):
        f = st / name
        if f.is_file() and f.stat().st_size > HARD_LIMIT:
            run(["git", "rm", "-q", "--cached", "--", name], cwd=st)
            print("警告: {} は {} あり、git サーバの上限を超えるので送りません。".format(name, human(f.stat().st_size)))
    if not run(["git", "diff", "--cached", "--name-only"], cwd=st).stdout.strip():
        return
    run(["git", "commit", "-q", "-m", message], cwd=st)
    if store_has_remote(st):
        errors = []
        for _ in range(2):
            r = run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=st, check=False)
            if r.returncode == 0:
                return
            errors.append(r.stderr.strip())
            r = run(["git", "pull", "--rebase", "--autostash"], cwd=st, check=False)
            if r.returncode != 0:
                errors.append(r.stderr.strip())
                if (st / ".git" / "rebase-merge").exists() or (st / ".git" / "rebase-apply").exists():
                    # 途中で止まった rebase を残すと、次の pull / push もすべて失敗する
                    run(["git", "rebase", "--abort"], cwd=st, check=False)
                break
        print("警告: ストアの git push に失敗しました ({})。手元のストアには記録済みです。\n"
              "git の出力:\n{}".format(st, "\n".join(e for e in errors if e) or "(なし)"))


def device_id(cfg):
    return cfg["device"]


# ---------------------------------------------------------------- プロジェクト

def git_remote_key(path):
    r = run(["git", "config", "--get", "remote.origin.url"], cwd=path, check=False)
    url = r.stdout.strip()
    if r.returncode != 0 or not url:
        return None
    return normalize_remote(url)


def normalize_remote(url):
    """同じリポジトリを指す URL を、SSH / HTTPS・ポート番号の違いによらず同じキーにする。
    例: git@git.example.com:me/app.git, ssh://git@git.example.com:2222/me/app,
        https://git.example.com/me/app.git -> git.example.com/me/app"""
    url = url.strip().rstrip("/")
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?(/.*)?$", url)
    if m:
        host, path = m.group(1), m.group(2) or ""
    else:
        m = re.match(r"^(?:[^@/]+@)?([^/:]+):(.*)$", url)  # scp 形式 user@host:path
        if m and not re.match(r"^[A-Za-z]:[\\/]", url):
            host, path = m.group(1), m.group(2)
        else:
            host, path = "local", url.replace("\\", "/")  # ローカルパス (NAS のマウント等)
    path = re.sub(r"\.git$", "", path.rstrip("/"))
    path = re.sub(r"^/*~[^/]*/", "", path)  # ssh://host/~user/repo
    path = re.sub(r"/+", "/", path).strip("/")
    return "{}/{}".format(host, path).lower()


def safe_key(key):
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def find_project(cfg, path=None):
    path = Path(path or os.getcwd()).resolve()
    for key, root in cfg.get("projects", {}).items():
        if under(path, root):
            return key, root
    return None, None


def link_project(cfg, path, key=None, quiet=False):
    path = str(Path(path).resolve())
    key = key or git_remote_key(path) or Path(path).name
    cfg.setdefault("projects", {})[key] = path
    save_config(cfg)
    pj = store_path(cfg) / "projects" / safe_key(key) / "project.json"
    info = load_json(pj, {"key": key, "devices": {}})
    info["key"] = key
    info.setdefault("devices", {})[device_id(cfg)] = {"path": path, "os": os_name()}
    save_json(pj, info)
    if not quiet:
        print("リンク: {} -> {}".format(key, path))
    return key


def auto_link(cfg, path=None):
    """カレントディレクトリが未リンクなら、git remote が一致するストア上のプロジェクトに自動でリンクする。"""
    key, root = find_project(cfg, path)
    if key:
        return key, root
    path = Path(path or os.getcwd()).resolve()
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=path, check=False).stdout.strip()
    if not top:
        return None, None
    rk = git_remote_key(top)
    if rk and (store_path(cfg) / "projects" / safe_key(rk)).is_dir():
        link_project(cfg, top, rk)
        return rk, str(Path(top).resolve())
    return None, None


def target_projects(cfg, args):
    if getattr(args, "all", False):
        return list(cfg.get("projects", {}).items())
    key, root = auto_link(cfg, getattr(args, "project", None))
    if not key and args.cmd == "push":
        # 初めて push するプロジェクトは自動で登録する
        path = Path(getattr(args, "project", None) or os.getcwd()).resolve()
        top = run(["git", "rev-parse", "--show-toplevel"], cwd=path, check=False).stdout.strip()
        if not top:
            print("git リポジトリの外なので、会話は送らず設定だけを扱います (git 以外のフォルダは `link --key` で登録)。")
            return []
        root = str(Path(top).resolve())
        key = link_project(cfg, root)
    if not key and args.cmd == "pull":
        print("このディレクトリはリンクされていないので、設定だけを取り込みました。")
        return []
    if not key:
        sys.exit("ccshare: このディレクトリはリンクされていません。`ccshare.py link` を実行するか --all を使ってください。")
    return [(key, root)]


# ---------------------------------------------------------------- ファイル一致の確認

def load_ignores(root):
    pats = list(DEFAULT_IGNORES)
    f = Path(root) / ".ccshareignore"
    if f.exists():
        pats += [l.strip() for l in read_text(f).splitlines() if l.strip() and not l.startswith("#")]
    return pats


def ignored(rel, pats):
    parts = rel.split("/")
    for p in pats:
        if p.endswith("/"):
            if p.rstrip("/") in parts[:-1] or fnmatch.fnmatch(rel, p + "*"):
                return True
        elif fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(parts[-1], p):
            return True
    return False


def file_digest(p):
    with open(p, "rb") as f:
        data = f.read()
    if b"\0" not in data[:8000]:
        data = data.replace(b"\r\n", b"\n")  # 改行コードの違いは無視
    return hashlib.sha256(data).hexdigest()


def build_manifest(root):
    root = Path(root)
    pats = load_ignores(root)
    r = run(["git", "ls-files", "-z", "-co", "--exclude-standard"], cwd=root, check=False)
    if r.returncode == 0:
        rels = [x for x in r.stdout.split("\0") if x]
        git = {
            "head": run(["git", "rev-parse", "HEAD"], cwd=root, check=False).stdout.strip(),
            "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, check=False).stdout.strip(),
            "dirty": bool(run(["git", "status", "--porcelain"], cwd=root, check=False).stdout.strip()),
        }
    else:
        rels = [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()]
        git = None
    files = {}
    for rel in sorted(rels):
        p = root / rel
        if ignored(rel, pats) or not p.is_file():
            continue
        files[rel] = file_digest(p)
    return {"time": now(), "os": os_name(), "git": git, "files": files}


def compare_manifest(local, remote):
    lf, rf = local["files"], remote["files"]
    diff = {
        "modified": sorted(k for k in lf.keys() & rf.keys() if lf[k] != rf[k]),
        "missing": sorted(rf.keys() - lf.keys()),
        "extra": sorted(lf.keys() - rf.keys()),
    }
    lg, rg = local.get("git") or {}, remote.get("git") or {}
    diff["head"] = (lg.get("head"), rg.get("head")) if lg.get("head") != rg.get("head") else None
    return diff


def report_verify(key, root, st, limit=20):
    remote = load_json(st / "projects" / safe_key(key) / "manifest.json", None)
    if not remote:
        print("  [ファイル確認] ストアにマニフェストがまだありません。")
        return True
    d = compare_manifest(build_manifest(root), remote)
    src = "{} ({}, {})".format(remote.get("device", "?"), remote.get("os", "?"), remote.get("time", "?"))
    ok = not (d["modified"] or d["missing"] or d["extra"] or d["head"])
    if ok:
        print("  [ファイル確認] {} の状態と一致しています。".format(src))
        return True
    print("  [ファイル確認] {} の状態と差があります:".format(src))
    if d["head"]:
        print("    git HEAD: ここ={} / 相手={}".format((d["head"][0] or "-")[:10], (d["head"][1] or "-")[:10]))
    for label, name in (("内容が異なる", "modified"), ("ここに無い", "missing"), ("ここにだけある", "extra")):
        items = d[name]
        if items:
            print("    {} ({}件): {}{}".format(label, len(items), ", ".join(items[:limit]),
                                            " ..." if len(items) > limit else ""))
    return False


# ---------------------------------------------------------------- セッション

def first_cwd(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if '"cwd"' in line:
                    try:
                        c = json.loads(line).get("cwd")
                        if c:
                            return c
                    except ValueError:
                        pass
                if i > 200:
                    break
    except OSError:
        pass
    return None


def local_sessions(root):
    """root 以下で開かれたローカルのセッション: {id: (jsonl パス, cwd)}"""
    out = {}
    pdir = claude_dir() / "projects"
    if not pdir.is_dir():
        return out
    for d in pdir.iterdir():
        if not d.is_dir():
            continue
        for f in d.glob("*.jsonl"):
            cwd = first_cwd(f)
            if cwd and (under(cwd, root) or under(os.path.realpath(cwd), root)):
                prev = out.get(f.stem)
                if not prev or f.stat().st_mtime > prev[0].stat().st_mtime:
                    out[f.stem] = (f, cwd)
    return out


def root_aliases(root, cwds):
    """セッションに記録された cwd のうち、root と表記が違うもの (リンク経由) から root の別表記を求める。"""
    out = set()
    for c in cwds:
        if under(c, root):
            continue
        real = os.path.realpath(c)
        if not under(real, root):
            continue
        rel = os.path.relpath(real, root)
        alias = c if rel == "." else c[: len(c) - len(rel) - 1]
        if alias:
            out.add(alias)
    return sorted(out, key=len, reverse=True)


def session_title(text):
    title, prompt = None, None
    for line in text.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") in ("ai-title", "custom-title", "summary"):
            title = d.get("aiTitle") or d.get("customTitle") or d.get("summary") or title
        elif d.get("type") == "user" and prompt is None and not d.get("isMeta"):
            c = d.get("message", {}).get("content")
            if isinstance(c, str):
                prompt = c
    return (title or prompt or "").strip().replace("\n", " ")[:60]


def copy_session_dir(src, dst, fn_obj, to_store=False):
    """<id>/ 付随ディレクトリをコピー。jsonl はパス変換する (ストアへは大きければ分割して書く)。"""
    if dst.exists():
        shutil.rmtree(dst)
    if not src.is_dir():
        return
    for p in src.rglob("*"):
        if p.is_file():
            m = re.fullmatch(r"(.*\.jsonl)\.(\d{3})", p.name)
            if m:
                if m.group(2) != "001":
                    continue
                p = p.with_name(m.group(1))
            t = dst / p.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == ".jsonl":
                text = convert_jsonl(read_stored(p), fn_obj)
                write_stored(t, text) if to_store else write_text(t, text)
            else:
                shutil.copy2(p, t)


def state_key(key, sid):
    return "{}/{}".format(key, sid)


def memory_dir(root):
    """Claude Code がプロジェクトごとに書き溜める自動メモリの場所。"""
    return claude_dir() / "projects" / encode_project_dir(root) / "memory"


def push_memory(cfg, state, key, root):
    src = memory_dir(root)
    st = store_path(cfg) / "projects" / safe_key(key) / "memory"
    if not src.is_dir():
        return 0, []
    mapper = PathMapper(root)
    mode = secret_mode(cfg)
    mem = state.setdefault("memory", {})
    pushed, conflicts = 0, []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(src)).replace("\\", "/")
        if ".from-other-device." in f.name:
            continue  # 競合時に置いた相手側の版は、このデバイスで確認するためのもの
        filt = SecretFilter(mode)
        local = filt(mapper.to_store(read_text(f)))
        if filt.found and mode == "block":
            continue
        L, dst = sha(local), st / rel
        S = sha(read_text(dst)) if dst.exists() else None
        B = mem.get(state_key(key, rel))
        if S == L:
            mem[state_key(key, rel)] = L
        elif S is None or S == B:
            write_text(dst, local)
            mem[state_key(key, rel)] = L
            pushed += 1
        elif L != B:
            conflicts.append(rel)
    return pushed, conflicts


def pull_memory(cfg, state, key, root):
    st = store_path(cfg) / "projects" / safe_key(key) / "memory"
    if not st.is_dir():
        return 0, []
    dst_root = memory_dir(root)
    mapper = PathMapper(root)
    filt = SecretFilter(secret_mode(cfg))
    mem = state.setdefault("memory", {})
    pulled, conflicts = 0, []
    for f in sorted(st.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(st)).replace("\\", "/")
        stored = read_text(f)
        S, B = sha(stored), mem.get(state_key(key, rel))
        dst = dst_root / rel
        if dst.exists():
            L = sha(filt(mapper.to_store(read_text(dst))))
            if L == S:
                mem[state_key(key, rel)] = S
                continue
            if S == B:
                continue  # 手元の方が新しい
            if L != B:
                # 両方で書き換わっている: 相手側の版を隣に置き、手元はそのまま残す
                other = dst.with_name(dst.stem + ".from-other-device" + dst.suffix)
                write_text(other, mapper.to_local(stored))
                mem[state_key(key, rel)] = S
                conflicts.append(str(other.name))
                continue
        write_text(dst, mapper.to_local(stored))
        mem[state_key(key, rel)] = S
        pulled += 1
    return pulled, conflicts


def push_project(cfg, state, key, root):
    """会話・メモリ・ファイルのマニフェストを送る。結果の表示用の行を返す。"""
    lines = []
    secrets = {}
    n, conflicts = push_sessions(cfg, state, key, root, report=secrets)
    mn, mconf = push_memory(cfg, state, key, root)
    m = build_manifest(root)
    m["device"] = device_id(cfg)
    save_json(store_path(cfg) / "projects" / safe_key(key) / "manifest.json", m)
    lines.append("[{}] セッション {} 件・メモリ {} 件を送信、ファイル {} 件のマニフェストを記録".format(
        key, n, mn, len(m["files"])))
    if m.get("git") and m["git"].get("dirty"):
        lines.append("  注意: 未コミットの変更があります。ファイルは Git で別途共有してください。")
    for sid in conflicts:
        lines.append("  競合: {} は別のデバイスでも更新されています。先に pull してください。".format(sid))
    for rel in mconf:
        lines.append("  競合: メモリ {} は別のデバイスでも更新されています。先に pull してください。".format(rel))
    mode = secret_mode(cfg)
    for sid, summary in sorted(secrets.items()):
        what = {"mask": "伏せ字にして送りました", "warn": "そのまま送りました", "block": "送りませんでした"}[mode]
        lines.append("  秘密情報: {} に {} が含まれていたため、{}。".format(sid, summary, what))
    return lines


def pull_project(cfg, state, key, root, skip=()):
    lines = []
    n, forks = pull_sessions(cfg, state, key, root, skip=skip)
    mn, mconf = pull_memory(cfg, state, key, root)
    lines.append("[{}] セッション {} 件・メモリ {} 件を取り込みました ({})".format(key, n, mn, root))
    for sid, fid in forks:
        lines.append("  競合: {} は両方で更新されていたため、相手側の版を {} として取り込みました。".format(sid, fid))
    for name in mconf:
        lines.append("  競合: メモリが両方で更新されていたため、相手側の版を {} として置きました。内容をまとめてください。".format(name))
    return lines, n + len(forks) + mn


def pruned_ids(cfg, key):
    return load_json(store_path(cfg) / "projects" / safe_key(key) / "pruned.json", {})


def push_sessions(cfg, state, key, root, report=None):
    """report: 秘密情報が見つかったセッションを {id: 概要} で受け取る dict"""
    st = store_path(cfg) / "projects" / safe_key(key) / "sessions"
    sessions = local_sessions(root)
    mapper = PathMapper(root, aliases=root_aliases(root, [c for _f, c in sessions.values()]))
    mode = secret_mode(cfg)
    pruned = pruned_ids(cfg, key)
    pushed, conflicts = 0, []
    for sid, (f, _cwd) in sorted(sessions.items()):
        filt = SecretFilter(mode)
        to_store = store_converter(mapper, filt)
        local = convert_jsonl(read_text(f), to_store)
        L = sha(local)
        dst = st / (sid + ".jsonl")
        S = sha(read_stored(dst)) if stored_exists(dst) else None
        B = state["sessions"].get(state_key(key, sid))
        if sid in pruned and L == B:
            continue  # 整理 (prune) 済みで、その後この会話を続けていない
        if filt.found and report is not None:
            report[sid] = filt.summary()
        if filt.found and mode == "block":
            continue
        if S == L:
            if dst.exists() and dst.stat().st_size > PART_LIMIT:
                write_stored(dst, local)  # 以前の版で分割せずに置いた大きな会話を分割し直す
            state["sessions"][state_key(key, sid)] = L
            continue
        if S is None or S == B:
            if sid in pruned:
                del pruned[sid]  # 整理後に続きを書いた会話は、また共有する
                save_json(store_path(cfg) / "projects" / safe_key(key) / "pruned.json", pruned)
            write_stored(dst, local)
            copy_session_dir(f.with_suffix(""), st / sid, to_store, to_store=True)
            state["sessions"][state_key(key, sid)] = L
            pushed += 1
        elif L == B:
            pass  # ストアの方が新しい。pull で取り込む
        else:
            conflicts.append(sid)
    return pushed, conflicts


def store_options(cfg):
    return load_json(store_path(cfg) / "ccshare.json", {})


def config_items(cfg):
    return CONFIG_ITEMS + [i for i in store_options(cfg).get("extra_items", []) if i not in CONFIG_ITEMS]


def push_settings(cfg):
    st = store_path(cfg) / "config"
    src = claude_dir()
    mapper = PathMapper(None)
    for item in config_items(cfg):
        s, d = src / item, st / item
        if item == "settings.json":
            if s.exists():
                local = load_json(s, {})
                overlay = load_json(st / "settings.{}.json".format(os_name()), {})
                common = load_json(d, {})
                filt = SecretFilter(secret_mode(cfg))
                out = store_converter(mapper, filt)(strip_overlay(local, overlay, common))
                if filt.found and filt.mode == "block":
                    print("  settings.json に秘密情報らしき値があるため送りませんでした ({})".format(filt.summary()))
                    continue
                save_json(d, out)
                if filt.found:
                    print("  settings.json に秘密情報らしき値があります ({}): {}".format(
                        filt.summary(), "伏せ字にして送りました" if filt.mode == "mask" else "そのまま送りました"))
            continue
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        elif s.is_file():
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)


def config_hash(cfg):
    st = store_path(cfg) / "config"
    h = hashlib.sha256()
    if st.is_dir():
        for p in sorted(st.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(st)).replace("\\", "/").encode())
                h.update(file_digest(p).encode())
    return h.hexdigest()


def store_config_empty(cfg):
    st = store_path(cfg) / "config"
    return not st.is_dir() or not any(st.iterdir())


def strip_overlay(local, overlay, common):
    """OS 上書きで入った値は共通設定に書き戻さない。"""
    out = dict(local)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = strip_overlay(out[k], v, common.get(k, {}) if isinstance(common.get(k), dict) else {})
        elif k in out and out[k] == v:
            if k in common:
                out[k] = common[k]
            else:
                del out[k]
    return out


def keep_redacted(new, local):
    """共有先で伏せ字になっている値は、手元に本物があればそれを残す。"""
    if isinstance(new, dict):
        return {k: keep_redacted(v, local.get(k) if isinstance(local, dict) else None) for k, v in new.items()}
    if isinstance(new, str) and "[REDACTED:" in new and isinstance(local, str):
        return local
    return new


def deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def tree_digests(root):
    """ファイル -> ハッシュ。root がファイルなら {"": ハッシュ}。"""
    root = Path(root)
    if root.is_file():
        return {"": file_digest(root)}
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)): file_digest(p) for p in root.rglob("*") if p.is_file()}


def pull_settings(cfg, keep_backups=5):
    st = store_path(cfg) / "config"
    if not st.is_dir():
        return
    dst = claude_dir()
    backup_root = ccshare_dir() / "backup"
    backup = backup_root / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    mapper = PathMapper(None)
    changed = []
    for item in config_items(cfg):
        s, d = st / item, dst / item
        if not s.exists():
            continue
        if item == "settings.json":
            common = mapper.walk(load_json(s, {}), mapper.to_local)
            overlay = mapper.walk(load_json(st / "settings.{}.json".format(os_name()), {}), mapper.to_local)
            new = keep_redacted(deep_merge(common, overlay), load_json(d, {}))
            if d.exists() and load_json(d, None) == new:
                continue
        else:
            local = tree_digests(d)
            incoming = tree_digests(s)
            # 手元にだけあるもの (新しく作ったスキル等) は消さないので、共有先の分が一致していれば変更なし
            if all(local.get(k) == v for k, v in incoming.items()):
                continue
        if d.exists():
            b = backup / item
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(d, b) if d.is_dir() else shutil.copy2(d, b)
        if item == "settings.json":
            save_json(d, new)
        elif s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
        changed.append(item)
    if changed:
        print("設定を反映しました: {}".format(", ".join(changed)))
    if backup.exists():
        print("  以前の設定のバックアップ: {}".format(backup))
        olds = sorted(p for p in backup_root.iterdir() if p.is_dir())
        for old in olds[:-keep_backups]:
            shutil.rmtree(old, ignore_errors=True)


def pull_sessions(cfg, state, key, root, skip=()):
    st = store_path(cfg) / "projects" / safe_key(key) / "sessions"
    if not st.is_dir():
        return 0, []
    have = local_sessions(root)
    mapper = PathMapper(root, aliases=root_aliases(root, [c for _f, c in have.values()]))
    to_store = store_converter(mapper, SecretFilter(secret_mode(cfg)))
    to_local = lambda o: mapper.walk(o, mapper.to_local)
    pulled, forks = 0, []
    for sid, src in sorted(stored_sessions(st).items()):
        if sid in skip:
            continue  # 今開いているセッションは書き換えない
        stored = read_stored(src)
        S = sha(stored)
        B = state["sessions"].get(state_key(key, sid))
        local_text = convert_jsonl(stored, to_local)
        cwd = first_cwd_from_text(local_text) or root
        if sid in have:
            f = have[sid][0]
            L = sha(convert_jsonl(read_text(f), to_store))
            if L == S:
                state["sessions"][state_key(key, sid)] = S
                continue
            if S == B:
                continue  # 手元の方が新しい。push で送る
            if L != B:
                # 両方で進んでいる: ストア側を別セッションとして取り込み、手元はそのまま残す
                fid = str(uuid.uuid5(FORK_NS, sid + S))
                fork_obj = lambda o, fid=fid, sid=sid: rename_session(to_local(o), sid, fid)
                dst = claude_dir() / "projects" / encode_project_dir(cwd) / (fid + ".jsonl")
                write_text(dst, convert_jsonl(stored, fork_obj))
                copy_session_dir(src.with_suffix(""), dst.with_suffix(""), fork_obj)
                state["sessions"][state_key(key, sid)] = S
                forks.append((sid, fid))
                continue
            dst = f
        else:
            dst = claude_dir() / "projects" / encode_project_dir(cwd) / (sid + ".jsonl")
        write_text(dst, local_text)
        copy_session_dir(src.with_suffix(""), dst.with_suffix(""), to_local)
        state["sessions"][state_key(key, sid)] = S
        pulled += 1
    return pulled, forks


def rename_session(obj, old, new):
    if isinstance(obj, dict) and obj.get("sessionId") == old:
        obj = dict(obj, sessionId=new)
    return obj


def first_cwd_from_text(text):
    for line in text.splitlines():
        if '"cwd"' in line:
            try:
                c = json.loads(line).get("cwd")
                if c:
                    return c
            except ValueError:
                pass
    return None


def load_state():
    s = load_json(ccshare_dir() / "state.json", {})
    s.setdefault("sessions", {})
    return s


def save_state(s):
    save_json(ccshare_dir() / "state.json", s)


# ---------------------------------------------------------------- コマンド

def remote_default_branch(st):
    """共有先の既定ブランチ名 (分からなければ手元のブランチ名)。"""
    out = run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=st, check=False).stdout
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out, re.M)
    if m and run(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/" + m.group(1)],
                  cwd=st, check=False).returncode == 0:
        return m.group(1)
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=st).stdout.strip()


REMOTE_HINTS = """接続できない場合の確認点:
  - SSH (git@host:path, ssh://host:port/path): `ssh -T git@<host>` が通るか。鍵を指定するなら init に --ssh-key <鍵のパス>
  - HTTPS: `git ls-remote <URL>` が通るか。認証は git の credential helper で設定する
  - 自己署名の証明書: init に --ca-cert <CA 証明書のパス>
  - サーバ側に空のリポジトリがあるか (例: サーバで `git init --bare /srv/git/claude-sessions.git`)"""


def store_git_config(st, args):
    """このデバイスのストアにだけ効く接続設定 (共有はされない)。"""
    if getattr(args, "ssh_key", None):
        key = str(Path(args.ssh_key).expanduser().resolve()).replace("\\", "/")
        run(["git", "config", "core.sshCommand", 'ssh -i "{}" -o IdentitiesOnly=yes'.format(key)], cwd=st)
    if getattr(args, "ca_cert", None):
        run(["git", "config", "http.sslCAInfo", str(Path(args.ca_cert).expanduser().resolve())], cwd=st)


def git_env_args(args):
    """接続確認・clone 用に、まだストアが無い段階でも同じ設定を -c で渡す。"""
    out = []
    if getattr(args, "ssh_key", None):
        key = str(Path(args.ssh_key).expanduser().resolve()).replace("\\", "/")
        out += ["-c", 'core.sshCommand=ssh -i "{}" -o IdentitiesOnly=yes'.format(key)]
    if getattr(args, "ca_cert", None):
        out += ["-c", "http.sslCAInfo={}".format(Path(args.ca_cert).expanduser().resolve())]
    return out


def cmd_init(args):
    cfg = load_json(ccshare_dir() / "config.json", {}) or {}
    st = Path(args.store).expanduser().resolve() if args.store else Path(cfg.get("store") or ccshare_dir() / "store")
    cfg["store"] = str(st)
    cfg["backend"] = args.backend
    cfg.setdefault("device", args.device or "{}-{}".format(socket.gethostname().split(".")[0], os_name()))
    if args.backend == "git":
        if args.remote:
            # 先に接続を確かめる (認証や証明書の問題を、後の push で気付くのではなくここで出す)
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
            r = subprocess.run(["git"] + git_env_args(args) + ["ls-remote", "--heads", args.remote],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            if r.returncode != 0:
                sys.exit("ccshare: 共有先 {} に接続できませんでした:\n{}\n\n{}".format(
                    args.remote, r.stderr.strip(), REMOTE_HINTS))
            remote_empty = not r.stdout.strip()
        if args.remote and not (st / ".git").exists():
            if st.exists() and any(st.iterdir()):
                sys.exit("ccshare: {} は空ではありません。".format(st))
            st.parent.mkdir(parents=True, exist_ok=True)
            if remote_empty:
                st.mkdir(parents=True, exist_ok=True)
                run(["git", "init", "-q"], cwd=st)
                run(["git", "remote", "add", "origin", args.remote], cwd=st)
            else:
                run(["git"] + git_env_args(args) + ["clone", "-q", args.remote, str(st)])
        elif not (st / ".git").exists():
            st.mkdir(parents=True, exist_ok=True)
            run(["git", "init", "-q"], cwd=st)
        elif args.remote:
            cur = run(["git", "config", "--get", "remote.origin.url"], cwd=st, check=False).stdout.strip()
            if cur and cur != args.remote:
                # 共有先の引っ越し (例: GitHub -> 自前の git サーバ)。手元のストアの中身を新しい共有先へ送る
                run(["git", "remote", "set-url", "origin", args.remote], cwd=st)
                store_git_config(st, args)
                if not remote_empty:
                    # 他のデバイスが引っ越し済みの共有先なら、同じ履歴の続きなので受け入れる
                    run(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], cwd=st, check=False)
                    target = "origin/" + remote_default_branch(st)
                    same = run(["git", "merge-base", "--is-ancestor", "HEAD", target], cwd=st, check=False)
                    if same.returncode != 0:
                        run(["git", "remote", "set-url", "origin", cur], cwd=st)
                        sys.exit("ccshare: 新しい共有先 {} には別の内容が入っています。空のリポジトリか、"
                                 "他のデバイスが引っ越しに使ったリポジトリを指定してください。".format(args.remote))
                    run(["git", "merge", "-q", "--ff-only", target], cwd=st)
                    run(["git", "branch", "-q", "--set-upstream-to=" + target], cwd=st, check=False)
                print("共有先を変更しました: {} -> {}".format(cur, args.remote))
            elif not cur:
                run(["git", "remote", "add", "origin", args.remote], cwd=st)
        run(["git", "config", "core.autocrlf", "false"], cwd=st)
        store_git_config(st, args)
    st.mkdir(parents=True, exist_ok=True)
    ga = st / ".gitattributes"
    if not ga.exists():
        write_text(ga, "* -text\n")
    save_config(cfg)
    if args.backend == "git" and args.remote and remote_empty:
        if run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=st, check=False).returncode != 0:
            run(["git", "add", "-A"], cwd=st)
            run(["git", "commit", "-q", "-m", "ccshare: init"], cwd=st)
        r = run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=st, check=False)
        if r.returncode != 0:
            sys.exit("ccshare: 共有先への push に失敗しました:\n{}\n\n{}".format(r.stderr.strip(), REMOTE_HINTS))
    print("初期化しました: ストア={} ({}) デバイス={}".format(st, args.backend, cfg["device"]))


def cmd_link(args):
    cfg = load_config()
    store_fetch(cfg)
    link_project(cfg, args.path or os.getcwd(), args.key)
    store_commit(cfg, "ccshare: link from {}".format(device_id(cfg)))


def cmd_push(args):
    cfg = load_config()
    store_fetch(cfg)
    state = load_state()
    st = store_path(cfg)
    if not args.no_settings:
        if store_config_empty(cfg) or state.get("settings_base") == config_hash(cfg):
            push_settings(cfg)
            state["settings_base"] = config_hash(cfg)
            print("設定を送信しました。")
        else:
            print("設定は送信しませんでした: 別のデバイスで更新されています。先に pull してください。")
    for key, root in target_projects(cfg, args):
        link_project(cfg, root, key, quiet=True)
        print("\n".join(push_project(cfg, state, key, root)))
    save_state(state)
    store_commit(cfg, "ccshare: push from {} at {}".format(device_id(cfg), now()))


def cmd_pull(args):
    cfg = load_config()
    store_fetch(cfg)
    state = load_state()
    if not args.no_settings:
        pull_settings(cfg)
        state["settings_base"] = config_hash(cfg)
    for key, root in target_projects(cfg, args):
        lines, _n = pull_project(cfg, state, key, root)
        print("\n".join(lines))
        report_verify(key, root, store_path(cfg))
    save_state(state)


def cmd_verify(args):
    cfg = load_config()
    store_fetch(cfg)
    ok = True
    for key, root in target_projects(cfg, args):
        print("[{}] {}".format(key, root))
        ok = report_verify(key, root, store_path(cfg), limit=200) and ok
    sys.exit(0 if ok else 1)


def cmd_list(args):
    cfg = load_config()
    store_fetch(cfg)
    for key, root in target_projects(cfg, args):
        st = store_path(cfg) / "projects" / safe_key(key) / "sessions"
        print("[{}] {}".format(key, root))
        rows = []
        for f in stored_sessions(st).values():
            text = read_stored(f)
            last = ""
            for line in reversed(text.splitlines()):
                m = re.search(r'"timestamp":"([^"]+)"', line)
                if m:
                    last = m.group(1)[:16].replace("T", " ")
                    break
            rows.append((last, f.stem, PathMapper(root).to_local(session_title(text))))
        for last, sid, title in sorted(rows, reverse=True)[: args.limit]:
            print("  {}  {}  {}".format(last, sid, title))
        print("  再開: claude --resume <ID>  (このプロジェクトのディレクトリで)")


def dir_size(p):
    p = Path(p)
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "{:.0f} {}".format(n, unit) if unit == "B" else "{:.1f} {}".format(n, unit)
        n /= 1024.0


def session_last_time(f):
    text = read_stored(f)
    for line in reversed(text.splitlines()):
        m = re.search(r'"timestamp":"([^"]+)"', line)
        if m:
            try:
                return datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            except ValueError:
                break
    f = f if f.exists() else part_files(f)[-1]
    return datetime.datetime.fromtimestamp(f.stat().st_mtime, datetime.timezone.utc)


def cmd_status(args):
    cfg = load_config()
    st = store_path(cfg)
    print("デバイス: {} ({})".format(cfg["device"], os_name()))
    print("ストア:   {} [{}]".format(cfg["store"], cfg.get("backend")))
    print("Claude:   {}".format(claude_dir()))
    print("秘密情報: {}".format({"mask": "伏せ字にして送る", "warn": "警告のみ", "block": "含む会話は送らない"}[secret_mode(cfg)]))
    total = dir_size(st)
    print("共有先の手元コピー: {} (うち git の履歴 {})".format(human(total), human(dir_size(st / ".git"))))
    for key, root in cfg.get("projects", {}).items():
        sd = st / "projects" / safe_key(key) / "sessions"
        n = len(stored_sessions(sd))
        print("  {} -> {} (ローカル {} 件 / 共有先 {} 件, {})".format(
            key, root, len(local_sessions(root)), n, human(dir_size(sd))))


def cmd_items(args):
    """共有する設定項目の確認・追加・削除。ストアに保存されるので全デバイスで共通になる。"""
    cfg = load_config()
    store_fetch(cfg)
    opts = store_options(cfg)
    extra = opts.get("extra_items", [])
    if args.action in ("add", "remove"):
        name = (args.name or "").strip().strip("/\\")
        if not name or name in NEVER_ITEMS or re.search(r"[/\\]|^\.\.?$", name):
            sys.exit("ccshare: {} は共有できません (~/.claude 直下のファイル名かフォルダ名を指定してください)".format(name))
        if args.action == "add" and name not in extra and name not in CONFIG_ITEMS:
            extra.append(name)
        if args.action == "remove":
            if name in CONFIG_ITEMS:
                sys.exit("ccshare: {} は既定の共有項目なので外せません。".format(name))
            extra = [i for i in extra if i != name]
            d = store_path(cfg) / "config" / name
            if d.exists():
                shutil.rmtree(d) if d.is_dir() else d.unlink()
        opts["extra_items"] = extra
        save_json(store_path(cfg) / "ccshare.json", opts)
        store_commit(cfg, "ccshare: items {} {} from {}".format(args.action, name, device_id(cfg)))
    print("既定: " + ", ".join(CONFIG_ITEMS))
    print("追加: " + (", ".join(extra) or "(なし)"))
    rest = [i for i in OPTIONAL_ITEMS if i not in extra]
    if rest:
        print("追加できる例: " + ", ".join(rest))


def cmd_secrets(args):
    """会話を送るときの秘密情報の扱い。共有先に保存されるので全デバイスで共通。"""
    cfg = load_config()
    store_fetch(cfg)
    if args.mode:
        opts = store_options(cfg)
        opts["secrets"] = args.mode
        save_json(store_path(cfg) / "ccshare.json", opts)
        store_commit(cfg, "ccshare: secrets {} from {}".format(args.mode, device_id(cfg)))
    mode = secret_mode(cfg)
    print("秘密情報の扱い: {} ({})".format(mode, {"mask": "見つけた値を [REDACTED:種類] に置き換えて送る",
                                            "warn": "そのまま送り、警告だけ出す",
                                            "block": "含む会話は送らない"}[mode]))
    print("検出する種類: " + ", ".join(k for k, _ in SECRET_PATTERNS) + ", パスワード等の代入")


def cmd_prune(args):
    """共有先から古い会話を外す (各デバイスの手元の会話は消さない)。--squash で git の履歴も作り直して容量を減らす。"""
    cfg = load_config()
    store_fetch(cfg)
    st = store_path(cfg)
    if args.older_than is None and not args.squash:
        sys.exit("ccshare: --older-than <日数> か --squash を指定してください。")
    targets = []
    if args.older_than is not None:
        limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.older_than)
        for pd in sorted((st / "projects").glob("*")) if (st / "projects").is_dir() else []:
            for _sid, f in sorted(stored_sessions(pd / "sessions").items()):
                if session_last_time(f) < limit:
                    size = stored_size(f) + dir_size(f.with_suffix(""))
                    targets.append((pd, f, size))
    freed = sum(t[2] for t in targets)
    print("{} 日より前の会話: {} 件 ({})".format(args.older_than, len(targets), human(freed))
          if args.older_than is not None else "古い会話の整理はしません。")
    for pd, f, size in targets[:50]:
        print("  {}  {}  {}".format(pd.name, f.stem, human(size)))
    if args.squash:
        print("git の履歴を作り直します (現在 {})。他のデバイスは次の同期で自動的に合わせます。".format(
            human(dir_size(st / ".git"))))
    if args.dry_run:
        print("(確認のみ。実行するには --dry-run を外してください)")
        return
    for pd, f, _size in targets:
        pruned = load_json(pd / "pruned.json", {})
        pruned[f.stem] = now()
        save_json(pd / "pruned.json", pruned)
        remove_stored(f)
        if f.with_suffix("").is_dir():
            shutil.rmtree(f.with_suffix(""))
    store_commit(cfg, "ccshare: prune from {} at {}".format(device_id(cfg), now()))
    if args.squash and git_store(cfg):
        opts = store_options(cfg)
        opts["history_epoch"] = str(uuid.uuid4())
        save_json(st / "ccshare.json", opts)
        store_commit(cfg, "ccshare: new history epoch")
        new = run(["git", "commit-tree", "HEAD^{tree}", "-m",
                   "ccshare: squashed history ({}, {})".format(device_id(cfg), now())], cwd=st).stdout.strip()
        run(["git", "reset", "-q", "--hard", new], cwd=st)
        if store_has_remote(st):
            r = run(["git", "push", "-q", "--force", "-u", "origin", "HEAD"], cwd=st, check=False)
            if r.returncode != 0:
                sys.exit("ccshare: 作り直した履歴の push に失敗しました (ブランチ保護で強制 push が禁止されていないか確認):\n"
                         + r.stderr.strip())
        run(["git", "reflog", "expire", "--expire=now", "--all"], cwd=st, check=False)
        run(["git", "gc", "-q", "--prune=now"], cwd=st, check=False)
        print("履歴を作り直しました。手元のコピー: {}".format(human(dir_size(st))))


def cmd_auto(args):
    """このデバイスで、起動時 pull / 終了時 push を自動で行うか (プラグインのフックが参照する)。"""
    cfg = load_config()
    if args.state:
        cfg["auto"] = args.state == "on"
        save_config(cfg)
    print("自動同期: {}".format("オン" if cfg.get("auto") else "オフ"))
    if cfg.get("auto"):
        print("リンク済みのプロジェクトで Claude Code を開くと pull、終了すると push します。")


def cmd_hook(args):
    """プラグインのフックから呼ばれる。失敗しても Claude Code を止めないよう、常に終了コード 0。"""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        data = {}
    cfg = load_json(ccshare_dir() / "config.json", None)
    if not cfg or not cfg.get("auto"):
        return
    cwd = data.get("cwd") or os.getcwd()
    out = sys.stdout
    sys.stdout = sys.stderr  # 詳細は stderr へ。stdout は Claude への短い要約だけ
    try:
        key, root = auto_link(cfg, cwd)
        if not key:
            return
        store_fetch(cfg)
        state = load_state()
        if args.event == "start":
            pull_settings(cfg)
            state["settings_base"] = config_hash(cfg)
            lines, n = pull_project(cfg, state, key, root, skip={data.get("session_id")})
            save_state(state)
            print("\n".join(lines))
            if n:
                out.write("session-share: 他のデバイスの会話・メモリを {} 件取り込みました (/session-share:list で一覧)。\n".format(n))
        else:
            print("\n".join(push_project(cfg, state, key, root)))
            save_state(state)
            store_commit(cfg, "ccshare: auto push from {} at {}".format(device_id(cfg), now()))
    except BaseException as e:  # noqa
        print("ccshare: {}".format(e), file=sys.stderr)
    finally:
        sys.stdout = out


def main():
    ap = argparse.ArgumentParser(prog="ccshare", description="Claude Code セッション共有")
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("init", help="ストアを設定")
    a.add_argument("--store", help="共有先の手元コピーの場所 (既定: ~/.ccshare/store)")
    a.add_argument("--backend", choices=["git", "folder"], default="git")
    a.add_argument("--remote", help="git リモート URL (GitHub 等の private リポジトリ、自前の git サーバ: git@host:path / ssh://host:port/path / https://...)")
    a.add_argument("--device", help="デバイス名 (既定: ホスト名-OS)")
    a.add_argument("--ssh-key", help="共有先への SSH 接続に使う秘密鍵 (このデバイスだけの設定)")
    a.add_argument("--ca-cert", help="自己署名の HTTPS サーバ用の CA 証明書 (このデバイスだけの設定)")
    a.set_defaults(fn=cmd_init)
    a = sp.add_parser("link", help="プロジェクトを登録")
    a.add_argument("path", nargs="?")
    a.add_argument("--key", help="デバイス間で共通のプロジェクト名 (既定: git remote)")
    a.set_defaults(fn=cmd_link)
    for name, fn in (("push", cmd_push), ("pull", cmd_pull), ("verify", cmd_verify), ("list", cmd_list)):
        a = sp.add_parser(name)
        a.add_argument("--project", help="対象プロジェクトのパス (既定: カレント)")
        a.add_argument("--all", action="store_true", help="リンク済みの全プロジェクト")
        if name in ("push", "pull"):
            a.add_argument("--no-settings", action="store_true", help="設定は同期しない")
            a.add_argument("--quiet-hook", action="store_true", help=argparse.SUPPRESS)
        if name == "list":
            a.add_argument("--limit", type=int, default=20)
        a.set_defaults(fn=fn)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    a = sp.add_parser("items", help="共有する設定項目の確認・追加・削除")
    a.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    a.add_argument("name", nargs="?", help="~/.claude 直下の名前 (例: rules)")
    a.set_defaults(fn=cmd_items)
    a = sp.add_parser("secrets", help="秘密情報の扱い (mask / warn / block)")
    a.add_argument("mode", nargs="?", choices=["mask", "warn", "block"])
    a.set_defaults(fn=cmd_secrets)
    a = sp.add_parser("prune", help="共有先から古い会話を外す / 履歴を作り直して容量を減らす")
    a.add_argument("--older-than", type=int, metavar="日数")
    a.add_argument("--squash", action="store_true", help="git の履歴を1つにまとめて容量を減らす")
    a.add_argument("--dry-run", action="store_true", help="対象を表示するだけ")
    a.set_defaults(fn=cmd_prune)
    a = sp.add_parser("auto", help="起動時 pull / 終了時 push の自動化 (このデバイス)")
    a.add_argument("state", nargs="?", choices=["on", "off"])
    a.set_defaults(fn=cmd_auto)
    a = sp.add_parser("hook", help=argparse.SUPPRESS)
    a.add_argument("event", choices=["start", "end"])
    a.set_defaults(fn=cmd_hook)
    args = ap.parse_args()
    if args.cmd == "hook":
        try:
            args.fn(args)
        finally:
            sys.exit(0)
    if getattr(args, "quiet_hook", False):
        # フックからの実行: 失敗しても Claude Code の起動・終了を止めない。出力は stderr へ
        try:
            sys.stdout = sys.stderr
            args.fn(args)
        except BaseException as e:  # noqa
            print("ccshare: {}".format(e), file=sys.stderr)
        sys.exit(0)
    try:
        args.fn(args)
    except RuntimeError as e:
        sys.exit("ccshare: {}".format(e))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
