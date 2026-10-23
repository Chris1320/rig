FROM fedora:44

# hadolint ignore=DL3064
ARG USERNAME=user
ARG USER_UID=1000
ARG USER_GID=1000

# 1. Update system packages and install dependencies
# hadolint ignore=DL3041
RUN dnf -y update && \
    dnf -y install \
    bat \
    ca-certificates \
    curl \
    eza \
    fd-find \
    findutils \
    fzf \
    git \
    procps-ng \
    ripgrep \
    shadow-utils \
    sudo \
    tar \
    tealdeer \
    tmux \
    unzip \
    util-linux-user \
    wget \
    which \
    zoxide \
    zsh && \
    dnf clean all

# Create non-root user with passwordless sudo
RUN if id -u "${USER_UID}" >/dev/null 2>&1; then \
    existing_user=$(id -nu "${USER_UID}"); \
    if [ "$existing_user" != "${USERNAME}" ]; then \
    usermod -l "${USERNAME}" -d "/home/${USERNAME}" -m "$existing_user"; \
    groupmod -n "${USERNAME}" "$(id -ng "${USERNAME}")" 2>/dev/null || true; \
    fi; \
    else \
    groupadd -g "${USER_GID}" "${USERNAME}" 2>/dev/null || true; \
    useradd -l -u "${USER_UID}" -g "${USERNAME}" -m -s /bin/zsh "${USERNAME}"; \
    fi && \
    chsh -s /bin/zsh "${USERNAME}" && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}" && \
    chmod 0440 "/etc/sudoers.d/${USERNAME}"

# Set environment for the user
ENV USER=${USERNAME}
ENV HOME=/home/${USERNAME}
ENV SHELL=/bin/zsh
ENV PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/.bun/bin:/home/${USERNAME}/.opencode/bin:${PATH}"
ENV TERM=xterm-256color

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

USER ${USERNAME}
WORKDIR /home/${USERNAME}

# 2. Sets up SetupGuides-ZSH
RUN curl -fsSL https://raw.githubusercontent.com/Chris1320/SetupGuides-ZSH/main/install -o /tmp/install-zsh.sh && \
    bash /tmp/install-zsh.sh install --install-only && \
    rm -f /tmp/install-zsh.sh

# 3. Installs tmux config and plugins
RUN mkdir -p /home/${USERNAME}/.config/tmux && \
    curl -fsSL https://github.com/Chris1320/SetupGuides-dotfiles/raw/refs/heads/main/tmux/tmux.conf -o /home/${USERNAME}/.config/tmux/tmux.conf && \
    ln -sf /home/${USERNAME}/.config/tmux/tmux.conf /home/${USERNAME}/.tmux.conf && \
    if [ -x /home/${USERNAME}/.config/tmux/plugins/tpm/bin/install_plugins ]; then \
    /home/${USERNAME}/.config/tmux/plugins/tpm/bin/install_plugins || true; \
    fi

# 4. Installs uv and bun
RUN curl -fsSL https://astral.sh/uv/install.sh | bash && \
    curl -fsSL https://bun.sh/install | bash && \
    mkdir -p /home/${USERNAME}/.local/bin && \
    ln -sf /home/${USERNAME}/.bun/bin/bun /home/${USERNAME}/.local/bin/bun && \
    ln -sf /home/${USERNAME}/.bun/bin/bunx /home/${USERNAME}/.local/bin/bunx

# 5. Installs Antigravity CLI, Claude Code, OpenCode, and Codex
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash && \
    curl -fsSL https://claude.ai/install.sh | bash && \
    curl -fsSL https://opencode.ai/install | bash && \
    ln -sf /home/${USERNAME}/.opencode/bin/opencode /home/${USERNAME}/.local/bin/opencode && \
    CODEX_NON_INTERACTIVE=true bash -c "$(curl -fsSL https://chatgpt.com/codex/install.sh)"

# Pre-populate tealdeer cache
RUN tldr --update || true

# 6. Installs rig via uv tool
COPY --chown=${USERNAME}:${USERNAME} . /tmp/rig-source
RUN uv python install 3.14 && \
    uv tool install /tmp/rig-source && \
    rm -rf /tmp/rig-source

# Ensure environment variables are permanently configured in user's zsh env
# hadolint ignore=SC2016
RUN echo 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.opencode/bin:$PATH"' >> /home/${USERNAME}/.config/zsh/user_env.sh

# 7. Default CWD to /workspace (bind mount point)
# hadolint ignore=DL3066
USER root
RUN mkdir -p /workspace && chown -R ${USERNAME}:${USERNAME} /workspace
# hadolint ignore=DL3066
USER ${USERNAME}
WORKDIR /workspace

CMD ["/bin/zsh"]
