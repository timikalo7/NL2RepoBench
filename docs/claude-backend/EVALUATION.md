# Triage of the third evaluation (added 2026-11-16, before the targeted fix round)

The independent evaluation below is unchanged. This triage sorts its 11 required fixes (F1 to F11, in "Required fixes" at the end).

| Group | Findings | Why |
|---|---|---|
| (a) Must fix before any implementation | F1 (API key readable by the agent), F2 (`NL2REPO_BASE_URL` fallback), F3 (single-agent claim; nested `claude` from Bash), F6 (`init` event found by position) | Each would cause harm or a wrong result once code exists: a leaked key in published artifacts, a paid run sent to the wrong endpoint, an unnoticed second agent, a reader that misses its key event |
| (b) Wording or source fixes | F4 (`--init` and SIGTERM), F5 (flag-gated feature list), F7 (`api_retry` cross-reference), F8 (ANALYSIS §3.1 first sentence), F9 (net diff), F10 (unclassified files), F11 (Explore and Plan context; `ultracode`) | The design is unaffected; the text overstated, misquoted or omitted a source |
| (c) Can wait until the open questions are answered | None of the 11 as a whole. Two residual parts: whether flag-gated features should stay off (F5's underlying trade-off, Open Question 3), and whether the scrub's PID namespace works as a non-root user in a default container (F1, NOT CHECKED until test T13 runs) | Neither can be settled by editing documents |

Fix status: all of (a) and (b) addressed in the targeted round; see the commit that adds this triage.

---

# Independent evaluation of the Claude Code backend docs

Evaluated: `ANALYSIS.md`, `HARNESS_NOTES.md` and `PLAN.md` in this directory, at commit `fdba918` on branch `feat/claude-code-backend`, against base `main` = `bbd664b`. Date: 2026-11-15.

Method: each check below was re-run against the repo. Code was read at the cited lines (`cat -n`, `sed -n`, `git show <commit>:<path>`). Claude Code facts were checked against the public docs, downloaded as raw markdown on 2026-11-15; the newest changelog entry was still 2.1.325. Nothing was built or run, and no paid API was called.

To reproduce the docs download (pages are free and public):

```sh
mkdir -p /tmp/ccdocs && cd /tmp/ccdocs
for p in headless cli-reference sub-agents agent-teams model-config env-vars prompt-caching \
  permission-modes llm-gateway llm-gateway-protocol llm-gateway-connect changelog setup devcontainer \
  tools-reference context-window sessions hooks skills workflows how-claude-code-works authentication \
  agent-sdk/agent-loop agent-sdk/typescript agent-sdk/hosting; do
  curl -sSL -o "$(echo "$p" | tr / _).md" "https://code.claude.com/docs/en/$p.md"; done
```

## Results

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | Scope | PASS | `git status`: clean. `git diff --name-status main HEAD` shows only `A` for the three docs. Each branch commit (`28406ca`, `37dec95`, `fdba918`) touches only those three files (`git show --name-status <c>`). |
| 2 | Branch, not pushed | PASS | `git branch`: `* feat/claude-code-backend`. `git rev-parse @{u}`: "no upstream configured". `git ls-remote origin` lists only `main`, `deepseek-harness-backend` and `pull/1/head`. `git reflog`: clone, checkout, three commits, no push. |
| 3 | Secrets | PASS | Regex scan of the three docs for key shapes (`sk-…`, `sk-ant`, `ghp_`, `AKIA…`, `bearer <long>`, `token=`, `password`) hits only prose such as "secret env". Scanning for strings of 32+ characters hits only variable names. The docs name variables and never contain a value. |
| 4 | Citations | PASS | 26 claims opened and confirmed (table below), plus every other `file:line` in ANALYSIS §3–§6 while checking 6 and 7. None was wrong or unresolved. One PLAN cross-reference points at the wrong section (fix 7). |
| 5 | Git history | PASS | Commands and output below. `d08501b` and `4bf6013` are the only commits on any ref that touch `deepseek/` or its assets. Base `781a1da` and merge `bbd664b` are correct, and the merge tree equals `4bf6013`. One per-commit detail is not stated (fix 9). |
| 6 | End-to-end trace | PASS | All 27 steps of ANALYSIS §4 exist at the cited lines in `main.py`, `runner.py`, `deepseek/runner.py`, `deepseek/config.py`, `docker_self/batch_container.py`, `test_data_service.py:25-118` and `openhands/post_processor.py` (`:282`, `:429-482`, `:511-532`). The exception path (`status = "error"`) is at `runner.py:118-119` as stated. |
| 7 | Integration vs backend split | PASS | Nothing is misclassified. The evaluator `openhands/post_processor.py` is correctly shown as shared (imported at `runner.py:90`). `_image_info`, `resolve_model`, `write_profile` and `summarize_sessions` are DeepSeek-only. One sentence contradicts its own table, and some files are not classified (fixes 8, 10). |
| 8 | Harness notes sourced | PASS | Scan for bullets with neither a `[KEY …]` source nor NOT CHECKED: 0 found. All 25 source keys used are defined in the source table. 45 facts spot-checked against the downloaded pages were all present; 3 are slightly imprecise (fix 11). |
| 9 | Plan completeness | PASS | Directory layout §3. Config schema §4, mirroring the `deepseek` keys and validation. Docker image §5. Dispatch §3 (`main.py:12`, `:33-38`) and §6. Result mapping §7. Test plan §8: cheap model, never GLM, tasks `jsonlines` and `records`, at most 6 paid runs. Open Questions is §11, the last section. |
| 10 | Honesty | **FAIL** | Three PLAN statements are presented as settled with nothing behind them: (a) §1 says T7 verifies that no other path starts an agent, but T7 cannot see the most obvious other path (fix 3); (b) §6.2 says SIGTERM reaches Claude Code through `--init`, with no source and no NOT CHECKED mark (fix 4); (c) D14 calls four features "the documented ones" when the cited list has about sixteen (fix 5). Everything else that is unverified is marked NOT CHECKED with a way to verify it. |
| 11 | Documentation quality | PASS | A newcomer can follow all three docs. Sources, cross-references (`[HN §n]`, `G1`–`G15`), reproduce commands and the reasons behind decisions are all written down, and nothing is padding. Minor gaps are listed as fixes 8–11. |

Outside the checklist, the review also found one design problem (F1, fix 1) and one test-sequence problem (F2, fix 2). They are listed first because they would cause real harm when the plan is implemented.

## Check 4: citations opened

| Doc | Claim | What the repo says |
|---|---|---|
| ANALYSIS §3.1 | `main.py:12` backend registry | `BACKENDS = ("openhands", "deepseek")` |
| ANALYSIS §3.1 | `main.py:33-38` dispatch | `if backend == "deepseek": … else: … start_openhands` |
| ANALYSIS §3.1 | `runner.py:47-69` `model_tasks` | validates only `moduleName` and `proNameList` |
| ANALYSIS §4 step 22 | `runner.py:82-84` early return | `evaluation_status="skipped"`; returns if not enabled or `status != "completed"` |
| ANALYSIS §3.3 | `runner.py:120-127` overwrite and defaults | `result.update(task_uuid=…, saved_at=…)`, then three `setdefault` calls |
| ANALYSIS §4 step 16 | `batch_container.py:41-45` timeout | `generation_status = "timeout"`, `docker stop --time 10` |
| ANALYSIS G4 | `batch_container.py:62-63` | comment: "Do not stringify CalledProcessError: its argv may contain endpoint details" |
| ANALYSIS G10 | pin `639ed01539` at `deepseek/runner.py:15`, `scripts/build_deepseek.sh:5`; label at `docker/deepseek.Dockerfile:18` | all three as stated |
| ANALYSIS G10 | `deepseek/session_summary.py:11,15-16` | `rglob("session.v4.jsonl")`; rejects `version != 4` |
| ANALYSIS G2 | `deepseek/config.py:16` | `entry.get("protocol", "openai-completions")` |
| ANALYSIS G14 | `openhands/openhands_app.py:29-44` | key read from `apiKeyEnv`/`sk`, written into `config.toml`, `chmod 0o600` |
| ANALYSIS G8, G7, G9 | `openhands/post_processor.py:282`, `:527,530`, `:187-228` | `FROM --platform=linux/amd64 ghcr.io/…`; `python-test-{task_uuid}`; `remove_package_files` |
| ANALYSIS G11 | `test_data_service.py:38,104`; `more-itertools` absent | `os.listdir`; `pro_name=str(project_folder)`. The reproduce command prints `False`, and the directory is `more-Itertools`. 104 task directories plus `task_difficulty.csv`. |
| ANALYSIS G12 | `logging_config.py:165-166` | `if __name__ != "__main__": setup_logging(… "logs/application.log")` |
| ANALYSIS G15 | `only_test.py:17-18` | evaluates `workspaces/<name>/workspace` in place |
| ANALYSIS §3.3 | `readme.md:106` | result file note naming `generation_status`, `evaluation_status`, `team.status` |
| PLAN D5 | `docker/deepseek.Dockerfile:19` | `DSH_PERMISSION_MODE=danger-full-access` |
| PLAN D3, D11 | `deepseek/config.py:73-76` | disables `tool-web`, `web-search-deepseek`, `tool-workflow` |
| PLAN §5 | prefix match at `deepseek/runner.py:29`; full SHA at `scripts/build_deepseek.sh:9,14` | `revision.startswith(HARNESS_REVISION)`; `rev-parse` output passed as the build argument |
| PLAN T12 | `deepseek/runner.py:26`; `deepseek/config.py:20-22` | "DeepSeek image is unavailable…"; "Set baseUrl or NL2REPO_BASE_URL…". The image check runs after `resolve_model` (`:88-89`), so the dummy variables are needed as stated. |
| PLAN §3 | `readme.md:9`, `:80`, `:134-151`; `.gitignore:7` | backend sentence; `### OpenHands setup`; DeepSeek artifacts block; `config.deepseek.json` |
| PLAN 4.3 | `deepseek/config.py:31` | `contextWindow` default `131072` |
| PLAN §8 | Easy tasks, smallest specs, test counts | `task_difficulty.csv`: `jsonlines,Easy`, `records,Easy`. `wc -c`: 15379 and 16149 bytes, the two smallest. `test_case_count.txt`: 27 and 31. |
| PLAN D13 | `4bf6013` removed write-only artifacts | commit message: "Drop … the write-only run.json and team_summary.json artifacts" |
| PLAN D12 | setup page, "Install on network storage" | `setup.md`: "the native installer's default `~/.local/share/claude/versions/` directory both sit in the home directory", under that heading |
| HARNESS §7 | `deepseek/config.py:68,70`; `deepseek/prompt.txt:3,5,7`; `readme.md:58` | `maxMembers`, `maxActiveSubagents`; `writeScopes`, `send_message`, `wait_agent`; "The lead and teammates inherit the same model configuration" |

## Check 5: git history, re-run

```text
$ git log --oneline --all -- deepseek/
4bf6013 Remove excess code from the DeepSeek backend
d08501b Add DeepSeek Harness backend with Agent Teams
$ git log --oneline --all -- scripts/build_deepseek.sh config.deepseek.example.json docker/deepseek.Dockerfile
(same two commits)
$ git log --oneline --all -- runner.py main.py docker_self/batch_container.py openhands/openhands_app.py .gitignore readme.md
4bf6013 … / d08501b … / dbe72aa Initialize
$ git rev-parse d08501b^            -> 781a1da…
$ git log -1 --format='%p' bbd664b  -> 781a1da 4bf6013   (merge of PR 1)
$ git diff --stat 781a1da 4bf6013 | tail -1   -> 31 files changed, 782 insertions(+), 496 deletions(-)
$ git diff --stat 781a1da 4bf6013 -- . ':!deepseek' ':!*.pyc'   -> 11 files
$ git diff 4bf6013 bbd664b | wc -l  -> 0
$ git log --oneline 781a1da..bbd664b --all   -> d08501b, 4bf6013, bbd664b, then the three docs commits
```

Dates match ANALYSIS §1. The file table in ANALYSIS §2 matches `git diff --name-status 781a1da 4bf6013`: 6 new files in `deepseek/`, 14 untracked `.pyc` files, and 11 other files. No relevant commit is missing.

## Check 8: harness facts spot-checked

Confirmed as written (page, then section or line in the downloaded file): exit codes 0 and non-zero (`headless`, Basic usage); SIGTERM gives 143 and kills the Bash process tree (`headless`, Stop a run with SIGTERM); 10-minute background ceiling (`headless`); teammates not spawned in `-p` (exact quote, `agent-teams:60`); refusal to run `bypassPermissions` as root, skipped in a "recognized sandbox" (`permission-modes:710-716`); Manual mode from v2.1.302 (`permission-modes:99`); about 967K compaction and 200K for 4.6 models without 1M (`model-config:916-918`); `CLAUDE_CODE_MAX_CONTEXT_TOKENS` rules and v2.1.324 (`model-config:945-947`); a bare `200` meaning 200 tokens for the environment variable (`model-config`, last line of "Values and warnings"); five files and the 5,000-token rule after compaction (`context-window:34-40`); 20 concurrent subagents from v2.1.217, depth 3, no total cap (`sub-agents:1077,1102-1104`); `--forward-subagent-text` from v2.1.211; `--disallowedTools` bare name removes the tool (`cli-reference:87`); result subtypes and fields (`agent-sdk/agent-loop`, Handle the result); `--bare` quote (`headless:73`); `ANTHROPIC_API_KEY` "always used when present" in `-p`, and `ANTHROPIC_AUTH_TOKEN` ranked above it (`authentication:251-252`); Anthropic Messages, Bedrock and Vertex formats only, `/v1/messages?beta=true` (`llm-gateway-protocol`, API formats); "doesn't support routing Claude Code to non-Claude models through any gateway" (`llm-gateway:17`); attribution block stable from v2.1.181; buffering gateway stalls; default retries 10, `API_TIMEOUT_MS` 10 min, Bash 2 and 10 min, output tokens 32,000 and 128,000 for unknown IDs, `DISABLE_NONESSENTIAL_TRAFFIC=0` still disables (`env-vars` rows); feature-flag fetch skipped with a gateway token and no API key (`env-vars`, First session after an install or upgrade); npm pin with `DISABLE_AUTOUPDATER` (`devcontainer:135`); Node 22, `EBADENGINE`, native binary (`setup:457-463`); 1 GiB, 5 GiB, 1 CPU (`agent-sdk/hosting:202`); one-hour TTL variables from v2.1.242 (`prompt-caching:290`); transcript path and "internal to Claude Code" (`sessions:268-270`); 2.1.325 dated November 13, 2026 (`changelog:13`).

## Overall verdict: FAIL

The analysis is accurate. Every citation checked resolves to what the docs say, the git history and trace are correct, and scope, branch and secrets are clean. The verdict is FAIL for two reasons. Check 10 fails on three unsupported statements in PLAN.md. And the plan has two problems that would cause harm when implemented: F1 could put the API key into artifacts that are published openly, and F2 could send a paid test run to the wrong endpoint. All fixes are edits to the three docs, and no new research is needed beyond the doc pages cited below.

## Required fixes

1. **F1: the key is readable by the agent.** PLAN D8 puts the key into the container as `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`). By default every Bash command Claude runs inherits it. A routine `env`, `printenv` or `.env` file then writes the key into `stdout.jsonl` (as a tool result), into the transcripts under `claude-home/`, or into `workspace/`. All of these are run artifacts, and the workspace is also copied for evaluation. T4 cannot catch this, because no model call succeeds in T4. Claude Code documents a fix: in the `env-vars` page, the `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` row ("Set to `1` to strip credentials from the environments of the subprocesses Claude Code starts, such as Bash commands"), and the section "What the subprocess environment scrub removes" (`ANTHROPIC_API_KEY`: "Removes it"; "The Claude Code process keeps the credentials for its own API calls"). Make these changes:
   - Add `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` to the image environment in PLAN §5 and to D8. Add the fact, with its source, to HARNESS_NOTES §5.
   - Mark NOT CHECKED that the scrub works in a default Docker container as a non-root user. On Linux it also runs Bash in an isolated PID namespace (same section), which may need privileges such a container lacks.
   - Add two pass conditions to T7: Bash tool calls still succeed, and `grep -rlF -- "$<apiKeyEnv variable>" workspaces/<run_id> result/` prints nothing. This prints file names only, never the key.
   - Add a line to ANALYSIS G3: the DeepSeek key is likewise in the agent's environment (`deepseek/runner.py:45,54`). "Never enters the result JSON or docker argv" is true but does not cover output the agent writes.
