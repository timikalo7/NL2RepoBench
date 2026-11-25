# Claude Code backend: test results

Every result here is "Claude Code driving Qwen through LiteLLM", or a free test that calls no model. Session of 2026-11-25. Commits are on `feat/claude-code-backend` in `timikalo7/NL2RepoBench`.

## Part A summary (status: stopped, ELM key not attached)

- The backend is implemented to PLAN.md and pinned at Claude Code **2.1.325**.
- Free tests T1, T2, T3, T4, T5, T6 and T12 **all pass**. T4 passes after the D8 update (session 2, below): it failed in session 1.
- The D8 decision is implemented. The scrub stays on; the container runs as uid 1000 with no added capabilities, under `docker/claude-seccomp.json` plus `--security-opt systempaths=unconfined`. A side effect: Claude Code then forces the permission mode to `default`, so the backend now also declares `--allowedTools Bash Read Edit Write` (approved by Timi, session 3). That this works with a real model is NOT CHECKED.
- The approved grader sentence is in `claude/prompt.txt` and PLAN §6.3.
- **Still blocked:** ELM returns 401 to `GET /models` and `GET /costs`, because this session's environment ("Default") lists no network secrets. So the LiteLLM check, the gateway smoke runs, and T13, T9, T10, T7 and T11 have not run. T8 is not run (optional). Part B has not started.
- **ELM spend: none.**

## Session 3 (2026-11-25, after 13:28)

| Check | Result |
|---|---|
| Branch | `feat/claude-code-backend` at `abbf953` on `mine`, working tree clean |
| uid 1000 setup, LiteLLM key file, clone | Still present (`ubuntu` in group `docker`; `/home/ubuntu/.litellm_master_key`; `/home/ubuntu/NL2RepoBench`) |
| `dockerd` | Not running at session start; not started, as nothing in this session needed Docker |
| ELM | `GET https://elm.edina.ac.uk/api/v1/models` returns **401**. The environment ("Default", `env_01BF7d6TsgNYEEDNGR56eKuY`) still lists `network_secrets: []` |
| `--allowedTools` | Timi's approval recorded in PLAN's D8 update row and above |

Per the brief, the 401 is a stop condition: no LiteLLM check, smoke run or paid test ran. ELM spend: none.

## Phase 0

| Check | Result | Evidence |
|---|---|---|
| Existing implementation past `1611a12` | None on any branch of `timikalo7/NL2RepoBench` (`main` at `bbd664b`, `feat/claude-code-backend` at `1611a12`) | `git fetch mine '+refs/heads/*:refs/remotes/mine/*'`, then `git ls-tree -r --name-only <branch>` for each branch: no `claude/`, `docker/claude.Dockerfile` or `scripts/build_claude.sh` |
| uid 1000 test user | `ubuntu` (uid 1000) exists; added to group `docker` (gid 996); own clone at `/home/ubuntu/NL2RepoBench` | `usermod -aG docker ubuntu`; `sudo -u ubuntu docker ps` works. The clone needed `safe.directory` entries in ubuntu's own `~/.gitconfig`, because the source repo is root-owned |
| LiteLLM key for uid 1000 | A throwaway LiteLLM master key, generated locally, in `/home/ubuntu/.litellm_master_key` (mode 0600, outside both repos). Tests export it as `LITELLM_MASTER_KEY`. It grants access to the local LiteLLM only; the ELM key is never in the VM | `ls -l /home/ubuntu/.litellm_master_key` |
| Docker | `dockerd` started once with plain `dockerd`; server 29.9.2, overlayfs, cgroup v1. `hello-world` ran | `docker info`; `docker run --rm hello-world` |
| GHCR | Works: `ghcr.io/multimodal-art-projection/nl2repobench/jsonlines:1.0` pulled in 17.7 s | `docker pull …/jsonlines:1.0` |
| Container internet | **No usable internet.** A container reaches the network, but the session proxy intercepts TLS with a CA containers don't trust: `CERTIFICATE_VERIFY_FAILED` for `https://pypi.org/simple/`. So the agent cannot `pip install` during a run | `docker run --rm python:3.12-slim python -c "urllib.request.urlopen('https://pypi.org/simple/')"` |
| uv | Session uv is 0.11.32, older than Harbor's required 0.13.5. uv 0.13.10 installed in a scratch venv (session-only) | `uv --version`; `pip install 'uv>=0.13.5'` |
| ELM reachable | Reachable, but **unauthenticated**: `GET https://elm.edina.ac.uk/api/v1/models` with no key returns `401 Missing or invalid Authorization header`. This session's environment ("Default") lists **no network secrets**, and neither do the user's other two environments | `curl -w '%{http_code}' …/models`; environment settings |

