# Claude Code as a harness: notes for the benchmark backend

Purpose: the facts about Claude Code that the backend design in `PLAN.md` depends on. Every fact carries a source key in square brackets. Anything not taken from a source is marked **NOT CHECKED** with what would verify it.

Nothing here was verified by running Claude Code. All of it is from the official documentation as retrieved on 2026-11-14, when the newest release in the changelog was 2.1.325 (2026-11-13) [CHG]. Claude Code changes quickly and many behaviours below are version-gated, so re-check against the version you pin.

## Sources

Every page is under `https://code.claude.com/docs/en/`. Append `.md` to get the raw text, for example:

```sh
curl -sSL https://code.claude.com/docs/en/headless.md | grep -n 'exits with code'
```

| Key | Page | Key | Page |
|---|---|---|---|
| HL | `headless` | PM | `permission-modes` |
| CLI | `cli-reference` | AUTH | `authentication` |
| SUB | `sub-agents` | DEV | `devcontainer` |
| TEAM | `agent-teams` | SETUP | `setup` |
| TOOLS | `tools-reference` | SESS | `sessions` |
| WF | `workflows` | LOOP | `agent-sdk/agent-loop` |
| CTX | `context-window` | TS | `agent-sdk/typescript` |
| HOW | `how-claude-code-works` | HOOKS | `hooks` |
| MC | `model-config` | GW | `llm-gateway` |
| ENV | `env-vars` | GWP | `llm-gateway-protocol` |
| PC | `prompt-caching` | GWC | `llm-gateway-connect` |
| CHG | `changelog` | HOST | `agent-sdk/hosting` |

A section name after the key, such as [HL § Basic usage], is the heading on that page.

## 1. Context compaction

