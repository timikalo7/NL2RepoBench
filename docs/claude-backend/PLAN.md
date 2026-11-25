# Implementation plan: a `claude/` backend

Context: this repo is the ARIA TA4 fork of NL2RepoBench (University of Edinburgh and EPCC), used to profile LLM performance across hardware. Results are published openly.

Goal: add Claude Code as a third generation backend, selected with `"backend": "claude"` or `--backend claude`. At this stage only pipeline correctness matters, not model performance.

Rules from the project brief that this plan must keep: API keys come only from environment variables named by `apiKeyEnv` and are never written to a file; testing uses cheap models on 2 to 4 sample tasks, never the full set and never GLM.

Read first: `ANALYSIS.md` (how the DeepSeek backend plugs into the shared code; section 3.3 is the contract this plan must meet) and `HARNESS_NOTES.md` (Claude Code facts, cited as [HN §n] below). `file:line` references are to commit `bbd664b`.

Status: plan only. No code has been written and nothing here has been run. Items that depend on unverified Claude Code behaviour are marked **NOT CHECKED** and each has a test in section 8 that verifies it.

## 1. Scope of the first version

In scope:

- One Claude Code process per task, in a local Docker container, headless (`claude -p`).
- **Single agent.** The tools that start another agent are removed and running `claude` from Bash is denied (D3), so each task is meant to run as one conversation. T7 checks the documented delegation tools and T13 checks the Bash block. A form the deny rule cannot match, such as `sh -c 'claude …'`, is not blocked by the rule [HN §5]; that it then fails for lack of a credential (D8) is NOT CHECKED and recorded by T13.
- Same workspace layout, result file and evaluator as the other backends. No change to `runner.py`, `docker_self/batch_container.py`, `openhands/` or `deepseek/`.

Out of scope for the first version:

- Any multi-agent mode. See section 9 for what that loses and why.
- Non-Claude models behind a translating gateway, **for real benchmark runs**. The backend does not block them and stays endpoint-agnostic; they are unsupported by Anthropic (risk R1, section 10).

**Scope change, 2026-11-25 (Timi Kalejaiye, after the 20 Nov meeting).** There is no Anthropic or DeepSeek key, so *testing* goes through a gateway and a non-Claude model: Claude Code → LiteLLM proxy on the Docker host (Anthropic `/v1/messages` in, OpenAI `/chat/completions` out) → ELM (`https://elm.edina.ac.uk/api/v1`) serving `Qwen/Qwen3.5-397B-A17B-FP8` (262,144-token context, shared by input and output). LiteLLM is test infrastructure only and is not part of the backend. Never GLM. Every result from this path is labelled "Claude Code driving Qwen through LiteLLM". See section 8 and `TEST_RESULTS.md`.

## 2. Decisions

Each decision states what was chosen, why, and the alternative that was rejected.

