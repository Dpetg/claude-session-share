# session-share — continue Claude Code sessions across devices and OSes

English | [日本語](README.ja.md)

A Claude Code plugin that shares your **conversation history and settings** between Windows, macOS and Linux, across dual-boot setups and multiple machines, so you can `claude --resume` on one device a session you started on another.

## Features

- Send and receive conversations and settings with `/session-share:push` and `/session-share:pull`
- Resume even when the project lives at a different path on each OS (paths inside conversations are rewritten automatically)
- If the same conversation was continued on two devices, both versions are kept, the other one as a separate session
- Check that your project files match the other device (environment-specific files such as `.env` and `node_modules/`, and line-ending differences, are ignored)
- `/session-share:auto on` pulls when Claude Code starts and pushes when it exits
- Also shares Claude Code's per-project auto memory (`~/.claude/projects/<project>/memory/`)
- Detects API keys, tokens and private keys before pushing and masks them as `[REDACTED:<kind>]` (your local copy is untouched)
- `/session-share:prune` removes old conversations from the sync repository and can squash its git history to reclaim space

Project files themselves are expected to be shared with Git. This plugin only shares Claude Code's own data.

## Requirements

- Claude Code
- Python 3.8+ (standard library only; `py` works on Windows)
- git and a **private** git repository to sync through (GitHub, GitLab, or your own git server), or a synced folder such as OneDrive, Dropbox or Google Drive
- On Windows, Git for Windows (Git Bash)

## Install

```
/plugin marketplace add Dpetg/claude-session-share
/plugin install session-share@claude-session-share
```

## Usage