- When the conversation approaches the limit, Claude Code replaces the message history with a summary and carries on; a full context window does not end the session. [CTX § When your context fills up] [HOW § When context fills up]
- The summary is produced by a separate model request that repeats the system prompt, tools and the history, and ends with a summarisation instruction. [PC § Compacting the conversation]
- What survives: the system prompt; project-root `CLAUDE.md` (re-read from disk); up to five of the files Claude read or edited, most recently modified first, and a file over 5,000 tokens comes back as a path only. Background commands and background subagents keep running. [CTX § What survives compaction]
- What can be lost: "detailed instructions from early in the conversation". The docs' advice is to put persistent rules in `CLAUDE.md`, which is re-injected. [HOW § When context fills up] [LOOP § Automatic compaction]
- Default trigger: when the conversation reaches the model's context limit. Models with a native 1M window compact at about 967K. Sonnet 4.6 and Opus 4.6 without the `[1m]` variant compact at 200K. [MC § Default auto-compact thresholds]
- **For a model ID Claude Code does not recognise (a gateway alias, a non-Claude model) it assumes a 1M window** and compacts against that. [GWP § Settings for unrecognized model IDs] [MC § Correct the window for a gateway or custom model ID]
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS` declares the real window. It applies on its own only to an unrecognised ID that has no `[1m]` suffix; for an ID such as `claude-sonnet-latest` that needs v2.1.324 or later. For an ID that resolves to a known Claude model it takes effect only together with `DISABLE_COMPACT`. [MC § Which IDs CLAUDE_CODE_MAX_CONTEXT_TOKENS applies to]
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW` sets how full the context may get before compaction. Range 100,000 to 1,000,000 tokens, capped at the model's window; it overrides the `--autocompact` flag and the `autoCompactWindow` setting. A bare number is read as tokens, so `200` means 200 tokens and is treated as the 100K minimum. [MC § Set the auto-compact window] [MC § Values and warnings for CLAUDE_CODE_AUTO_COMPACT_WINDOW]
- A limit below 100,000 tokens cannot be expressed with `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. [GWC § Troubleshoot gateway errors]
- `DISABLE_AUTO_COMPACT=1` turns off automatic compaction; `DISABLE_COMPACT=1` turns off all compaction. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (1 to 100) can only make compaction earlier. [ENV]
- If a gateway rewrites the upstream "prompt too long" error into its own wording, Claude Code does not recognise it and does not compact and retry. [GWC § Troubleshoot gateway errors]
- If one tool output is large enough to refill the context straight after each summary, Claude Code stops auto-compacting after a few attempts and reports an error. [HOW § When context fills up]
- Observable in the output stream as a message with `type: "system"`, `subtype: "compact_boundary"` and `compact_metadata.trigger` / `compact_metadata.pre_tokens`. [LOOP § Automatic compaction] [TS § SDKCompactBoundaryMessage] Transcript files spell the same record `compactMetadata.trigger` / `compactMetadata.preTokens`. [SUB § Auto-compaction]
- Subagents compact independently, in their own windows. [SUB § Auto-compaction]

## 2. Subagents and multi-agent features

Claude Code has three delegation mechanisms. Subagents and workflows work in a headless `-p` run; agent teams do not. [SUB § Which subagents run in the background] [WF § Turn workflows off] [TEAM § Enable agent teams]

**Subagents** (the `Agent` tool)

- A subagent runs in its own context window with its own system prompt and tool access, and returns only a summary to the caller. [SUB intro] [TOOLS § `Agent` row]
- Its initial context is its own system prompt (not the Claude Code system prompt), the delegation message Claude writes, `CLAUDE.md` files and a git status snapshot. It does not see the parent's history. [SUB § What loads at startup]
- Built-in types include `Explore` and `Plan` (read-only) and `general-purpose` (every tool available to subagents). Claude delegates on its own judgement. [SUB § Built-in subagents]
- Custom subagents come from `--agents` JSON, `.claude/agents/`, `~/.claude/agents/` or plugins. [SUB § Choose the subagent scope] [CLI § `--agents`]
- A subagent starts in the main conversation's working directory, so it shares the workspace unless its definition sets `isolation: worktree`. [SUB § Write subagent files]
- Model: by default the model of the conversation that starts it. `CLAUDE_CODE_SUBAGENT_MODEL` sets a default, below a per-call model and a definition's `model` field in precedence. [SUB § Choose a model]
- With nothing configured a subagent spawned from the main conversation starts in the background; in `claude -p` "Claude can wait, on its own judgment or when you ask". `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` makes Claude wait for subagents. [SUB § Which subagents run in the background] [SUB § Let Claude wait for a subagent]
- Limits: nesting up to three layers below the main conversation (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`); 20 running at once (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, v2.1.217 or later); no cap on the total over a session. [SUB § Let subagents spawn their own subagents] [SUB § Concurrent subagent limit]
- To turn delegation off, deny the `Agent` tool. `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` removes the built-in types in `-p` runs only. [SUB § Built-in subagents] A bare tool name in `--disallowedTools` removes that tool from Claude's context. [CLI § `--disallowedTools`]
- `SendMessage` resumes or messages a subagent by agent ID or name and does not need agent teams. Claude can give a subagent a name only when the session starts with agent teams enabled. A named subagent whose tools include `SendMessage` is told the names of `main` and of the other named agents. [SUB § Resume subagents] [SUB § Subagent names] [SUB § What loads at startup]
- Subagent transcripts are written to `~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`. [SUB § Resume subagents]
- In `stream-json` output, subagent messages carry `parent_tool_use_id`; main-conversation messages carry `null`. By default only the subagent's `tool_use` and `tool_result` blocks are emitted; `--forward-subagent-text` adds text and thinking (v2.1.211 or later). [HL § Follow subagent messages] [CLI § `--forward-subagent-text`]
- Subagent spend counts toward `--max-budget-usd`. [CLI § `--max-budget-usd`]

**Agent teams** (lead, teammates, shared task list, mailbox)

- Experimental and off by default; enabled with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. [TEAM intro]
- Components: a team lead (the main session), teammates (separate Claude Code instances, each with its own context window), a shared task list with pending, in-progress and completed states and file-locked claiming, and a mailbox at `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`. Teammates message each other directly. [TEAM § Architecture] [TEAM § Assign and claim tasks]
- **Not available headless.** "In non-interactive mode with the `-p` flag, including Agent SDK sessions, Claude doesn't spawn teammates, and a subagent that Claude names runs as an ordinary subagent even with agent teams enabled." [TEAM § Enable agent teams]
- Known limitations include task status lagging, one team per session and no nested teams. [TEAM § Limitations]