## Build wrapper used for T3 (session-only, not committed)

`scripts/build_claude.sh` builds from an empty context (PLAN §5). Containers here cannot use the session proxy or trust its CA (`/root/.ccr/README.md`, "docker build / docker run"), so T3 used a local copy of the script as a wrapper, outside the repo. Compared with `scripts/build_claude.sh`, the wrapper:

1. copies the session CA bundle into the build context and writes a derived Dockerfile that installs it right after `FROM python:3.12-bookworm` (`update-ca-certificates`, `ENV NODE_EXTRA_CA_CERTS`);
2. rewrites the apt sources from `http://deb.debian.org` to `https://`, because the proxy refuses plain-HTTP requests with `405` (first build failed on `apt-get update`; README, "405 Method Not Allowed");
3. builds with `--network host` and passes only `HTTPS_PROXY` as a build arg (an `ARG`, so it is not baked in).

The resulting local image therefore also trusts the session CA and carries `NODE_EXTRA_CA_CERTS`. Neither is in the repo's Dockerfile or committed anywhere.

## Free tests

All as uid 1000 (`ubuntu`) in `/home/ubuntu/NL2RepoBench`, except T3 (image build, as root) and T6 (as root on purpose).

| # | Verdict | What ran | Result |
|---|---|---|---|
| T1 | PASS | `python3 main.py --backend nosuch`; `python3 main.py --help` | `invalid choice: 'nosuch' (choose from 'openhands', 'deepseek', 'claude')` |
| T2 | PASS | `main.py --config` with 7 bad configs: unknown `claude` key; `protocol: openai-completions`; `sk` present; key variable unset; `reasoningEfforts` present; `baseUrl` empty with `NL2REPO_BASE_URL=http://127.0.0.1:9` exported; `gateway_env` setting `ANTHROPIC_API_KEY` | Each exits 1 with a `ValueError` naming the field (for example `baseUrl must be an http(s) URL with a host`); `workspaces/` entries before 0, after 0 |
| T3 | PASS (wrapper) | Wrapper build (above), then `docker run --rm --entrypoint claude nl2repobench-claude:2.1.325 --version`, and the same with `--user 1000:1000` | Both print `2.1.325 (Claude Code)`; label `org.nl2repobench.harness-revision=2.1.325`; image env has `CLAUDE_CONFIG_DIR`, `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` |
| T4 (session 1) | **FAIL** (superseded, see session 2) | `main.py` with `baseUrl: http://host.docker.internal:9` (closed), `T4_DUMMY_KEY=dummy-t4-key-0000000000`, `task_timeout_seconds: 120` | The container exits 1 within 1 s; `stdout.jsonl` is empty. `stderr.log`: "Claude Code could not start: bubblewrap is required for subprocess env scrubbing and isolation". Result `generation_status: failed`, `status: failed`, `claude.status: incomplete`. The other T4 checks pass: the container was removed, and `grep -rlF` finds neither the dummy key, the URL, `Bearer` nor `Authorization` in `result/` or the run directory |
| T5 | PASS | `python3 -m unittest tests.test_claude_backend -v` | 10 tests OK: success → `completed`; `error_max_turns` → `incomplete`; truncated file → `incomplete`, no exception; `init` after a hook event still found; delegation counted; missing file handled; argument order; `gateway_env` validation; `baseUrl` without fallback |
| T6 | PASS | As root: `python3 main.py --config <valid config>` | `RuntimeError: The claude backend refuses to run as root … (PLAN D5)`, exit 1; no workspace, no container |
| T12 | PASS | `NL2REPO_API_KEY=dummy… NL2REPO_BASE_URL=http://127.0.0.1:9 python3 main.py --config config.deepseek.example.json` | `RuntimeError: DeepSeek image is unavailable…` (`deepseek/runner.py:26`), exit 1 |

## Design decision needed: D8 scrub vs container security (resolved in session 2)

**Finding.** Claude Code 2.1.325 refuses to start with `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` unless `bubblewrap` is installed. Commit `15dc93d` adds it to the image. Even with bubblewrap installed, `bwrap` cannot create its namespace as uid 1000 under Docker's default security options. Diagnostic commands, nothing committed (`bwrap --ro-bind / / --unshare-pid --proc /proc true` inside `nl2repobench-claude:2.1.325` as uid 1000):

