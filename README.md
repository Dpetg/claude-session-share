# session-share — continue Claude Code sessions across devices and OSes

English | [日本語](README.ja.md)

A Claude Code plugin that shares your **conversation history and settings** between Windows, macOS and Linux, across dual-boot setups and multiple machines, so you can `claude --resume` on one device a session you started on another.

## Features

- Send and receive conversations and settings with `/session-share:push` and `/session-share:pull`
- Resume even when the project lives at a different path on each OS (paths inside conversations are rewritten automatically)
- If the same conversation was continued on two devices, both versions are kept, the other one as a separate session
- Check that your project files match the other device (environment-specific files such as `.env` and `node_modules/`, and line-ending differences, are ignored)
- `/session-share:auto on` pulls when Claude Code starts and pushes when it exits

Project files themselves are expected to be shared with Git. This plugin only shares Claude Code's own data.

## Requirements

- Claude Code
- Python 3.8+ (standard library only; `py` works on Windows)
- git and a **private** git repository to sync through (GitHub etc.), or a synced folder such as OneDrive, Dropbox or Google Drive
- On Windows, Git for Windows (Git Bash)

## Install

```
/plugin marketplace add Dpetg/claude-session-share
/plugin install session-share@claude-session-share
```

## Usage

1. Create an empty **private** repository to sync through (for example `claude-sessions`).
2. On the first device, run `/session-share:setup https://github.com/<you>/claude-sessions`, then `/session-share:push`.
3. On every other device, install the plugin and run `/session-share:setup <same URL>`. Your settings and conversations are pulled in.
4. Run `/session-share:pull` when you start working and `/session-share:push` when you finish (inside the project directory), or turn on `/session-share:auto on`.
5. Open a pulled conversation with `claude --resume` (or `/resume`).

| Command | What it does |
|---|---|
| `/session-share:setup [URL\|folder]` | Initial setup |
| `/session-share:pull` | Pull conversations and settings from other devices |
| `/session-share:push` | Push this device's conversations and settings |
| `/session-share:list` | List shared conversations |
| `/session-share:verify` | Check that project files match the device that pushed last |
| `/session-share:items [add\|remove] <name>` | Add or remove shared settings items (e.g. `add rules`) |
| `/session-share:auto [on\|off]` | Pull on start / push on exit (per device) |
| `/session-share:status` | Show the current state |

## What is shared

| Shared | Not shared |
|---|---|
| Conversation history (from `~/.claude/projects/`, for linked projects only) | Credentials (`.credentials.json`) |
| `settings.json`, `CLAUDE.md`, `keybindings.json` | `~/.claude.json` (account info etc.) |
| `agents/`, `commands/`, `skills/`, `output-styles/`, `hooks/` | `settings.local.json` |
| Extra items you add with `items add`, such as `rules/` | Shell snapshots and other temporary files |

For settings that must differ per OS (such as a statusLine command), put them in `config/settings.windows.json`, `settings.mac.json` or `settings.linux.json` in your sync repository. They override the shared settings on that OS only.

> **Warning**: conversations can contain code and secrets. Always keep the sync repository private.

## How it works

Claude Code stores each conversation in `~/.claude/projects/<encoded working directory>/<session id>.jsonl`, and `--resume` looks in the folder that matches the current directory. Copying the files to a device where the project lives at a different path therefore does not work.

When pushing, session-share replaces absolute paths inside conversations (the project root and your home directory) with `{{CCSHARE_PROJECT}}` and `{{CCSHARE_HOME}}`. When pulling, it puts that device's paths back and writes the conversation into the right folder. Projects are matched across devices by their git `origin` URL; for projects without a remote, give them a shared name with `link --key`.

Sync state is tracked per session as a hash of the last synced version. If only one side changed, it is overwritten; if both changed, the other side's version is pulled in as a separate session.

## Tests

```
python3 tests/test_paths.py   # path conversion for Windows / macOS / Linux
bash tests/e2e.sh             # push / pull / conflicts / auto sync between two simulated devices
```

## License

MIT
