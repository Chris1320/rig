<div align="center">
    <h1>rig</h1>
</div>

<p align="center">
    <i>Manage multiple profiles for AI agent harnesses.</i>
</p>

> [!warning]
> **This project is still under development**!
>
> Back up existing harness data before migrating or experimenting with profiles.

`rig` is a profile manager for AI agent harnesses, written in Python. It isolates
configurations, credentials, and conversation data between profiles so you can
switch between work, personal, and project environments without conflicts.

> [!note]
> Supported Harnesses:
>
> | Agent Harness                                                                    | Identifier    |
> | -------------------------------------------------------------------------------- | ------------- |
> | **[OpenCode](https://opencode.ai/)**                                             | `opencode`    |
> | **[Claude Code](https://claude.com/product/claude-code)**                        | `claude-code` |
> | **[Google Antigravity CLI](https://antigravity.google/product/antigravity-cli)** | `antigravity` |

- Isolate harness state in `$HOME` using either `symlink` (default) or `move` strategies.
- Run a harness temporarily under any profile with per-harness lockfile protection (`rig run`), automatically restoring the previous default profile on exit.
- Export and import profile archives with optional cache exclusion.
- Pass `--json` (`-j`) to inspection and management commands for machine-readable output.

## Quickstart

```bash
# Initialize and import existing harness configs
rig setup

# Create work (default) and personal profiles
rig profile create claude-code work --desc "Work account" --default
rig profile create claude-code personal --desc "Personal account"

# List profiles and check harness profile status
rig profile list
rig status

# Switch default profile (optionally changing isolation strategy)
rig profile use claude-code work --strategy move

# Run a single session under another profile without changing the default
rig run claude-code personal -- --resume

# Export and import profile archives
rig profile export claude-code work -o claude-work.tar.gz
rig profile import claude-work.tar.gz --name work-laptop
```

## Roadmap

- [x] (CLI) Create new profiles
- [x] (CLI) List existing profiles
- [x] (CLI) Run harnesses in specific profiles
- [x] (CLI) Use existing profiles
- [x] (CLI) Delete existing profiles
- [x] (CLI) Export profiles for sharing or backup
- [x] (CLI) Import recently exported profiles