2. **F2: the `baseUrl` fallback picks up the DeepSeek endpoint in the test sequence.** PLAN 4.2 falls back to `NL2REPO_BASE_URL`, and the PLAN example config sets `"baseUrl": ""`. The readme tells DeepSeek users to `export NL2REPO_BASE_URL='https://your-endpoint.example/v1'` (`readme.md:32`), and PLAN T12 itself sets it to `http://127.0.0.1:9`. A T7 run in the same shell would then go to that endpoint instead of the Anthropic API that §8 assumes. Either drop the fallback for this backend, so that an empty `baseUrl` means the Anthropic API, or have T7–T11 unset the variable explicitly and log which source supplied the URL. Add the case to T2.
3. **PLAN §1 and T7: the single-agent claim is over-verified (check 10a).** The `delegations` counter (§7) sees only messages with a `parent_tool_use_id` and calls to `Agent`, `Workflow` or `Skill`. It cannot see a second Claude Code started from Bash (`claude -p …`): the binary is on `PATH` at `/usr/local/bin`, and without fix 1 the key is in the environment. Either reword §1 to "T7 checks the documented delegation tools only; other paths stay NOT CHECKED", or also count Bash `tool_use` inputs that invoke `claude`. Fix 1 makes a nested run fail authentication, so state that as well once it is verified.
4. **PLAN §6.2, Timeout paragraph: unsourced mechanism (check 10b).** "With `--init`, SIGTERM reaches Claude Code" has no source. `docker run --help` here says only "Run an init inside the container". Cite Docker's documentation for signal forwarding by `--init`, or mark it NOT CHECKED and point to T10, which already records 143 against 137.
5. **PLAN D14: misquoted list (check 10c).** "The documented ones (Remote Control, advisor tool, MCP tasks, Code Mode)" misreports the source. The `env-vars` section "Features that need feature-flag fetching" lists about sixteen items, including `claude import`, synced skills and plugins, Claude-drafted feedback, and excluding MCP tools with invalid schemas. HARNESS_NOTES §5 correctly says "include". Reword to "the documented list includes nothing this plan uses" after checking each item, and cite the section.
6. **PLAN §6.2, stdout reader assumption.** HARNESS_NOTES §5 says "The stream starts with a `system`/`init` event". The `headless` page (Read session metadata) says it is "the first event in the stream unless startup events precede it". Correct HARNESS_NOTES §5, and say in PLAN §7 that `summarize_run` must search for the `init` event rather than read line 1.
7. **PLAN T4: wrong cross-reference.** "The documented `api_retry` event fields carry no URL [HN §3]": HARNESS_NOTES §3 does not list those fields. The fact is correct. Cite `[HL § Handle API retries]` directly (fields: `type`, `subtype`, `attempt`, `max_retries`, `retry_delay_ms`, `error_status`, `no_response`, `error`, `uuid`, `session_id`), or add the list to HARNESS_NOTES §3.
8. **ANALYSIS §3.1, first sentence.** "A new backend calls it and should not need to change it" contradicts the table's own rows for `main.py:12` and `main.py:33-38`, which must be edited, as must `.gitignore` and `readme.md` (§2). Reword to: "calls it; the only shared edits are the registry and dispatch in `main.py`, one `.gitignore` line and the readme."
9. **ANALYSIS §2: say the table is a net diff.** `d08501b` also added `test_data_list.clear()` to `test_data_service.py`, and `4bf6013` removed it (`git diff --stat d08501b 4bf6013` shows `test_data_service.py | 1 -`). `docker_self/docker_config.py` was deleted in `4bf6013`, not in `d08501b`. Without this line, `git show --stat d08501b` appears to contradict the table.
10. **ANALYSIS §3: classify the remaining key files.** The brief names `template/` and `config.json`. `template/config.template.toml` is OpenHands-only (read at `openhands/openhands_app.py:37`). `config.json` is the default `--config` (`main.py:17`) and an OpenHands config, since it has no `backend` key. `test_data_service.py`, `logging_config.py` and `docker_self/docker_service.py` are shared and untouched by a new backend.
11. **HARNESS_NOTES precision.** (a) §2: the subagent's initial context includes `CLAUDE.md` and git status except for Explore and Plan, which start without both (`sub-agents`, line 33 of the downloaded page). (b) §3: `--effort` also accepts `ultracode` (`cli-reference`, `--effort` row). Neither changes the plan. Fix 6 covers the third imprecision.
