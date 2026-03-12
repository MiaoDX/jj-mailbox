FROM ghcr.io/openclaw/openclaw:latest

USER root

# Install jj-mailbox dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 xxd curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install jj
RUN curl -fsSL https://github.com/jj-vcs/jj/releases/download/v0.28.2/jj-v0.28.2-x86_64-unknown-linux-musl.tar.gz \
    | tar xz -C /usr/local/bin/ jj \
    && chmod +x /usr/local/bin/jj

# Configure git & jj
RUN git config --global user.name "openclaw-agent" \
    && git config --global user.email "agent@jj-mailbox.local" \
    && git config --global init.defaultBranch main \
    && mkdir -p /root/.config/jj \
    && printf '[user]\nname = "openclaw-agent"\nemail = "agent@jj-mailbox.local"\n' > /root/.config/jj/config.toml

# Install jj-mailbox CLI
COPY bin/jj-mailbox /usr/local/bin/jj-mailbox
RUN chmod +x /usr/local/bin/jj-mailbox

# Install jj-mailbox skill for OpenClaw
COPY skills/jj-mailbox /root/.openclaw/skills/jj-mailbox

WORKDIR /mailbox
