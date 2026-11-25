"""Translate a benchmark startPro entry into Claude Code launch settings."""

import os
import re
from urllib.parse import urlparse

from logging_config import get_logger
from runner import positive_int

logger = get_logger(__name__)

EFFORTS = {"low", "medium", "high", "xhigh", "max"}
AUTH_HEADERS = {"x-api-key": "ANTHROPIC_API_KEY", "bearer": "ANTHROPIC_AUTH_TOKEN"}
# Claude Code clamps CLAUDE_CODE_AUTO_COMPACT_WINDOW to 100,000-1,000,000 tokens (HARNESS_NOTES §1).
MIN_COMPACT_WINDOW = 100_000


def resolve_model(entry: dict) -> tuple:
    """Return public launch settings and a separate secret-bearing environment."""
    for field in ("sk", "reasoningEfforts", "compat"):
        if field in entry:
            raise ValueError(f"{field} is not accepted by the claude backend")
    protocol = entry.get("protocol", "anthropic-messages")
    if protocol != "anthropic-messages":
        raise ValueError("protocol must be anthropic-messages: Claude Code speaks only the Anthropic Messages format")
    base_url = entry.get("baseUrl")
    # No fallback to NL2REPO_BASE_URL: it is exported for DeepSeek runs and would redirect a Claude run.
    if not isinstance(base_url, str) or urlparse(base_url).scheme not in {"http", "https"} or not urlparse(base_url).netloc:
        raise ValueError("baseUrl must be an http(s) URL with a host, for example https://api.anthropic.com")
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]  # Claude Code appends /v1/messages itself.
    auth_header = entry.get("authHeader", "x-api-key")
    if auth_header not in AUTH_HEADERS:
        raise ValueError(f"authHeader must be one of {sorted(AUTH_HEADERS)}")
    key_env = entry.get("apiKeyEnv", "NL2REPO_API_KEY")
    if not isinstance(key_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        raise ValueError("apiKeyEnv must name an environment variable")
    key = os.environ.get(key_env)
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"Set {key_env} before launching Claude Code")
    public = {"model": entry["moduleName"], "base_url": base_url, "auth_header": auth_header, "api_key_env": key_env}
    if "maxTokens" in entry:
        public["max_tokens"] = positive_int(entry["maxTokens"], "maxTokens")
    if "contextWindow" in entry:
        window = positive_int(entry["contextWindow"], "contextWindow")
        public["context_window"] = window
        if window < MIN_COMPACT_WINDOW and public["model"].startswith("claude-"):
            logger.warning("contextWindow below %d has no effect on a recognised Claude model ID", MIN_COMPACT_WINDOW)
    if "reasoningEffort" in entry:
        if entry["reasoningEffort"] not in EFFORTS:
            raise ValueError(f"reasoningEffort must be one of {sorted(EFFORTS)}")
        public["reasoning_effort"] = entry["reasoningEffort"]
    secret_env = {AUTH_HEADERS[auth_header]: key, "ANTHROPIC_BASE_URL": base_url}
    return public, secret_env


def model_environment(model: dict) -> list:
    """Non-secret --env NAME=VALUE pairs derived from the model settings (PLAN §4.3, §6.2)."""
    pairs = [f"ANTHROPIC_DEFAULT_HAIKU_MODEL={model['model']}"]
    if "max_tokens" in model:
        pairs.append(f"CLAUDE_CODE_MAX_OUTPUT_TOKENS={model['max_tokens']}")
    if "context_window" in model:
        pairs.append(f"CLAUDE_CODE_MAX_CONTEXT_TOKENS={model['context_window']}")
        if model["context_window"] >= MIN_COMPACT_WINDOW:
            pairs.append(f"CLAUDE_CODE_AUTO_COMPACT_WINDOW={model['context_window']}")
    return pairs
