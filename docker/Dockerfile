FROM debian:bookworm-slim

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    python3 \
    xxd \
    && rm -rf /var/lib/apt/lists/*

# Install jj (Jujutsu)
RUN curl -fsSL https://github.com/jj-vcs/jj/releases/download/v0.28.2/jj-v0.28.2-x86_64-unknown-linux-musl.tar.gz \
    | tar xz -C /usr/local/bin/ jj \
    && chmod +x /usr/local/bin/jj

# Configure git (required for jj git backend)
RUN git config --global user.name "jj-mailbox" \
    && git config --global user.email "agent@jj-mailbox.local" \
    && git config --global init.defaultBranch main

# Configure jj
RUN mkdir -p ~/.config/jj && cat > ~/.config/jj/config.toml <<'EOF'
[user]
name = "jj-mailbox"
email = "agent@jj-mailbox.local"
EOF

# Install jj-mailbox CLI
COPY bin/jj-mailbox /usr/local/bin/jj-mailbox
RUN chmod +x /usr/local/bin/jj-mailbox

WORKDIR /mailbox