1. On each device, install the plugin and run `/session-share:setup` in the directory of a project you want to share.
   - If you are logged in to the [GitHub CLI (gh)](https://cli.github.com/), this creates the private repository `<you>/claude-sessions` (or reuses it on later devices), pushes from the first device or pulls on later ones, and turns on auto sync (pull on start, push on exit), all in one step.
   - To use a cloud drive, run `/session-share:setup onedrive` (or `dropbox`, `gdrive`, `icloud`, `box`). It finds that drive's synced folder on the device and uses a `claude-sessions` folder inside it. If it can't find it, pass the path instead: `/session-share:setup "D:\OneDrive\claude-sessions"`
   - To use git without gh, pass the URL of an empty **private** repository: `/session-share:setup https://github.com/<you>/claude-sessions`
2. For other projects, run `/session-share:push` once in their directory; after that they sync automatically.
3. Open a pulled conversation with `claude --resume` (or `/resume`).

| Command | What it does |
|---|---|
| `/session-share:setup [onedrive\|dropbox\|gdrive\|icloud\|box\|URL\|owner/repo\|folder]` | Initial setup (with no argument, creates a private repository with gh) |
| `/session-share:pull` | Pull conversations and settings from other devices |
| `/session-share:push` | Push this device's conversations and settings |
| `/session-share:list` | List shared conversations |
| `/session-share:verify` | Check that project files match the device that pushed last |
| `/session-share:items [add\|remove] <name>` | Add or remove shared settings items (e.g. `add rules`) |
| `/session-share:auto [on\|off]` | Pull on start / push on exit (per device) |
| `/session-share:secrets [mask\|warn\|block]` | How to handle secrets found in conversations |
| `/session-share:slim [hooks\|images] [on\|off]` | Trim hook output and images from the shared copy |
| `/session-share:prune [--older-than DAYS] [--squash]` | Remove old conversations from the sync repository / squash its history |
| `/session-share:status` | Show the current state |

## Using a cloud drive

The synced folder of OneDrive, Dropbox, Google Drive, iCloud Drive or Box can be the sync target. No git or GitHub account is needed.

- `/session-share:setup onedrive` (and so on) looks for that drive's synced folder on the device: `%OneDrive%` on Windows, `~/Library/CloudStorage/...` on macOS, `G:\My Drive` for Google Drive for desktop, and similar. `drives` lists what it finds.
- Files are written through a temporary file, and files whose content did not change are not rewritten, so other devices don't pick up half-written files and unchanged files aren't uploaded again. A conversation whose last line is incomplete (still syncing) is skipped until the next pull.
- If two devices push the same conversation at once and the drive keeps a conflict copy (`<id> (1).jsonl`, `<id>-DESKTOP-XXX.jsonl`, ...), it is pulled in as a separate session, just like a git conflict.
- Unlike git, no history is kept. To move from GitHub, run `/session-share:setup onedrive`; the current contents are copied over.

## Using your own git server

Any git remote that `git` itself can reach works: Gitea, GitLab, a bare repository on a server you can SSH into, or a NAS.

```
# On the server (for a plain SSH server)
git init --bare /srv/git/claude-sessions.git

# In Claude Code, on each device
/session-share:setup me@myserver:/srv/git/claude-sessions.git
/session-share:setup ssh://git@git.example.com:2222/me/claude-sessions.git
/session-share:setup https://git.example.com/me/claude-sessions.git
```

- Setup checks the connection first and stops with the reason and what to check if it fails.
- To use a dedicated SSH key, or a CA certificate for a self-signed HTTPS server, run the script's `init` with `--ssh-key <private key>` or `--ca-cert <CA cert>`. These are stored only on that device. (`/session-share:setup` passes them for you if you mention them.)
- To move to another server, run setup again with the new URL. If the new repository is empty, everything is copied there; other devices then switch with the same command and continue from it.
- Projects are matched across devices by their git `origin` URL, ignoring the SSH/HTTPS difference and port numbers, so `git@host:me/app.git` and `https://host/me/app` count as the same project.

## What is shared

| Shared | Not shared |
|---|---|
| Conversation history (from `~/.claude/projects/`, for linked projects only) | Credentials (`.credentials.json`) |
| Per-project auto memory (`~/.claude/projects/<project>/memory/`) | |
| `settings.json`, `CLAUDE.md`, `keybindings.json` | `~/.claude.json` (account info etc.) |
| `agents/`, `commands/`, `skills/`, `output-styles/`, `hooks/` | `settings.local.json` |
| Extra items you add with `items add`, such as `rules/` | Shell snapshots and other temporary files |

For settings that must differ per OS (such as a statusLine command), put them in `config/settings.windows.json`, `settings.mac.json` or `settings.linux.json` in your sync repository. They override the shared settings on that OS only.

## Secrets

Before anything is pushed, conversations, memory and `settings.json` are scanned for API keys (Anthropic, OpenAI, Google, AWS, Stripe), GitHub/GitLab/Slack tokens, JWTs, private keys and `password=`-style assignments.

- `mask` (default): replace them with `[REDACTED:<kind>]` in the shared copy. Your local files are not modified, and a masked value in `settings.json` never overwrites the real value on a device that has it.
- `warn`: push as is and report what was found.
- `block`: do not push conversations that contain secrets.

The setting is stored in the sync repository and applies to every device. Detection is pattern-based and cannot catch everything.

> **Warning**: conversations can contain code and secrets. Always keep the sync repository private.

## Keeping the sync repository small

Every push commits the latest version of each changed conversation, so the repository grows over time.

- The shared copy keeps only the first 500 characters of what hooks print to stdout (turn off with `/session-share:slim hooks off`). A hook that echoes its tool input can make up nearly half of a conversation. Your local files are not modified.
- `/session-share:slim images on` also replaces pasted images with an "image omitted" note. Claude can no longer see those images in a resumed conversation.
- `/session-share:prune --older-than 90` removes conversations not touched for 90 days from the sync repository. They stay on each device, and continuing one shares it again.
- Conversations over 40MB are split by line into `<id>.jsonl.001`, `.002`, ... in the sync repository, because GitHub rejects files over 100MB. They are joined back into one conversation when pulled.
- `/session-share:prune --squash` rewrites the repository's history into a single commit (force push) to reclaim space. Other devices follow automatically on their next sync. This fails if the branch is protected against force pushes.
- `/session-share:status` shows how much space the repository uses.

## How it works

Claude Code stores each conversation in `~/.claude/projects/<encoded working directory>/<session id>.jsonl`, and `--resume` looks in the folder that matches the current directory. Copying the files to a device where the project lives at a different path therefore does not work.

When pushing, session-share replaces absolute paths inside conversations (the project root and your home directory) with `{{CCSHARE_PROJECT}}` and `{{CCSHARE_HOME}}`. When pulling, it puts that device's paths back and writes the conversation into the right folder. Projects are matched across devices by their git `origin` URL; for projects without a remote, give them a shared name with `link --key`.

Sync state is tracked per session as a hash of the last synced version. If only one side changed, it is overwritten; if both changed, the other side's version is pulled in as a separate session.

## Tests

```
python3 tests/test_paths.py   # path conversion for Windows / macOS / Linux
bash tests/e2e.sh             # push / pull / conflicts / auto sync between two simulated devices
bash tests/self_hosted.sh     # a self-hosted HTTPS git server with a self-signed certificate, and moving servers
bash tests/features.sh        # secret masking, memory sharing, prune and squash
bash tests/folder.sh          # cloud drive (synced folder): sharing, conflict copies, moving from git
bash tests/setup.sh           # setup with no argument (creates the repository with gh)
bash tests/large.sh           # splitting large conversations, and recovering from a rejected push
```

## License

MIT