**Dynamic workflows**

- A JavaScript script, written by Claude, that orchestrates many subagents in the background. Available in `claude -p`. [WF intro] [WF § Turn workflows off]

**Task tools**

- `TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList` are provided by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5 and earlier models. On newer models and on unrecognised model IDs they are left out unless you opt in with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` or by naming them in `--allowedTools` or `--tools`. A subagent has them only when the session has them. [TOOLS § Task tool availability] [TOOLS § Task-tracking tools in subagents and agent teams]

## 3. Context, turns and stopping

- The loop ends when Claude produces a response with no tool calls. [LOOP § The loop at a glance]
- `--max-turns N` caps agentic turns; print mode only; no limit by default. Hitting it ends the run with result subtype `error_max_turns` and no final text. [CLI § `--max-turns`] [LOOP § Turns and messages]
- `--max-budget-usd X` stops the run once the client-side cost estimate reaches X; print mode only. The response that crosses the cap still completes, so spend can exceed it. Subtype `error_max_budget_usd`. [CLI § `--max-budget-usd`] [LOOP § Budget headroom]
- **NOT CHECKED:** whether the cost estimate is meaningful for a model ID Claude Code does not recognise. Verify by reading `total_cost_usd` and `modelUsage.*.costBasis` in the result of a gateway run. If it is zero or unknown, `--max-budget-usd` gives no protection there.
- **NOT CHECKED:** the CLI reference lists no wall-clock time limit flag. Verify with `claude --help` on the pinned version. The backend's wall-clock limit is therefore the container timeout.
- Result subtypes: `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. Every subtype carries `total_cost_usd`, `usage`, `num_turns` and `session_id`; only `success` carries `result`. [LOOP § Handle the result]
- "Claude Code exits with code 0 on success and a non-zero code when the run fails." [HL § Basic usage] When a query ends on an error result "the underlying Claude Code process also exits with a nonzero code". [LOOP § Handle the result]
- **NOT CHECKED:** that every non-success result subtype and every `is_error: true` result gives a non-zero exit code in every case. Verify by forcing each case (bad key, `--max-turns 1`) and comparing the exit code with the result event.
- SIGTERM: exit code 143, the running Bash command's process tree is terminated, and no result is recorded for the unfinished turn. [HL § Stop a run with SIGTERM]
- After the final turn a `-p` run stays open for background work it started, by default up to 10 minutes of idle waiting (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). [HL § Background tasks at exit]
- Bash tool commands time out after 2 minutes by default (`BASH_DEFAULT_TIMEOUT_MS`), with a model-settable maximum of 10 minutes (`BASH_MAX_TIMEOUT_MS`). [ENV]
- Failed API requests are retried, 10 times by default (`CLAUDE_CODE_MAX_RETRIES`); each attempt has 10 minutes to return response headers (`API_TIMEOUT_MS`). [ENV] Each retry emits a `system` / `api_retry` event. [HL § Handle API retries]
- Output size per request: `CLAUDE_CODE_MAX_OUTPUT_TOKENS`. For an unrecognised model ID the default is 32,000 and the cap 128,000. [ENV]
- Reasoning depth: `--effort low|medium|high|xhigh|max`; available levels depend on the model. [CLI § `--effort`]
- What fills the context before the task starts: system prompt, tool definitions, `CLAUDE.md`, auto memory and skill descriptions. [CTX § What the timeline shows] [LOOP § What consumes context]
- A `Stop` hook that exits with code 2 prevents Claude from stopping and continues the conversation. [HOOKS § Exit code 2 behavior per event]

## 4. Prompt caching

