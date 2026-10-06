<div align="center">
    <h1>rig</h1>
</div>

<p align="center">
    <i>Manage multiple profiles for AI agent harnesses.</i>
</p>

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
