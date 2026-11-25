FROM node:24-bookworm AS node-runtime
FROM python:3.12-bookworm

COPY --from=node-runtime /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# A global npm install sits under /usr/local, readable by whatever uid runs the task (PLAN D12).
ARG CLAUDE_CODE_VERSION
RUN test -n "$CLAUDE_CODE_VERSION" \
    && npm install --global "@anthropic-ai/claude-code@$CLAUDE_CODE_VERSION" \
    && claude --version

LABEL org.nl2repobench.harness-revision=$CLAUDE_CODE_VERSION
ENV CLAUDE_CONFIG_DIR=/claude-home/config \
    DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1
WORKDIR /workspace
ENTRYPOINT ["claude"]