- Claude Code manages prompt caching itself. Each request re-sends the full context with new content appended, ordered so that rarely-changing content comes first: system prompt and tool definitions, then project context, then the conversation. [PC § How the cache is organized]
- Matching is by exact prefix; there is no per-file or per-segment caching. A change early in the request recomputes everything after it. [PC § How the cache is organized]
- Each model has its own cache. On most models each effort level does too. [PC § How the cache is organized]
- Compaction invalidates the conversation layer by design. The summarisation request itself reads the cached prefix while the cache is warm. [PC § Compacting the conversation]
- Time to live with an API key or cloud provider is five minutes for every request. `CLAUDE_CODE_PROMPT_CACHE_TTL=1h` raises it for the main conversation and `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` for subagents and compaction (v2.1.242 or later); one-hour writes cost more. [PC § Which TTL each request gets] [PC § Choose the TTL yourself]
- A subagent's first request does not read the parent's cache because its system prompt and tools differ; it warms its own. [PC § Subagents and the cache]
- The cache is effectively scoped to one machine and directory, because the prompt embeds paths and environment details. Parallel sessions in the same directory can share it. [PC § Cache scope]
- Behind a custom `ANTHROPIC_BASE_URL` "the cache lives wherever your requests are forwarded, and whether caching works depends on the gateway". If the gateway drops the `cache_control` markers but returns success, the whole history bills as uncached on every turn, with no error. [PC § Where the cache lives] [GWP § Feature pass-through, Prompt caching row]
- Claude Code prepends an attribution block to the system prompt. Through a custom base URL it is stable for the life of a conversation from v2.1.181; before that it changed on every request and broke prefix reuse. `CLAUDE_CODE_ATTRIBUTION_HEADER=0` omits it. [GWP § System prompt attribution block]
- Measuring: every result reports `cache_creation_input_tokens` and `cache_read_input_tokens`; `usage.cache_creation` splits writes into `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`. [PC § Check cache performance] [PC § Choose the TTL yourself]
- Turning it off: `DISABLE_PROMPT_CACHING=1`. [PC § Disable prompt caching]
- **NOT CHECKED: key-value (KV) cache reuse on a self-hosted inference server.** The Claude Code docs describe only API-level prompt caching and say nothing about an inference server's KV cache. Inference from the facts above: because requests are append-only with a stable prefix, a server that reuses the KV cache for a matching prefix should benefit between compactions, and lose it at each compaction. Verify on the target server by comparing its prefix-cache hit metrics, or time to first token, across consecutive turns of one run.

## 5. Running headless in a container, and structured output