| # | Decision | Why | Rejected alternative |
|---|---|---|---|
| D1 | Mirror the `deepseek/` package file for file (`config.py`, `runner.py`, `session_summary.py`, `prompt.txt`). | Reviewers can diff the two backends; the integration layer needs no change (ANALYSIS §3.1). | A generic harness-adapter base class. Premature with two examples of different shapes. |
| D2 | Run the `claude` CLI in print mode as the container entrypoint. | Same shape as DeepSeek (`docker/deepseek.Dockerfile:21`); the host needs no new Python dependency. | The Python Agent SDK inside the container. It spawns the same CLI [HN §5] and adds a layer for no gain here. |
| D3 | Single agent: remove the `Agent`, `Workflow` and `Skill` tools, and deny starting `claude` from Bash with permission rules (§6.2) rather than trying to detect it afterwards. `Agent` also covers conversation forks [HN §2]. `Skill` is removed because a skill with `context: fork` runs as a subagent and Claude invokes some bundled skills on its own [HN §2]; the workspace holds no skills of its own, so only bundled skills are lost. | Agent teams do not run headless [HN §2]. With delegation left on, Claude may run up to 20 subagents at once [HN §2], which makes request concurrency per task uncontrolled; that matters for a hardware-profiling benchmark. DeepSeek's profile also disables its alternative delegation tool (`deepseek/config.py:73-76`). | Leave Claude Code's default delegation on. Deferred to Open Question 2. |
| D4 | Full harness, not `--bare`. Isolation comes from a fresh `CLAUDE_CONFIG_DIR` and a workspace that contains only `start.md`. | `--bare` swaps in a minimal system prompt and a three-tool set [HN §5]. The default system prompt and tool set are what users run, and the harness is the thing being measured. This is still not Claude Code exactly as shipped: delegation, skill and web tools are removed (D3, D11) and flag-gated features are off (D14). | `--bare`: faster and more reproducible, and the docs call it "the recommended mode for scripted and SDK calls" and say it will become the default for `-p` [HN §5]. Deferred to Open Question 3. |
| D5 | `--permission-mode bypassPermissions`, container user is the host uid:gid, and the backend refuses to start when the host uid is 0. | The documented unattended-container mode [HN §5]; equivalent to DeepSeek's `DSH_PERMISSION_MODE=danger-full-access` (`docker/deepseek.Dockerfile:19`). Claude Code refuses this mode as root [HN §5]. Host uid:gid keeps artifacts readable, as in `deepseek/runner.py:49`. | `dontAsk` plus allow rules: silently denies some writes, which would look like model failure. Remapping root to uid 1000: more code; add only if a root host is really needed. |
| D6 | `--output-format stream-json --verbose`, captured as `stdout.jsonl`. | Events are written as they happen, so a timed-out run still leaves a log. The file name is fixed by shared code (`docker_self/batch_container.py:16`) and already means JSON lines. | `--output-format json`: a single object written only at the end, so a timeout leaves nothing. |
| D7 | `status` is `completed` only if the container run completed **and** the stream ends with a `result` event whose `subtype` is `success` and `is_error` is false. | Exit-code behaviour for every error case is NOT CHECKED [HN §3]. Without this guard, an API failure that exits 0 would send a half-written repo to the evaluator and be recorded as model performance. | Exit code only, as DeepSeek does (`deepseek/runner.py:66`). Revisit once test T9 shows the two always agree. |
| D8 | The API key reaches the container by variable name only, and `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` keeps it out of every Bash command the agent runs. An inline `sk` key in the config is rejected. The base URL is also passed by environment, never on the command line, and neither appears in the result JSON. | Project rule: keys come from `apiKeyEnv` and are never written to a file. Same mechanism as `deepseek/runner.py:45,54`. Without the scrub, a routine `env` or `.env` file would copy the key into `stdout.jsonl`, transcripts or the workspace, all of which may be published [HN §5]. Endpoint details are kept out of argv and errors by existing convention (`docker_self/batch_container.py:62`). Results are published. | Accepting `sk` for parity with the other backends (`deepseek/config.py:26`). |
| D8 update (2026-11-25, Timi Kalejaiye) | Keep the scrub. Run the container with `--security-opt seccomp=docker/claude-seccomp.json --security-opt systempaths=unconfined`, still as uid 1000, with no added capabilities and never `--privileged`. | The scrub needs bubblewrap (Claude Code 2.1.325 refuses to start without it), and bwrap cannot create namespaces under Docker's defaults (T4, `TEST_RESULTS.md`). `docker/claude-seccomp.json` is Docker's default profile (`moby/profiles` seccomp v0.2.4, the version Docker 29.9.2 vendors) plus one rule, with no `includes.caps`, allowing `clone` (without its namespace-flag filter), `unshare`, `mount`, `umount2`, `pivot_root` and `sethostname`. Neither the profile alone (bwrap cannot mount `/proc`) nor `systempaths=unconfined` alone (no namespaces) is enough; `sethostname` is needed for Claude Code's `--unshare-uts --hostname localhost`. **Security cost:** the agent can create user, PID, network, IPC and UTS namespaces and mount inside them, and `/proc` and `/sys` are not masked, so kernel information and namespace-related kernel attack surface are exposed to the agent's code, though still without capabilities in the init namespace. **Second consequence (found in T4, 2026-11-25):** with the scrub on, Claude Code 2.1.325 ignores `--permission-mode bypassPermissions`, forces the mode to `default` and prints "Declare allowedTools explicitly, or set CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0 to opt out". The backend therefore also passes `--allowedTools Bash Read Edit Write`; deny rules still apply. **Approved by Timi Kalejaiye, 2026-11-25 (session 3 brief).** After every model run, the `result` event's `permission_denials` must hold only denials from `Bash(claude *)` and `Bash(*/claude *)`; any other denial means `--allowedTools` did not work. Harbor's agent needs the same `allowed_tools` for parity (Part B). **NOT CHECKED** until a model run (T13): that these tools then run without a prompt in `-p` mode, and whether any other tool the agent tries is denied (`permission_denials`). **NOT CHECKED:** AppArmor hosts (this host has none; Docker's default AppArmor profile denies `mount`, so bwrap would also need `apparmor=unconfined` or a custom AppArmor profile), and EPCC hosts. | `--security-opt seccomp=unconfined` with `systempaths=unconfined` (works, drops the whole filter); `--privileged` (rejected); turning the scrub off (rejected: Bash would inherit the key). |
| D9 | `protocol` defaults to `anthropic-messages` for this backend and any other value is an error. | Claude Code speaks only the Anthropic Messages format to `ANTHROPIC_BASE_URL` [HN §6]. | Silently ignoring `protocol`: an `openai-completions` entry copied from the DeepSeek config would fail later with an opaque HTTP error. |
| D10 | Pin `ANTHROPIC_DEFAULT_HAIKU_MODEL` to the configured model. | Keeps background requests on the model under test [HN §6]. | Leaving it unset: a second model may appear in usage, and in the bill. |
| D11 | Remove `WebSearch` and `WebFetch`. | Parity with the DeepSeek profile, which disables web tools (`deepseek/config.py:73-76`, `readme.md:78`). `WebFetch` also calls `api.anthropic.com` regardless of the base URL [HN §6]. | Leaving them on. |
| D12 | Install with `npm install -g @anthropic-ai/claude-code@<pinned version>` on the same base as the DeepSeek image; enforce the pin through an image label. | The docs' recommended way to pin in a container [HN §5]. The native installer puts the binary under the installing user's home directory (`https://code.claude.com/docs/en/setup.md`, section "Install on network storage": "the native installer's default `~/.local/share/claude/versions/` directory … sit[s] in the home directory"), and the container runs as the host uid (D5), not as the user who built the image. A global npm install sits under `/usr/local`, outside any home directory. **NOT CHECKED:** that a native install made as root at build time is unreadable by the run-time uid; verify by building with the native installer and running `claude --version` as uid 1000. The same base (Python 3.12, Node 24, `docker/deepseek.Dockerfile:1-7`) gives both agents the same toolchain. | Native installer under a home directory. |
| D13 | No settings file. Everything is a CLI flag or an environment variable. | One place to read the whole configuration; nothing depends on settings precedence. `4bf6013` removed write-only run artifacts, so none is added. | A generated `settings.json` in the config directory. |
| D14 | Turn off feature-flag fetching, through `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` in the image. | A run should depend only on the pinned version and the run configuration, not on flags Anthropic serves at run time, which can change between runs and are not recorded. With a fresh config directory every run is a first session anyway, where flag-gated features can be missing, and a gateway run with a bearer token cannot fetch flags at all [HN §5]. It also keeps telemetry and update checks from leaving the container. Cost: flag-gated features are off; the documented list has sixteen items, among them Remote Control, the advisor tool, MCP tasks, Code Mode, synced skills and plugins, artifact comments and `claude import`, and none is something this plan uses (it has no MCP servers, no Windows hosts and no claude.ai login) [ENV § Features that need feature-flag fetching, on `https://code.claude.com/docs/en/env-vars.md`]. Whether that list is complete is NOT CHECKED [HN §5]. | Leave fetching on and reuse a warmed config directory: closer to an interactive install, but results would then depend on server-side flags at warm-up time. Open Question 3. |

## 3. Directory layout

New files:

| File | Purpose | Modelled on |
|---|---|---|
| `claude/__init__.py` | Docstring only | `deepseek/__init__.py` |
| `claude/config.py` | `resolve_model(entry)`: validates the model fields of a `startPro` entry and returns `(public settings, secret environment)` | `deepseek/config.py:14-52` |
| `claude/runner.py` | `start_claude(config)`, `_run_task(...)`, `_image_info(image)`, and the version pin | `deepseek/runner.py` |
| `claude/session_summary.py` | `summarize_run(stdout_path)`: reads `stdout.jsonl`, returns the `claude` block of the result | `deepseek/session_summary.py` |
| `claude/prompt.txt` | Task prompt | `deepseek/prompt.txt:1` |
| `tests/test_claude_backend.py` | Offline unit checks, including T5 (added 2026-11-25 so the checks are re-runnable) | none |
| `docker/claude.Dockerfile` | Image | `docker/deepseek.Dockerfile` |
| `scripts/build_claude.sh` | Image build | `scripts/build_deepseek.sh` |
| `config.claude.example.json` | Example config | `config.deepseek.example.json` |

Edited files:

| File | Edit |
|---|---|
| `main.py:12` | Add `"claude"` to `BACKENDS` |
| `main.py:33-38` | Add `elif backend == "claude": from claude.runner import start_claude; results = start_claude(config)` |
| `.gitignore` (after line 7) | Add `config.claude.json` |
| `readme.md` | New "Claude Code setup" section before "OpenHands setup" (`readme.md:80`); update the backend sentence (`readme.md:9`), the result-file note (`readme.md:106`) and add a "Claude Code artifacts" block like `readme.md:134-151` |

Untouched: `runner.py`, `docker_self/`, `openhands/`, `deepseek/`, `test_data_service.py`, `requirements.txt`, `template/`, `test_files/`.

`_image_info` is copied, not imported from `deepseek.runner`, so the two backends stay independent. If a fourth backend appears, hoist it into `docker_self/batch_container.py`.

## 4. Config schema

### 4.1 The `claude` object (mirrors `deepseek`, validated like `deepseek/runner.py:76-87`)

| Key | Type | Default | Maps to |
|---|---|---|---|
| `image` | string | `nl2repobench-claude:<pinned version>` | Image to run |
| `task_timeout_seconds` | positive int | `7200` | Wall-clock limit, enforced by `run_batch_container` (`docker_self/batch_container.py:38-45`) |
| `max_turns` | positive int | none | `--max-turns` [HN §3] |
| `max_budget_usd` | positive number | none | `--max-budget-usd` [HN §3] |
| `prompt_file` | path | `claude/prompt.txt` | Prompt to send. For tests such as T13 only; benchmark runs leave it unset |
| `gateway_env` | object of `NAME: "value"` strings | `{}` | Extra `--env NAME=value` pairs for a gateway path (section 10), for example `API_TIMEOUT_MS` or `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`. Rejects names the backend sets itself and names that look like credentials (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`). Added 2026-11-25 for the ELM test path; which values it needs is decided by the gateway smoke runs, and the option is removed again if they need none (`TEST_RESULTS.md`) |

Unknown keys are an error. `max_pool_size` and `evaluate` stay top-level, as for DeepSeek (`deepseek/runner.py:74-75`); `max_pool_size` defaults to 1.

Example (`config.claude.example.json`):

```json
{
  "backend": "claude",
  "evaluate": false,
  "max_pool_size": 1,
  "claude": {
    "task_timeout_seconds": 7200
  },
  "startPro": [
    {
      "moduleName": "YOUR_MODEL_ID",
      "protocol": "anthropic-messages",
      "baseUrl": "https://api.anthropic.com",
      "apiKeyEnv": "NL2REPO_API_KEY",
      "proNameList": ["jsonlines"]
    }
  ]
}
```

### 4.2 `startPro` fields as this backend reads them

| Field | Handling | Becomes |
|---|---|---|
| `moduleName` | Required (already validated by `runner.py:57-59`) | `--model <moduleName>` |
| `proNameList` | Required (`runner.py:60-67`) | One job per task |
| `protocol` | Optional; must be `anthropic-messages` (D9) | Nothing |
| `baseUrl` | **Required**, an `http(s)` URL with a host; use `https://api.anthropic.com` for the Anthropic API. There is deliberately no fallback to `NL2REPO_BASE_URL`, unlike `deepseek/config.py:20`: that variable is exported for DeepSeek runs (`readme.md:32`) and would silently redirect a Claude run. A missing or empty value fails config validation, before any container starts. A single trailing `/v1` is stripped, because Claude Code appends `/v1/messages` itself [HN §6]. | `ANTHROPIC_BASE_URL` |
| `apiKeyEnv` | Optional, default `NL2REPO_API_KEY` (as `deepseek/config.py:23`). The named variable must be set and non-empty. | Its value is passed as `ANTHROPIC_API_KEY`, or as `ANTHROPIC_AUTH_TOKEN` when `authHeader` is `bearer` |
| `authHeader` | **New**, optional: `x-api-key` (default) or `bearer`. Needed because the two variables map to different HTTP headers and the wrong one gives 401 [HN §6]. | Selects the credential variable |
| `sk` | Rejected (D8) | Error |
| `maxTokens` | Optional positive int | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` [HN §3]. Not set when absent. |
| `contextWindow` | Optional positive int. See 4.3. | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and `CLAUDE_CODE_AUTO_COMPACT_WINDOW` |
| `reasoningEffort` | Optional: `low`, `medium`, `high`, `xhigh` or `max` | `--effort` [HN §3] |
| `reasoningEfforts`, `compat` | Rejected: they configure DeepSeek's pi-ai transport (`readme.md:54-55`) and have no Claude Code meaning | Error |

Other backends ignore fields they do not know (ANALYSIS G1), so `authHeader` does not break existing configs.

### 4.3 `contextWindow`

Unlike DeepSeek, there is no default (DeepSeek defaults to 131072, `deepseek/config.py:31`). Claude Code knows the window of every Claude model and a default would shrink it.

| Case | What the backend sets | Effect [HN §1] |
|---|---|---|
| `contextWindow` absent | Nothing | Claude models: correct built-in window. Unrecognised model ID: Claude Code assumes 1M, so requests will overflow a smaller model. |
| `contextWindow` ≥ 100000 | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, both to that value | Unrecognised ID: window declared, compaction at that size. Recognised Claude ID: the first variable is ignored, the second makes compaction happen earlier. |
| `contextWindow` < 100000 | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` only | Works for an unrecognised ID. For a recognised Claude ID it has no effect; log a warning. |

**NOT CHECKED:** that setting both variables together behaves as the table says. Test T8 verifies it by forcing an early compaction.

The README must say: set `contextWindow` for any model that is not a Claude model.

## 5. Docker image

`docker/claude.Dockerfile`, built by `scripts/build_claude.sh`:

- Base and system packages as in `docker/deepseek.Dockerfile:1-7`: `python:3.12-bookworm`, `/usr/local` copied from `node:24-bookworm`, then `build-essential git ripgrep ca-certificates`, **plus `bubblewrap`** (added 2026-11-25: Claude Code 2.1.325 refuses to start with `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` without it, found in T4; see `TEST_RESULTS.md`). Under Docker's default security options bwrap still cannot create its namespace as a non-root user; **resolved 2026-11-25** by the seccomp profile and `systempaths` option in D8 and §6.2.
- Build argument `CLAUDE_CODE_VERSION`; `npm install --global @anthropic-ai/claude-code@$CLAUDE_CODE_VERSION`; then `claude --version` as a build step so a missing binary fails the build.
- Label `org.nl2repobench.harness-revision=$CLAUDE_CODE_VERSION`, the same label key DeepSeek uses (`docker/deepseek.Dockerfile:18`). `claude/runner.py:_image_info` rejects an image whose label does not equal the pin. DeepSeek uses a prefix match instead (`startswith`, `deepseek/runner.py:29`), because its build writes the full commit SHA into the label while the pin is the short form (`scripts/build_deepseek.sh:5,9,14`). Here the label and the pin are the same version string, so exact equality is correct.
- Environment baked into the image, mirroring `docker/deepseek.Dockerfile:19`: `CLAUDE_CONFIG_DIR=/claude-home/config`, `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` [HN §5]. `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` also turns off feature-flag fetching (D14); the scrub keeps the key out of Bash commands (D8).
- `WORKDIR /workspace`, `ENTRYPOINT ["claude"]`.

`scripts/build_claude.sh [image_tag]`: holds the version pin, builds from an empty temporary directory with `--file docker/claude.Dockerfile` so that no repo content or local credential enters the build context (the same intent as `scripts/build_deepseek.sh:4`). Unlike the DeepSeek script it needs no local harness checkout, only network access to the npm registry.

**The pin lives in two places**, `claude/runner.py` and `scripts/build_claude.sh`, as it does for DeepSeek (ANALYSIS G10). Proposed starting value: `2.1.325`, the newest release on 2026-11-14 [HN intro]. **NOT CHECKED:** that this version installs and behaves as documented. Tests T3 and T4 verify it; pin whichever version passes them.

## 6. Dispatch and the per-task run

### 6.1 `start_claude(config)` (order matters: all validation before any container)

1. `max_pool_size` (default 1) and `evaluation_enabled(config)`.
2. Validate the `claude` object (4.1).
3. Refuse to continue if `os.getuid() == 0` (D5), with a message that says why.
4. `model_tasks(config)` then `resolve_model(entry)` for each (4.2).
5. `_image_info(image)`.
6. One `Job(run_id, "claude", model, task.proName, partial(_run_task, ...))` per task; `run_batch(jobs, pool_size)`.

### 6.2 `_run_task`

Directories, created under `workspaces/<run_id>/` (same pattern as `deepseek/runner.py:36-44`):

```text
workspace/            start.md copied in; bind-mounted at /workspace
claude-home/config/   bind-mounted; CLAUDE_CONFIG_DIR; transcripts land in projects/-workspace/ (naming rule in [HN §5])
claude-home/user/     HOME for the container user
prompt.txt            the exact prompt
```

A fresh `claude-home` per task means no settings, memory or session carries from one task to the next.

`docker create` arguments, in this order:

```text
--init
--user <host uid>:<host gid>
--security-opt seccomp=<repo>/docker/claude-seccomp.json   (added 2026-11-25, D8 update)
--security-opt systempaths=unconfined                       (added 2026-11-25, D8 update)
--volume <workspace>:/workspace:rw
--volume <claude-home>:/claude-home:rw
--env HOME=/claude-home/user
--env PATH=/claude-home/user/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
--env ANTHROPIC_API_KEY            (or ANTHROPIC_AUTH_TOKEN; name only, no value)
--env ANTHROPIC_BASE_URL           (name only; always set, see 4.2)
--env ANTHROPIC_DEFAULT_HAIKU_MODEL=<moduleName>
--env CLAUDE_CODE_MAX_OUTPUT_TOKENS=<maxTokens>          (when set)
--env CLAUDE_CODE_MAX_CONTEXT_TOKENS=<contextWindow>     (per 4.3)
--env CLAUDE_CODE_AUTO_COMPACT_WINDOW=<contextWindow>    (per 4.3)
--add-host host.docker.internal:host-gateway
<image id>
-p <prompt>
--output-format stream-json --verbose
--model <moduleName>
--permission-mode bypassPermissions
[--effort <reasoningEffort>] [--max-turns <n>] [--max-budget-usd <x>]
--allowedTools Bash Read Edit Write      (added 2026-11-25, D8 update)
--disallowedTools Agent Workflow Skill WebSearch WebFetch "Bash(claude *)" "Bash(*/claude *)"
```

The two scoped `Bash(...)` entries are deny rules: they keep `claude` and `/usr/local/bin/claude` from being started by the agent, in every permission mode including `bypassPermissions` [HN §5]. Each goes in as one argv element, so no shell quoting is involved.

Three things an implementer could get wrong:

- **Argument order.** `--disallowedTools` takes several values [HN §5], so it goes last and the prompt follows `-p` directly. Whether a prompt placed after it would be consumed as a tool name is NOT CHECKED; this ordering avoids the question.
- **Variables passed by name.** `--env NAME` with no value copies `NAME` from the environment of the `docker` process. `_run_task` builds that environment as a copy of `os.environ` with `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`) and `ANTHROPIC_BASE_URL` set from the resolved config. This overrides anything the developer happens to have exported under those names, so the container always gets the key named by `apiKeyEnv`. No other host `ANTHROPIC_*` or `CLAUDE_*` variable is forwarded.
- **Stdin.** The container has no stdin attached. Claude Code is documented to continue with the command-line prompt [HN §5]; NOT CHECKED, verified by T4.

Then `run_batch_container(arguments, f"claude-{run_id}", run_dir, timeout, env=env)`, the same call as `deepseek/runner.py:58-59`.

**Timeout.** On expiry the shared code runs `docker stop --time 10` (`docker_self/batch_container.py:44`). `--init` runs an init process "that forwards signals and reaps processes" (Docker CLI reference, `--init` row: `https://github.com/docker/cli/blob/master/docs/reference/commandline/container_run.md`), so SIGTERM reaches Claude Code, which then stops its Bash child processes and exits 143 without writing a result event [HN §3]. **NOT CHECKED:** that Claude Code exits within Docker's 10-second grace period; T10 records 143 or 137. The run is recorded as `generation_status: "timeout"`, `status: "failed"`, and is not evaluated (ANALYSIS G5).

### 6.3 Prompt

`claude/prompt.txt` is the first paragraph of `deepseek/prompt.txt:1` with its last sentence replaced (approved by Timi Kalejaiye, 2026-11-25). "Produce a runnable repository, including its package metadata and dependencies." became the sentence below, because the grader deletes package files and grades in a fresh container (`TEST_RESULTS.md`, "Known upstream issue"). **The two backends therefore no longer state the task identically**; `deepseek/` is unchanged. Harbor's `instruction.md` uses the same text word for word.

> Read /workspace/start.md and implement the complete project in /workspace. Follow the document's API Usage Guide and runtime requirements. Do not rely on package or dependency files: grading deletes every file named setup.py, pyproject.toml, setup.cfg, requirements.txt, requirements-dev.txt, requirements-test.txt, tox.ini, pytest.ini, poetry.lock, Pipfile, Pipfile.lock, environment.yml, conda-env.yaml, manifest.in or MANIFEST.in anywhere in the repository, then runs the tests in a fresh environment with /workspace on PYTHONPATH, so nothing declared in those files or installed while you work will be available.

Nothing about teams or delegation is added.

## 7. Result mapping

The result keeps the DeepSeek shape (ANALYSIS §5). Only the backend-specific block changes: `team` becomes `claude`. The evaluator is untouched because it reads only `status`, `workspace_path` and `task_uuid` (ANALYSIS §3.3).

| Key | Source for the Claude backend | Same as DeepSeek? |
|---|---|---|
| `container_name`, `container_id`, `exit_code`, `attach_exit_code`, `generation_status`, `stdout_path`, `stderr_path`, `container_log_path`, `error`, `cleanup_error`, `duration_seconds` | `run_batch_container` | Identical (shared code) |
| `task_uuid`, `workspace_path` | `_run_task` | Identical |
| `image` | `{tag, id, harness_revision}` from `_image_info`; `harness_revision` is the Claude Code version | Same shape |
| `session_logs_path` | `workspaces/<run_id>/claude-home/config/projects` | Same key |
| `config_path` | Omitted. There is no generated config file (D13) and no shared code reads the key (ANALYSIS §3.3). | **Differs** |
| `claude` | `summarize_run(stdout.jsonl)`, below | Replaces `team` |
| `status` | D7 | **Stricter** than DeepSeek |
| `evaluation_status`, `test_score`, `score`, `post_process_result`, `evaluation_workspace_path`, `evaluation_error` | `evaluate_result` | Identical (shared code) |
| `backend` (`"claude"`), `module_name`, `pro_name`, `saved_at` | `run_batch` | Identical (shared code) |

The `claude` block, all read from `stdout.jsonl` (field names in [HN §5] and [HN §1]):

| Field | From | Affects `status`? |
|---|---|---|
| `status` (`completed` or `incomplete`), `errors` | `completed` when a final `result` event exists with `subtype == "success"` and `is_error == false` | Yes (D7) |
| `result_subtype`, `is_error`, `stop_reason`, `num_turns`, `session_id` | `result` event | No |
| `total_cost_usd`, `usage`, `model_usage` | `result` event (`modelUsage` holds one entry per model) | No |
| `claude_code_version`, `model`, `tools` | `system`/`init` event | No |
| `compactions` | Count of `system`/`compact_boundary` events | No |
| `api_retries` | Count of `system`/`api_retry` events | No |
| `permission_denials` | Length of the `result` event's list | No |
| `delegations` | Count of messages with a non-null `parent_tool_use_id` (subagent messages [HN §2]) plus `tool_use` blocks named `Agent`, `Workflow` or `Skill`; expected 0 | No |

The reader finds each event by its `type` and `subtype`, never by line number: the `init` event is not always first [HN §5]. It must tolerate a truncated or partly unparsable file (timeouts cut it short) and must not fail the task because of an unknown event type.

## 8. Test plan

**Test model (2026-11-25):** `Qwen/Qwen3.5-397B-A17B-FP8` on ELM through LiteLLM (section 1). Pass conditions that assume a Claude model on the Anthropic API are adapted per test and recorded in `TEST_RESULTS.md`: `max_budget_usd` stays unset (R6), runs are capped with `max_turns` and `task_timeout_seconds`, and Claude-only behaviour (one `model_usage` key, compaction, `result_subtype` values) is reported as observed or NOT CHECKED, never as a backend failure. Up to 3 gateway smoke runs (`jsonlines`, `max_turns: 2`) settle `claude.gateway_env` before T13; T8 is not run.

Constraints: cheap models only, never GLM, never the full task set. Two sample tasks, `jsonlines` and `records`: both are labelled Easy in `test_files/task_difficulty.csv`, have the two smallest specifications in the set (15 to 16 KB; `wc -c test_files/*/start.md | sort -n | head -3`) and 27 and 31 tests (`test_case_count.txt`). `jsonlines` is also the task the DeepSeek commit messages report being checked with. Total paid usage: at most seven runs, four of them full generations of an Easy task and one (T13) a short scripted run.

Which model to use is Open Question 1. The plan assumes one inexpensive Claude model reached directly on the Anthropic API.

**Free: no model calls**

| # | Test | Passes when |
|---|---|---|
| T1 | `python main.py --backend nosuch` and `--help` | `claude` is listed among the choices; `openhands` and `deepseek` still are |
| T2 | Config validation, each run before any container exists: unknown key in `claude`; `protocol: "openai-completions"`; `sk` present; key variable unset; `reasoningEfforts` present; `baseUrl` empty while `NL2REPO_BASE_URL` is exported | Each exits with a message naming the field; no `workspaces/` directory is created |
| T3 | `bash scripts/build_claude.sh`, then `docker run --rm --entrypoint claude <image> --version`, and the same with `--user 1000:1000` | Both print the pinned version (the second checks the run-time-user concern in D12); the image label matches |
| T4 | Run one task with `baseUrl` pointing at a closed local port, a dummy key and `task_timeout_seconds: 120` (connection retries can otherwise take minutes [HN §3]) | `stdout.jsonl` contains a `system`/`init` event, which shows the process started and did not block on stdin; `result/<id>.json` exists with `status: "failed"`; the container is removed; `grep -r` finds neither the dummy key nor the URL under `result/` or anywhere in `workspaces/<run_id>/` (including `stdout.jsonl`, `stderr.log` and `claude-home/`). The documented `api_retry` event fields carry no URL [HN §3]; whether error text, `stderr.log` or transcripts echo the endpoint is NOT CHECKED. If any do, record which run files are safe to publish |
| T5 | `summarize_run` on three hand-written fixtures: a success stream, an `error_max_turns` stream, a file cut off mid-line | Returns `completed`, `incomplete`, `incomplete` without raising |
| T6 | Run as root (for example in a root shell) | Refuses before scheduling, with the D5 message |

**Paid: cheap model, `jsonlines`, `evaluate: false`**

| # | Test | Passes when |
|---|---|---|
| T7 | Full generation run, `max_budget_usd` set low | `generation_status` and `status` are `completed`; `claude.result_subtype` is `success`; `claude.model_usage` has exactly one key, the configured model (D10); `claude.delegations` is 0 and `claude.tools` lacks the five removed tools (D3, D11); Bash tool calls succeed (the scrub's PID namespace works, D8); `grep -rlF -- "$NL2REPO_API_KEY" workspaces/<run_id> result/` prints nothing (it prints file names only, never the key); transcripts exist under `session_logs_path`; list what Claude Code left in `workspace/` besides the repo (risk R5) |
| T8 | Optional. Same, with `contextWindow: 100000` | `claude.compactions` ≥ 1. If the run finishes below 100K tokens the test is inconclusive and 4.3 stays NOT CHECKED. |
| T9 | `max_turns: 2` | `claude.result_subtype` is `error_max_turns`; `status` is `failed`; `evaluation_status` is `skipped`. Record `exit_code`: an exit code of 0 here is a finding about Claude Code that confirms D7 is needed, not a backend failure. |
| T10 | `task_timeout_seconds: 60` | `generation_status` is `timeout`; `exit_code` is 143, or 137 if Claude Code did not exit within the 10-second grace period (record which); the container is removed; `stdout.jsonl` holds the events up to the stop |

**Paid: evaluation hand-off**

| # | Test | Passes when |
|---|---|---|
| T11 | `evaluate: true`, tasks `jsonlines` and `records`, `max_pool_size: 2` | Two result files; `evaluation_status` is `completed`; `score` is an integer between 0 and the task's test count; `workspace/` is unchanged and `evaluation/workspace/` exists. The score itself is not a pass criterion. Needs GHCR access and amd64 emulation on ARM (ANALYSIS G8). |

**Paid: isolation of the key and of nested runs**

| # | Test | Passes when |
|---|---|---|
| T13 | `jsonlines`, `evaluate: false`, `max_turns: 6`, `prompt_file` set to a test prompt: "Use the Bash tool to run each command separately and report its output: `env`, then `claude -p hi`, then `/usr/local/bin/claude -p hi`, then `sh -c 'claude -p hi'`." | The `env` tool result in `stdout.jsonl` contains no `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` line; `grep -rlF -- "$NL2REPO_API_KEY" workspaces/<run_id> result/` prints nothing; the result event's `permission_denials` lists the `claude -p hi` and `/usr/local/bin/claude -p hi` calls, which shows the block holds. For `sh -c 'claude -p hi'`, which the rule cannot match [HN §5], record what happened: expected an authentication failure because the scrub removed the key (NOT CHECKED until this run). If it reached the model, the block is incomplete; record it as a finding and do not run T7 to T11 until it is decided. |

**Regression**

| # | Test | Passes when |
|---|---|---|
| T12 | `python main.py --config config.deepseek.example.json` with no DeepSeek image built | Fails with "DeepSeek image is unavailable" (`deepseek/runner.py:26`), which shows the existing dispatch path is unchanged. Needs `NL2REPO_API_KEY` set to a dummy value and `NL2REPO_BASE_URL` set to a dummy `http(s)` URL with a host, such as `http://127.0.0.1:9`; anything else fails earlier with "Set baseUrl or NL2REPO_BASE_URL" (`deepseek/config.py:20-22`), which would look like a regression. |

Not in this plan: any gateway or non-Claude model test. If Open Question 1 asks for it, add one `jsonlines` run through the chosen gateway and expect to iterate on the variables in [HN §6].

## 9. What the single-agent version loses

The full mapping is in HARNESS_NOTES §7. Compared with the DeepSeek backend, the first version has:

- **No teammates.** One context window does all the work, so the long-horizon load falls on compaction [HN §1] instead of being spread across agents.
- **No shared task board and no inter-agent messages**, so no analogue of `team.status` and its checks (`readme.md:68-76`). The `claude` block reports run health instead.
- **No parallelism inside a task.** Wall-clock time and request concurrency are not comparable with a three-agent DeepSeek run; concurrency per task is 1, against a lead plus `teammates`.
- **No review by a second agent**, which the DeepSeek prompt requires (`deepseek/prompt.txt:3,5`).

A later multi-agent version cannot be a port of agent teams, because Claude Code's agent teams are interactive-only [HN §2]. The realistic second step is lead plus subagents: drop `Agent` from the removed tools, add a `subagents` count to the `claude` object, cap concurrency with `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, force waiting with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, pass `--forward-subagent-text`, and count `Agent` calls from the stream. Peer-to-peer messaging between subagents in a headless run is NOT CHECKED [HN §7].

## 10. Self-hosted models on our own GPUs (works, unsupported)

This path is not part of the first version and nothing here has been run. It is written down because profiling models on our own hardware may be the project's main interest (Open Question 1).

**How it works.** SGLang serves `POST /v1/messages` and `POST /v1/messages/count_tokens` on every server with no extra flag, for any model, and documents running Claude Code against it [HN §6, SG]. With this plan's schema that means:

| Setting | Value for an SGLang server |
|---|---|
| `baseUrl` | The server root, for example `http://host.docker.internal:30000`, reachable from the task container (the container already maps `host.docker.internal`, §6.2) |
| `authHeader` | `bearer`. SGLang accepts any non-empty token when started without `--api-key` [SG]; the token still comes from the `apiKeyEnv` variable, never the config file |
| `moduleName` | Any name; SGLang does not validate it [SG]. Use the served model's name so results are labelled correctly |
| `contextWindow` | **Required in practice**: Claude Code does not know the model and would assume 1M [HN §1]. Do not add a `[1m]` suffix (SGLang's example does) unless the model really has a 1M window |
| Extra environment | `CLAUDE_CODE_ATTRIBUTION_HEADER=0` (SGLang says its prefix cache needs it; the Claude Code docs disagree, NOT CHECKED, [HN §6]) and a raised `API_TIMEOUT_MS` [SG]. Neither is in the schema yet; add a `claude.gateway_env` option only if Open Question 1 says yes |
| Server side | `--tool-call-parser` (and `--reasoning-parser` for reasoning models) matching the model; without the tool parser Claude Code cannot execute tool calls [SG] |

**Unsupported.** Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway" [HN §6, `https://code.claude.com/docs/en/llm-gateway`]. What that costs us:

- **No fix path.** If a Claude Code release breaks against SGLang, nobody upstream owns it. Every version change needs the smoke test below before any benchmark run, and the pin (§5) becomes mandatory, not just good practice.
- **The harness is tuned for Claude.** For an unrecognised model ID Claude Code sends the request fields of current Claude models (adaptive thinking, effort, context management) [HN §6]. SGLang may ignore or reject them; `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` and `CLAUDE_CODE_DISABLE_THINKING=1` are the documented levers [HN §6]. The Task tools are absent on unrecognised IDs [HN §2].
- **Results mean something different.** A score measures "Claude Code's harness driving model X through a translation layer", not Claude Code as Anthropic ships it, and not model X in a harness built for it. Published results must say so.
- **Controls weaken.** Cost estimates, and with them `max_budget_usd`, are likely meaningless for an unknown model (R6); use `max_turns` and the timeout. Feature flags cannot be fetched with a bearer token (D14 makes that moot).
- **Prompt caching depends on SGLang**, not on Anthropic's cache [HN §4].

**NOT CHECKED, all of it:** that tool calls, streaming (including `ping` events, [HN §6]) and compaction work end to end through SGLang with the pinned Claude Code version. Verify with one `jsonlines` run, `evaluate: false`, against an SGLang server on project GPUs serving a small approved model. Not GLM, even though SGLang's own example uses it. This test (T14) is not in section 8 and runs only if Open Question 1 approves the path.

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Endpoint reach (largest).** Claude Code talks only to Anthropic-format endpoints, and Anthropic does not support non-Claude models behind a gateway [HN §6]. If the project's purpose is to profile models served on its own hardware, this backend may only ever run Claude models on Anthropic's hardware. Through a gateway there are known failure modes: 400s on fields the upstream rejects, a 1M context assumption, cache markers dropped without error [HN §1, §4, §6]. | Decide scope first (Open Question 1). Section 10 describes the self-hosted path and what it costs. The schema already carries `baseUrl`, `authHeader` and `contextWindow`. |
| R2 | **Version drift.** Defaults change between releases: `-p` began starting in Manual mode at v2.1.302, and `--bare` is announced as the future default for `-p` [HN §5]. Transcript format is explicitly unstable [HN §5]. | Version pin enforced by image label; pass every behaviour-defining flag explicitly; read only the documented output stream, not transcripts. |
| R3 | A run exits 0 without a successful result. | D7, T9. |
| R4 | Root hosts cannot run the backend. | D5, T6; Open Question 6. |
| R5 | Claude Code may write its own files into `/workspace` (for example a `.claude/` directory). **NOT CHECKED.** They would be copied into the evaluation workspace. | T7 lists the workspace. If anything appears, decide then; do not delete from `workspace/`, which is kept as generated. |
| R6 | Cost caps may not work for unrecognised model IDs [HN §3]. | Use `max_turns` and the timeout as the real limits in gateway runs. |

## 12. Open Questions

For supervisors. Each blocks or shapes the implementation.

**Status, 2026-11-25** (recorded by Timi Kalejaiye's instruction):

- **Q1:** answered for testing only: Qwen on ELM through LiteLLM (section 1). Which model for real runs stays open.
- **Q2: closed.** A single agent is approved for pipeline testing (Yinsicheng, supervisor). D3 stands.
- **Q3, Q5, Q6:** default chosen, confirm Friday. Working defaults (Timi's, not supervisor decisions): keep D4 and D14; pin the Claude Code version current at build time (2.1.325); keep D5 (tests run as uid 1000).
- **Q4:** keep the current rule; it is shared code, so it already matches the DeepSeek backend.
- **Q7:** open.

1. **Which models and endpoints is this backend for?** (a) Claude models on the Anthropic API only; or (b) also non-Claude models on our own GPUs through SGLang's `/v1/messages` (section 10), which works by SGLang's account but is unsupported by Anthropic, with the costs listed there. If (b), which model and which SGLang parsers, and may we spend GPU time on test T14? Which cheap, non-GLM model is approved for the tests in section 8?
2. **Is single-agent with delegation removed the right first baseline (D3)?** Or should Claude Code's default subagent delegation stay on? And is a lead-plus-subagents second stage wanted, given that agent teams cannot run headless?
3. **Full harness or `--bare` (D4), and feature flags on or off (D14)?** Full keeps Claude Code's default system prompt and tool set; bare is leaner, more reproducible and the documented recommendation for scripted calls, but is a different system prompt and tool set. Flags off makes runs reproducible but leaves out flag-gated behaviour that interactive users get.
4. **Should a run that hits the timeout, `max_turns` or the budget still be evaluated if it left code?** Today no backend evaluates such runs (`runner.py:83`). Changing it means editing shared code and affects all three backends.
5. **Version policy.** Which Claude Code version to pin, and how often to move it? Results from different versions are not comparable.
6. **Are root hosts in scope?** If EPCC or CI runners execute as root, D5 needs the uid-remapping alternative.
7. **Publication.** Results are published openly: may the result JSON carry `total_cost_usd` and token usage? And has anyone confirmed that Anthropic's terms allow benchmarking Claude Code and publishing the results? NOT CHECKED; this is a question for whoever owns the project's agreements.
