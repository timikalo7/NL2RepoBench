# How the DeepSeek backend was added

Purpose: the DeepSeek backend is the only worked example of adding a generation backend to this repo. This document records what that change touched, which parts are reusable template and which are DeepSeek-specific, so that a Claude Code backend (see `PLAN.md`) can follow the same path.

All `file:line` references are to commit `bbd664b` (tip of `main`, checked 2026-11-14). Nothing in this document was verified by running the benchmark; see [Not checked](#7-not-checked).

## 1. Commits

| Commit | Date | What it is |
|---|---|---|
| `781a1da` | 2026-05-13 | Base. Last commit before the backend work. OpenHands is the only backend. |
| `d08501b` | 2026-10-07 | "Add DeepSeek Harness backend with Agent Teams". Adds `deepseek/`, the shared `runner.py` and `docker_self/batch_container.py`, rewrites OpenHands onto them. |
| `4bf6013` | 2026-10-07 | "Remove excess code from the DeepSeek backend". Cleanup of `d08501b`; moves `startPro` validation into `runner.model_tasks`. |
| `bbd664b` | 2026-10-08 | Merge commit of pull request 1 (branch `deepseek-harness-backend`) into `main`. Tree is identical to `4bf6013`. |

No other commit touches these paths. The only remote branch besides `main` is `origin/deepseek-harness-backend`, which points at `4bf6013`.

Reproduce:

```sh
git log --oneline --all -- deepseek/
git log --oneline --all -- scripts/build_deepseek.sh config.deepseek.example.json
git rev-parse d08501b^                       # 781a1da..., the base
git diff --stat 781a1da 4bf6013              # 31 files, +782 -496
git diff --stat 781a1da 4bf6013 -- . ':!deepseek' ':!*.pyc'   # 11 files outside deepseek/
git diff 4bf6013 bbd664b | wc -l             # 0: the merge adds nothing
git diff d08501b 4bf6013                     # what the cleanup changed
```

## 2. Files touched (`781a1da` → `4bf6013`)

| File | Change | Layer |
|---|---|---|
| `main.py` | Rewritten: argparse, `--config`, `--backend`, `--skip-evaluation`, dispatch | Integration |
| `runner.py` | New: batch scheduling, validation, result writing, evaluation hand-off | Integration |
| `docker_self/batch_container.py` | New: bounded container run with captured diagnostics | Integration |
| `openhands/openhands_app.py` | Rewritten on the shared runner (521 lines changed, now 79 lines) | Second example of a backend |
| `docker/deepseek.Dockerfile` | New | Backend asset in a shared directory |
| `scripts/build_deepseek.sh` | New | Backend asset in a shared directory |
| `config.deepseek.example.json` | New | Backend asset at repo root |
| `.gitignore` | New; line 7 ignores `config.deepseek.json` | Integration (one line per backend) |
| `readme.md` | DeepSeek setup, endpoint settings, artifacts | Integration (docs) |
| `requirements.txt` | Reduced to `python_on_whales` | Housekeeping |
| `docker_self/docker_config.py` | Deleted (unused after the rewrite) | Housekeeping |
| 14 `*.pyc` files | Untracked | Housekeeping |
| `deepseek/__init__.py`, `config.py`, `runner.py`, `session_summary.py`, `prompt.txt`, `profile/package.json` | New | Backend-specific |

`openhands/post_processor.py` (the evaluator) and `docker_self/docker_service.py` were not changed.

## 3. Integration layer versus backend layer

The first backend addition also paid for a one-off refactor: `d08501b` extracted scheduling, result writing and evaluation out of the old 450-line `openhands_app.py` into shared modules. A third backend does not repeat that. It only plugs into what now exists.

### 3.1 Integration layer (the template)

Shared code. A new backend calls it and should not need to change it.

| Concern | Where | What a backend does with it |
|---|---|---|
| Backend registry | `main.py:12` (`BACKENDS` tuple) | Add its name |
| CLI flag | `main.py:18` (`choices=BACKENDS`) | Nothing; follows the tuple |
| Default backend | `main.py:27` (`config.get("backend", "openhands")`) | Nothing |
| Dispatch | `main.py:33-38` (`if backend == "deepseek": … else: …`) | Add a branch with a lazy import |
| Process exit code | `main.py:39-41` (1 if any `status != "completed"`) | Return a list of result dicts that carry `status` |
| `startPro` validation | `runner.py:47-69` (`model_tasks`) | Call it; returns `(entry, moduleName, TestData)` per task |
| `evaluate` flag | `runner.py:40-44` (`evaluation_enabled`); `main.py:25-26` | Call it once, pass the bool into each job |
| Run identifier | `runner.py:28-31` (`new_run_id`) | Call it; the id names the run directory, container and result file |
| Job contract | `runner.py:19-25` (`Job` dataclass) | Build one `Job(task_uuid, backend, module_name, pro_name, run)` per task |
| Scheduling and result file | `runner.py:109-132` (`run_batch`) | Call it last; it writes `result/<task_uuid>.json` |
| Atomic JSON write | `runner.py:72-77` (`write_json`) | Optional helper |
| Container lifecycle and timeout | `docker_self/batch_container.py:13-73` (`run_batch_container`) | Pass `docker create` arguments, a container name, the run directory and a timeout |
| Evaluation hand-off | `runner.py:80-106` (`evaluate_result`) | Call it as the last line of the per-task function |
| Evaluator | `openhands/post_processor.py:485-555` (`post_process_task`) | Nothing. Shared by every backend despite living in `openhands/` (imported at `runner.py:90`). It drives Docker through `docker_self/docker_service.py` (`openhands/post_processor.py:11`), not through `batch_container.py` |
| Config validation helper | `runner.py:34-37` (`positive_int`) | Use for every integer option |
| Docker CLI helper | `docker_self/batch_container.py:9-10` (`docker_command`) | Use for one-off Docker calls such as image inspection |

### 3.2 Backend layer (what gets replaced)

Everything in `deepseek/`, plus three assets that live outside it by naming convention:

| File | Role | Claude Code counterpart needed? |
|---|---|---|
| `deepseek/runner.py:72-95` `start_deepseek` | Entry point: validates options, builds jobs | Yes |
| `deepseek/runner.py:34-69` `_run_task` | Per-task: directories, prompt, container arguments, result assembly | Yes |
| `deepseek/runner.py:20-31` `_image_info` | Fails early if the image is missing or built from the wrong revision | Yes |
| `deepseek/config.py:14-52` `resolve_model` | Reads the model fields of a `startPro` entry; returns public settings and a separate secret env | Yes (own version; see gotcha G1) |
| `deepseek/config.py:55-99` `write_profile` | Writes the harness profile (`cordis.patch.yml`) | No profile format in Claude Code; replaced by CLI flags and environment variables |
| `deepseek/session_summary.py:7-85` `summarize_sessions` | Reads session logs, reports whether the team workflow happened (`team.status`) | Yes, different content |
| `deepseek/prompt.txt` | Task prompt, including the agent-teams instructions | Yes, different content |
| `deepseek/profile/package.json` | Harness bundle selection | No |
| `docker/deepseek.Dockerfile` | Image | Yes |
| `scripts/build_deepseek.sh` | Image build | Yes |
| `config.deepseek.example.json` | Example config | Yes |

### 3.3 The contract between the layers

Derived from the code paths in section 4. A backend's per-task function must return a dict with:

- `status`: `"completed"` or `"failed"`. Read by `evaluate_result` (`runner.py:83`), `run_batch` logging (`runner.py:130-131`) and `main.py:39`.
- `workspace_path`: directory holding the generated repo. Read by `runner.py:86`.
- `task_uuid`: read by `runner.py:94`.
- `generation_status`: not read by shared code, but every backend sets it via `run_batch_container` and the README documents it (`readme.md:106`).

`run_batch` then overwrites `task_uuid`, `backend`, `module_name`, `pro_name` and `saved_at` (`runner.py:120-124`) and defaults `evaluation_status`, `test_score`, `score` (`runner.py:125-127`). No shared code reads `config_path`, `image`, `team`, `session_logs_path` or the log paths; they are informational.

## 4. End-to-end trace of one DeepSeek task

Command: `python main.py --config config.deepseek.json`.

| # | Step | Function | File:line |
|---|---|---|---|
| 1 | Parse CLI, load JSON config | `main` | `main.py:16-24` |
| 2 | `--skip-evaluation` forces `evaluate: false` | `main` | `main.py:25-26` |
| 3 | Resolve backend (flag, then config, then `openhands`) | `main` | `main.py:27-29` |
| 4 | `chdir` to the repo root, load all task metadata from `./test_files` | `main`, `read_all_test_data` | `main.py:31-32`, `test_data_service.py:25-118` |
| 5 | Dispatch | `main` | `main.py:33-35` |
| 6 | Read `max_pool_size`, `evaluate`, the `deepseek` object; reject unknown keys; enforce `teammates >= 2` | `start_deepseek` | `deepseek/runner.py:74-87` |
| 7 | Validate every `startPro` entry and task name | `model_tasks` | `runner.py:47-69` (called at `deepseek/runner.py:88`) |
| 8 | Resolve model settings and the API key for each entry | `resolve_model` | `deepseek/config.py:14-52` |
| 9 | Check the image exists and carries the pinned revision label | `_image_info` | `deepseek/runner.py:20-31` (called at line 89) |
| 10 | Build one `Job` per task with a fresh run id | `start_deepseek`, `new_run_id` | `deepseek/runner.py:90-94`, `runner.py:28-31` |
| 11 | Schedule jobs on a thread pool | `run_batch` | `runner.py:112-113` |
| 12 | Create `workspaces/<run_id>/workspace`; copy the task's `start.md` in | `_run_task` | `deepseek/runner.py:36-40` |
| 13 | Create `dsh-home` by writing the harness profile into it, then `dsh-home/user`; render and save the prompt | `_run_task`, `write_profile` | `deepseek/runner.py:41-44`, `deepseek/config.py:55-99` (directory created at `:57-58`) |
| 14 | Build `docker create` arguments (host uid:gid, two bind mounts, key passed by variable name, image id, prompt) | `_run_task` | `deepseek/runner.py:45-57` |
| 15 | `docker create`, then `docker start --attach` with stdout to `stdout.jsonl` and stderr to `stderr.log` | `run_batch_container` | `docker_self/batch_container.py:28-40` |
| 16 | Timeout: mark `generation_status = "timeout"`, `docker stop --time 10` | `run_batch_container` | `docker_self/batch_container.py:41-45` |
| 17 | `docker inspect`; `completed` only if exited, exit code 0, not OOM-killed, no error, attach exit 0 | `run_batch_container` | `docker_self/batch_container.py:47-60` |
| 18 | Always `docker rm --force`; record `duration_seconds` | `run_batch_container` | `docker_self/batch_container.py:64-72` |
| 19 | Workspace output is whatever the agent left in the bind mount | n/a | `deepseek/runner.py:50` |
| 20 | Add paths, image info and the team summary to the result | `_run_task`, `summarize_sessions` | `deepseek/runner.py:60-64`, `deepseek/session_summary.py:7-85` |
| 21 | `status = "completed"` only if `generation_status == "completed"`; a cleanup error forces `"failed"`. `team.status` is not consulted. | `_run_task` | `deepseek/runner.py:65-68` |
| 22 | Evaluation hand-off. Returns early with `evaluation_status = "skipped"` if disabled or `status != "completed"` | `evaluate_result` | `runner.py:82-84` |
| 23 | Copy the workspace to `workspaces/<run_id>/evaluation/workspace`, run the evaluator on the copy | `evaluate_result` | `runner.py:86-95` |
| 24 | Evaluator: zip, delete package files and the task's test files, write a Dockerfile `FROM ghcr.io/multimodal-art-projection/nl2repobench/<task>:1.0`, build, run the task's test commands, parse pytest counts | `post_process_task` | `openhands/post_processor.py:511-532` (Dockerfile at `:282`, parsing at `:429-482`) |
| 25 | `score = passed` count; an evaluator error sets `status = "failed"` | `evaluate_result` | `runner.py:98-105` |
| 26 | Stamp ids and time, default the score fields, write `result/<run_id>.json` | `run_batch` | `runner.py:116-128` |
| 27 | Exit 1 if any task's `status != "completed"` | `main` | `main.py:39-41` |

A job that raises instead of returning still gets a result file, with `status = "error"` (`runner.py:118-119`).

## 5. Result JSON as written by the DeepSeek path

| Key | Set by |
|---|---|
| `container_name`, `exit_code`, `generation_status`, `stdout_path`, `stderr_path`, `container_log_path` | `docker_self/batch_container.py:19-23` |
| `container_id`, `attach_exit_code`, `error`, `cleanup_error`, `duration_seconds` | `docker_self/batch_container.py:33-72` (present when applicable) |
| `task_uuid`, `workspace_path`, `config_path`, `image`, `team`, `session_logs_path` | `deepseek/runner.py:60-64` |
| `status` | `deepseek/runner.py:66-68`, may be changed at `runner.py:103,105` |
| `evaluation_status`, `test_score`, `score` | `runner.py:82`, `runner.py:101`, `runner.py:103,105` (errors), defaults at `runner.py:125-127` |
| `post_process_result`, `evaluation_workspace_path`, `evaluation_error` | `runner.py:96-97,105` (only when evaluation runs) |
| `backend`, `module_name`, `pro_name`, `saved_at` | `runner.py:120-124` |

`generation_status` values: `completed`, `failed`, `timeout`, `error`. `evaluation_status` values: `skipped`, `completed`, `error`.

## 6. Gotchas

- **G1. `startPro` model fields are parsed by the backend, not by shared code.** `runner.model_tasks` validates only `moduleName` and `proNameList`. `protocol`, `baseUrl` fallback to `NL2REPO_BASE_URL`, `apiKeyEnv` default `NL2REPO_API_KEY`, `contextWindow`, `maxTokens`, `reasoningEffort`, `reasoningEfforts` and `compat` are read only in `deepseek/config.py:16-51`. OpenHands reads `moduleName`, `apiKeyEnv`, `sk` and `baseUrl` and nothing else (`openhands/openhands_app.py:29-36`), and has no `apiKeyEnv` default. A new backend must write its own resolver.
- **G2. The default `protocol` is `openai-completions`** (`deepseek/config.py:16`). That default is DeepSeek's, not the repo's.
- **G3. A legacy inline key is still accepted.** `sk` is read at `deepseek/config.py:26` and `openhands/openhands_app.py:29`, and the shipped `config.json:6` still uses it. The key is returned separately from the public settings (`deepseek/config.py:52`) and reaches the container by variable name only (`deepseek/runner.py:54`), so it never enters the result JSON or `docker` argv.
- **G4. Endpoint details are kept out of error text.** `docker_self/batch_container.py:62-63` deliberately does not stringify `CalledProcessError` because its argv may contain them.
- **G5. Timed-out and failed generations are never evaluated**, even if the workspace holds usable code (`runner.py:83`). A timeout therefore reports `score: null`, not a low score.
- **G6. `status` is not pass or fail.** It means every requested stage ran. `score` is the count of passed tests (`runner.py:100`); there is no threshold.
- **G7. Run directory names are not bare UUIDs.** `new_run_id` returns `<task>-<model>` lower-cased and truncated to 70 characters, then `-<uuid hex>` (`runner.py:30-31`). The same string names the container (`dsh-<run_id>`, `deepseek/runner.py:58`) and the evaluator image and container (`python-test-<run_id>`, `openhands/post_processor.py:527,530`).
- **G8. The evaluator needs its own network and platform.** It builds `FROM --platform=linux/amd64 ghcr.io/multimodal-art-projection/nl2repobench/<task>:1.0` (`openhands/post_processor.py:282`), so evaluation pulls from GHCR and needs amd64 emulation on ARM hosts. Generation does not force a platform: neither `FROM` line in `docker/deepseek.Dockerfile:1-2` nor the build command in `scripts/build_deepseek.sh:14` passes `--platform`.
- **G9. The evaluator mutates its input**, which is why `evaluate_result` gives it a copy (`runner.py:87-92`). It deletes `setup.py`, `pyproject.toml`, `requirements.txt` and similar from the copy (`openhands/post_processor.py:187-228`).
- **G10. Pins are duplicated.** The harness pin `639ed01539` appears in `deepseek/runner.py:15` and `scripts/build_deepseek.sh:5`; `_image_info` enforces it through the image label `org.nl2repobench.harness-revision` (`docker/deepseek.Dockerfile:18`, `deepseek/runner.py:28-30`). The session reader accepts only `session.v4.jsonl` with `version == 4` (`deepseek/session_summary.py:11,15-16`).
- **G11. `config.json` lists a task that does not exist.** It names `more-itertools` but the directory is `test_files/more-Itertools`, and task names are matched as exact strings against the directory names that `os.listdir` returns (`test_data_service.py:38,104`, `runner.py:49,64`), so `model_tasks` rejects the shipped config on every filesystem (`runner.py:64-65`). Reproduce: `python3 -c "import os; print('more-itertools' in os.listdir('test_files'))"` prints `False`. `test_files/` holds 104 task directories plus `task_difficulty.csv`.
- **G12. Importing `logging_config` has a side effect.** It creates `logs/application.log` relative to the current directory at import (`logging_config.py:165-166`), and `main.py:8` imports it before the `chdir` at `main.py:31`.
- **G13. Concurrency defaults differ.** `max_pool_size` defaults to 1 for DeepSeek (`deepseek/runner.py:74`) and 10 for OpenHands (`openhands/openhands_app.py:71`). The OpenHands timeout is a top-level `task_timeout_seconds` (`openhands/openhands_app.py:72`); DeepSeek's lives under the `deepseek` object (`deepseek/runner.py:84`).
- **G14. OpenHands writes the API key to disk.** It renders the resolved key into `workspaces/<run_id>/config.toml` in plain text, with mode 0600 (`openhands/openhands_app.py:29-44`). DeepSeek does not (G3). Results are published openly, so never publish an OpenHands run's `workspaces/` directory as is.
- **G15. `only_test.py` re-scores a run destructively.** It calls the evaluator on `workspaces/<run_id>/workspace` itself (`only_test.py:17-18`), not on a copy, so it deletes the package and test files from the generated repo (G9). Copy the workspace first if you use it.

## 7. Not checked

| Claim | Status | What would verify it |
|---|---|---|
| The DeepSeek path runs end to end | NOT CHECKED. The commit messages of `d08501b` and `4bf6013` each report one successful `jsonlines` run; nothing was run in this session. | Build the image and run one task with a cheap model |
| Behaviour of the DeepSeek harness itself (tools such as `spawn_teammate`, `send_message`, `wait_agent`; "the harness stops all teammates as soon as the lead finishes") | NOT CHECKED. The harness source is not in this repo; `scripts/build_deepseek.sh:7` expects a local checkout. The statements come from `deepseek/prompt.txt` and `readme.md:76`. | Read the harness at commit `639ed01539` |
| The evaluator works when package files are deleted before `pip install -e .` runs | NOT CHECKED. Depends on what the `ghcr.io/.../<task>:1.0` base images contain. | Pull one image and inspect `/workspace` |
| `tests/test_docker.py` still runs | NOT CHECKED. It predates the refactor and is not referenced by any workflow. | `pytest tests/` with Docker available |