| `docker run` options | bwrap |
|---|---|
| default | FAIL: "No permissions to create new namespace" |
| `--security-opt seccomp=unconfined` (also with `apparmor=unconfined`) | FAIL |
| `--cap-add SYS_ADMIN` + seccomp and apparmor unconfined | FAIL |
| `--security-opt systempaths=unconfined --security-opt seccomp=unconfined` | OK |
| `--privileged` | OK |

With `systempaths=unconfined` and `seccomp=unconfined`, Claude Code starts with the scrub on: the stream has an `init` event, 10 `api_retry` events and a final `result`. The host itself allows unprivileged user namespaces (`unshare --user --map-root-user true` works), so the block comes from Docker's defaults, mainly the masked `/proc` paths. NOT CHECKED: whether a stock Docker host at EPCC behaves the same.

**Side finding that confirms D7.** On a refused connection, the final `result` event has `subtype: "success"` with `is_error: true` and `terminal_reason: "api_error"`. D7 checks both fields, so `status` is `failed` there, as intended.

**Options for Timi** (this changes a PLAN decision, so I have stopped):

1. **Add `--security-opt systempaths=unconfined --security-opt seccomp=unconfined` to the `docker create` arguments (§6.2) and keep D8.** The scrub and its PID isolation then work. Cost: the agent's container loses Docker's seccomp filter and `/proc`/`/sys` masking, which weakens isolation from the host. It still runs as uid 1000 without `--privileged`.
2. **Set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0` and drop the scrub from D8.** Cost: Bash commands inherit the LiteLLM key again. Two things then rely on other controls: keeping the key out of published files (the post-run `grep -rlF`, plus a throwaway key per session) and the `sh -c 'claude …'` case in T13, which would then have a credential and reach the model.
3. **Use `--privileged`.** It works, but it is the widest change. Not recommended.

My recommendation is option 1. It keeps D8's protection, and the containers already run as an unprivileged user with no usable internet. Harbor's `claude-code` agent would need the same choice in Part B.

## Session 2 (2026-11-25, from 12:25 UTC)

### Phase 0, again

| Check | Result |
|---|---|
| Existing work | The fork's `feat/claude-code-backend` was at `3f0c140` (session 1's work). Not a fresh VM after all: user `ubuntu`'s clone, its `docker` group membership, the local LiteLLM key file, the scratch build wrapper and the Docker images all survived |
| Docker | `dockerd` was not running, and a stale `/var/run/docker.pid` (PID 184, no longer running) blocked a start. Removed the stale pid file, as the daemon's own message says, then started plain `dockerd` once |
| AppArmor | None on this host (`/sys/kernel/security/apparmor` absent) |
| ELM | **401** to `GET /models` and `GET /costs`, at session start and again at the end. The environment still lists no network secrets |
| uv | Session uv is still 0.11.32; the scratch-venv uv 0.13.10 from session 1 survived |

### T3, re-run

The same session-only wrapper (see "Build wrapper used for T3" above) rebuilt `nl2repobench-claude:2.1.325` from commit `3f0c140`'s Dockerfile, which now includes bubblewrap. Result: `claude --version` prints `2.1.325 (Claude Code)` as root and as uid 1000, the label is `2.1.325`, and bubblewrap is 0.8.0. **PASS.**

### D8 implementation

- **bwrap flags Claude Code 2.1.325 passes.** Found by grepping the installed CLI (`/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`): `--new-session --die-with-parent --unshare-user --unshare-pid --unshare-net --unshare-ipc --unshare-uts --unshare-cgroup-try --hostname localhost`, plus `--dev /dev` and `--proc /proc`.
- **Base profile.** Docker 29.9.2 vendors `github.com/moby/profiles/seccomp v0.2.4` (`https://raw.githubusercontent.com/moby/moby/docker-v29.9.2/go.mod`). `docker/claude-seccomp.json` is that version's `default.json` plus one rule, with no `includes.caps`, allowing `clone`, `unshare`, `mount`, `umount2`, `pivot_root` and `sethostname` (commit `4029b46`).
- **Checks** (`docker run --user 1000:1000 … bwrap …` inside the image):

| Options | Session 1 diagnostic (`--unshare-pid --proc /proc`) | Claude Code's flags |
|---|---|---|
| profile + `systempaths=unconfined` | OK | OK (`hostname` prints `localhost`) |
| profile only | FAIL: "Can't mount proc on /newroot/proc" | FAIL |
| `systempaths=unconfined` only | FAIL: "No permissions to create new namespace" | FAIL |
| default | FAIL | FAIL |
| profile without `sethostname` + `systempaths` | not run | FAIL: "Can't set hostname to localhost" |