- `claude -p "<prompt>"` runs non-interactively. [HL § Basic usage] The Agent SDK is a wrapper around the same thing: it spawns a `claude` CLI subprocess and talks to it over stdio. [HOST § The subprocess model]
- `--allowedTools` and `--disallowedTools` each take several space-separated values. [CLI, example column of those rows]
- Output formats: `text`, `json` (one object with the result, session ID and metadata) and `stream-json` (newline-delimited JSON events). The last line of the stream is a `result` message. [HL § Get structured output] [HL § Stream responses]
- Every documented `stream-json` example also passes `--verbose`. **NOT CHECKED:** whether `--verbose` is required with `-p --output-format stream-json`. Verify by running without it.
- The stream starts with a `system` / `init` event carrying `model`, `tools`, `claude_code_version`, `permissionMode` and `apiKeySource`. [HL § Read session metadata] [TS § SDKSystemMessage]
- The `result` event carries `subtype`, `is_error`, `num_turns`, `duration_ms`, `stop_reason`, `total_cost_usd`, `usage`, `modelUsage` (per model) and `permission_denials`; error subtypes add `errors`. [TS § SDKResultMessage]
- `--json-schema` with `--output-format json` returns schema-validated output in `structured_output`. [HL § Get structured output]
- **Permissions.** From v2.1.302 a `-p` run with no permission mode starts in Manual mode, where a tool call that needs approval is denied. [HL § Auto-approve tools] `--permission-mode bypassPermissions` (same as `--dangerously-skip-permissions`) is the documented way to run "fully unattended inside a container", and shows no dialog in non-interactive mode. [PM § Common setups] [PM § Skip all checks with bypassPermissions mode]
- **Root.** "On Linux and macOS, Claude Code refuses to start in `bypassPermissions` mode when running as root or under `sudo`." The check is skipped "inside a recognized sandbox". [PM § Skip all checks with bypassPermissions mode] [DEV § Run without permission prompts] **NOT CHECKED:** what counts as a recognised sandbox, and whether a plain Docker container does. Verify by running the image as uid 0.
- **Install.** `npm install -g @anthropic-ai/claude-code@X.Y.Z` pins a version; the docs recommend it for reproducible container builds together with `DISABLE_AUTOUPDATER=1`. The npm package asks for Node.js 22 or later; on an older Node.js, npm prints an `EBADENGINE` warning and still installs. The installed `claude` is a native binary that does not use Node at run time. [DEV § Enforce organization policy] [SETUP § Install with npm]
- **State location.** `CLAUDE_CONFIG_DIR` moves everything normally under `~/.claude` (settings, session history, plugins). [ENV] Transcripts are JSONL at `<config dir>/projects/<project>/<session-id>.jsonl`, where `<project>` is the working directory with non-alphanumeric characters replaced by `-`. The format "is internal to Claude Code and changes between versions". [SESS § Where transcripts are stored]
- **Credentials headless.** In `-p` mode `ANTHROPIC_API_KEY` "is always used when present", with no approval prompt. [AUTH § Authentication precedence]
- **Stdin.** Non-interactive mode reads stdin. If it cannot, Claude Code warns on stderr and continues with the prompt from the command line. [HL § Pipe data through Claude] **NOT CHECKED:** that a container started without `-i` does not block on stdin. Verify in the first smoke test.
- **Bare mode.** `--bare` skips hooks, skills, custom commands, subagents, plugins, MCP servers, auto memory and `CLAUDE.md`, gives Claude only the Bash, file read and file edit tools with a minimal system prompt, disables background tasks, and needs `ANTHROPIC_API_KEY` or an `apiKeyHelper`. It "will become the default for `-p` in a future release". [HL § Start faster with bare mode] [ENV, `CLAUDE_CODE_SIMPLE` row]
- **What `-p` loads without `--bare`.** The same as an interactive session, including anything in the working directory or `~/.claude`: hooks in a project's `.claude/settings.json` and servers in its `.mcp.json` run with no trust prompt. [HL § Start faster with bare mode]
- **Background network traffic.** `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` set to any non-empty value disables auto-updates, telemetry, error reporting and release-note fetches. Setting it to `0` still disables them. [ENV] [GWC § Turn off traffic outside the gateway path]
- Sizing guidance for one agent: 1 GiB RAM, 5 GiB disk, 1 CPU as a starting point. [HOST § Resources]

## 6. Custom endpoints and models

- `ANTHROPIC_BASE_URL` redirects model requests. Claude Code then treats the endpoint as the Claude API and posts to `/v1/messages?beta=true` under that base. [GWP § API formats] [GWP § Optional endpoints and startup traffic]
- The endpoint must speak one of three formats: Anthropic Messages (`ANTHROPIC_BASE_URL`), Amazon Bedrock InvokeModel (`CLAUDE_CODE_USE_BEDROCK=1`) or Google Cloud rawPredict (`CLAUDE_CODE_USE_VERTEX=1`). **There is no OpenAI-compatible format.** [GWP § API formats]
- **OpenAI-compatible endpoints.** Claude Code cannot call one directly. It can reach one only through a gateway that exposes the Anthropic Messages format and translates. Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway". [GW intro] **NOT CHECKED:** that any specific translating gateway works with the pinned Claude Code version, including tool calls and streaming. Verify with the gateway smoke test in `PLAN.md`.
- Credentials: `ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer`; `ANTHROPIC_API_KEY` as `x-api-key`. The wrong one gives `401`. `ANTHROPIC_AUTH_TOKEN` takes precedence when both are set. [GWC § How the credential variable maps to a header] [AUTH § Authentication precedence]
- Model selection: `--model <full name or alias>`, which overrides `ANTHROPIC_MODEL`. [CLI § `--model`]
- Claude Code also makes background requests. `ANTHROPIC_DEFAULT_HAIKU_MODEL` names the model used "for `haiku`, or background functionality". [MC § Environment variables] Behind an `ANTHROPIC_BASE_URL` gateway, unless that variable pins one, they go to the main model, or to the default Haiku model when `ANTHROPIC_API_KEY` holds an Anthropic Console key and `ANTHROPIC_AUTH_TOKEN` is unset. [GWP § Requests and defaults by connection method] **NOT CHECKED:** which background requests a `-p` run actually makes. Verify from the per-model keys of `modelUsage` in the result event.
- For an unrecognised model ID Claude Code sends everything current Claude models accept, including adaptive reasoning, effort and context-management fields. An upstream that rejects them returns `400`. `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` removes most pre-release fields but not the `thinking` field or `output_config.effort`. [GWP § Requests and defaults by connection method] [GWP § Disable pre-release capabilities] `CLAUDE_CODE_DISABLE_THINKING=1` omits the `thinking` parameter. [ENV]
- The gateway must stream events as they arrive; one that buffers the whole response makes Claude Code stall. [GWP § Streaming]
- Two requests bypass `ANTHROPIC_BASE_URL` and go to `api.anthropic.com`: the fast-mode availability check and the WebFetch domain safety check. [GWP § Optional endpoints and startup traffic]
- The `/v1/messages/count_tokens` endpoint is optional; without it Claude Code estimates context use by character count. [GWP § Optional endpoints and startup traffic]

