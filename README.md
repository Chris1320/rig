<div align="center">
    <h1>rig</h1>
</div>

<p align="center">
    <i>Manage multiple profiles for AI agent harnesses.</i>
</p>

> [!warning]
> **This project is still under development**!
>
> Many features are not yet implemented and/or unstable. Please use at your own risk.

`rig` is a profile manager for AI agent harnesses, written in Python. It isolates
configurations, credentials, and conversation data between profiles, enabling
switching between work, personal, and other environments without conflicts.

> [!note]
> Supported Harnesses:
>
> - **[OpenCode](https://opencode.ai/)**
> - **[Claude Code](https://claude.com/product/claude-code)**
> - **[Google Antigravity CLI](https://antigravity.google/product/antigravity-cli)**

- Create symlinks from standard paths directly into the target profile.
- Spawn the harness subprocess with environment overrides or temporary symlinks
  without altering your shell or global environment variables.
- Export profiles into shareable archives.

## Roadmap

- [ ] (CLI) Create new profiles
- [ ] (CLI) List existing profiles
- [ ] (CLI) Run harnesses in specific profiles
- [ ] (CLI) Use existing profiles
- [ ] (CLI) Delete existing profiles
- [ ] (CLI) Export profiles for sharing or backup
- [ ] (CLI) Import recently exported profiles
- [ ] Interactive Terminal UI