- **Privileges.** With the chosen options, `/proc/self/status` shows `CapEff: 0000000000000000` for uid 1000. No capabilities were added, and `--privileged` is not used.
- **Arguments.** `_docker_arguments` now adds the two `--security-opt` values. A new unit check (`DockerArgumentsTest`) confirms the options are there and that `--privileged`, `--cap-add` and `seccomp=unconfined` are not, that secrets are passed by name only, and the argument order.

### New finding: the scrub forces the permission mode to default

After the D8 options, T4's `stderr.log` showed: "⚠ Permission mode forced to default — CLAUDE_CODE_SUBPROCESS_ENV_SCRUB is set (allowed_non_write_users hardening). Declare allowedTools explicitly, or set CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0 to opt out." The `init` event reports `permissionMode: "default"`, with or without `--allowedTools`. In `-p` mode, tools not covered by an allow rule would be denied, so the backend now passes `--allowedTools Bash Read Edit Write` (commit `6707f21`; PLAN D8 update). **NOT CHECKED** until a model run: that these tools then run unprompted. T13 and T7 check it through `permission_denials`. **Approved by Timi on 2026-11-25 (session 3 brief)** and recorded in PLAN's D8 update row.

### T4 and T5, re-run

| # | Verdict | Result |
|---|---|---|
| T4 | **PASS** | As uid 1000, with `baseUrl: http://host.docker.internal:9`, a dummy key and a 120 s timeout. The `init` event is present (Claude Code started, did not block on stdin, `claude_code_version: 2.1.325`); 9 `api_retry` events; the run hit the 120 s timeout (`generation_status: timeout`, `exit_code: 143`, `status: failed`); no container left. `grep -rlF` finds neither the dummy key, the URL, `Bearer` nor `Authorization` in `result/` or the run directory. The `init` tool list has no `Agent`, `Workflow`, `Skill`, `WebSearch` or `WebFetch`. Re-run after the `--allowedTools` change with the same outcome |
| T5 | **PASS** | `python3 -m unittest tests.test_claude_backend`: 14 tests OK (now including the `docker create` checks and `--allowedTools`) |

Exit code on timeout: **143**, so Claude Code exited within Docker's 10 s grace period after SIGTERM (PLAN §6.2's NOT CHECKED item, now observed once).

## Blockers

1. ~~D8 scrub~~: resolved in session 2.
2. **ELM key not attached (still, session 2).** This session's environment ("Default") has no network secrets, so `elm.edina.ac.uk` returns 401 to every request. That blocks the LiteLLM check, `GET /costs`, the smoke runs and all paid tests. To fix: in the cloud environment menu, choose Default, then Edit, then Network secrets, and add a secret for host `elm.edina.ac.uk`, header `Authorization`, prefix `Bearer`. A new session picks it up reliably.
3. ~~Grader sentence~~: approved and applied in session 2 (commit `3a161c3`).

### Draft sentence for PLAN §6.3, for approval

It would replace "Produce a runnable repository, including its package metadata and dependencies.":

> Do not rely on package or dependency files: grading deletes every file named setup.py, pyproject.toml, setup.cfg, requirements.txt, requirements-dev.txt, requirements-test.txt, tox.ini, pytest.ini, poetry.lock, Pipfile, Pipfile.lock, environment.yml, conda-env.yaml, manifest.in or MANIFEST.in anywhere in the repository, then runs the tests in a fresh environment with /workspace on PYTHONPATH, so nothing declared in those files or installed while you work will be available.

Approved by Timi and applied to `claude/prompt.txt` and PLAN §6.3 in session 2. `deepseek/` is untouched.

## Known upstream issue: the grader deletes package files

`evaluate_result` copies the workspace (`runner.py:92`). `post_process_task` then deletes the 15 package-file names anywhere in the copy (`openhands/post_processor.py:187-228`, called at `:518`), deletes the task's test files (`:521`), and builds `FROM --platform=linux/amd64 ghcr.io/multimodal-art-projection/nl2repobench/<task>:1.0` (`:282`). Dependencies the agent declared or installed never reach grading. The other interns saw this with python-slugify (lost `Unidecode`) and structlog (lost `typing-extensions`). The deletion is not fixed in this repo by design; the prompt sentence above is the mitigation.

## ELM costs

| When | `GET /costs` | asOf | Spend |
|---|---|---|---|
| 2026-11-25, session 1 start | 401 (no key attached) | not available | none sent |
| 2026-11-25, session 2 start and end | 401 (no key attached) | not available | none sent |