## 7. Mapping the DeepSeek agent-teams model onto Claude Code

Left column sources are in this repo at commit `bbd664b`. The DeepSeek harness source itself is not in the repo, so its tool names are taken from `deepseek/prompt.txt` and are NOT CHECKED against the harness.

| DeepSeek agent teams | Claude Code | Verdict |
|---|---|---|
| Lead agent (`deepseek/prompt.txt:5,7`; the session with no parent, `deepseek/session_summary.py:57-58`) | Main conversation; "team lead" in agent teams [TEAM § Architecture] | Direct equivalent |
| Fixed number of teammates, `teammates` → `maxMembers` (`deepseek/config.py:68`) | No setting fixes a count. Team size and subagent count are decided by the model from the prompt [TEAM § Specify teammates and models] | No equivalent; prompt-driven only |
| Teammates with fresh context (`deepseek/prompt.txt:3`) | Subagents [SUB § What loads at startup]; teammates [TEAM § Context and communication] | Direct equivalent |
| Shared workspace (`deepseek/runner.py:50`) | Subagents start in the main working directory [SUB § Write subagent files] | Direct equivalent |
| Shared task board (`team/task` events, `deepseek/session_summary.py:43-45`) | Shared task list exists only in agent teams [TEAM § Assign and claim tasks]; Task tools are off by default on current models [TOOLS § Task tool availability] | Interactive only |
| Lead ↔ teammate and teammate ↔ teammate messages (`deepseek/prompt.txt:5`) | `SendMessage` [SUB § Resume subagents]; team mailbox [TEAM § Architecture] | Partial. **NOT CHECKED** whether two running subagents can exchange messages in a `-p` run; verify with a prompt that requires it and inspect `SendMessage` tool calls in the stream |
| Lead waits for every teammate (`wait_agent`, `deepseek/prompt.txt:7`) | Claude may wait for subagents in `-p`; forced by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` [SUB § Let Claude wait for a subagent] | Equivalent by configuration |
| Concurrency cap `maxActiveSubagents` (`deepseek/config.py:70`) | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` [SUB § Concurrent subagent limit] | Direct equivalent |
| File ownership via `writeScopes` (`deepseek/prompt.txt:3`) | None found. The docs warn that two teammates editing one file overwrite each other [TEAM § Avoid file conflicts]; `isolation: worktree` is the nearest mechanism [SUB § Write subagent files] | No equivalent |
| Per-agent session logs, format v4 (`deepseek/session_summary.py:11-16`) | Main transcript plus `subagents/agent-<id>.jsonl` [SUB § Resume subagents]; format unstable across versions [SESS § Where transcripts are stored] | Equivalent, weaker stability |
| Queued and delivered message events used to prove communication (`deepseek/session_summary.py:46-52`) | No documented delivered event. Nearest evidence is `Agent` and `SendMessage` tool calls with `parent_tool_use_id` in the stream [HL § Follow subagent messages] | No equivalent |
| One model for the whole team (`readme.md:58`) | Subagents inherit the main model by default [SUB § Choose a model] | Direct equivalent |

Consequence, drawn from the rows above: a faithful port of agent teams is not possible in a headless container today, because the Claude Code feature that matches it is interactive-only. What is possible headless is lead-plus-subagents (hub and spoke), with peer messaging unverified.
