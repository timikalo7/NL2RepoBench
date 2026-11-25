"""Launch the local Claude Code image once for each benchmark task (PLAN §6)."""

import json
import os
import re
import subprocess
from functools import partial
from pathlib import Path

from docker_self.batch_container import docker_command, run_batch_container
from runner import Job, evaluate_result, evaluation_enabled, model_tasks, new_run_id, positive_int, run_batch
from .config import model_environment, resolve_model
from .session_summary import summarize_run

# The pin also lives in scripts/build_claude.sh (PLAN §5); keep the two equal.
CLAUDE_CODE_VERSION = "2.1.325"
DEFAULT_IMAGE = f"nl2repobench-claude:{CLAUDE_CODE_VERSION}"
PACKAGE_DIR = Path(__file__).parent
OPTION_KEYS = {"image", "task_timeout_seconds", "max_turns", "max_budget_usd", "prompt_file", "gateway_env"}
# Tools that start another agent, web tools, and nested Claude Code runs (PLAN D3, D11, §6.2).
DISALLOWED_TOOLS = ["Agent", "Workflow", "Skill", "WebSearch", "WebFetch", "Bash(claude *)", "Bash(*/claude *)"]
# gateway_env may not override what the backend sets itself, and is for non-secret settings only.
RESERVED_ENV = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CONFIG_DIR", "HOME", "PATH", "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB",
}
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)


def _image_info(image: str) -> dict:
    """Fail before scheduling when the locally built image is missing or has the wrong pin."""
    try:
        inspected = docker_command(["image", "inspect", image], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Claude Code image is unavailable. Start Docker and run scripts/build_claude.sh.") from exc
    value = json.loads(inspected.stdout)[0]
    revision = (value["Config"].get("Labels") or {}).get("org.nl2repobench.harness-revision", "")
    if revision != CLAUDE_CODE_VERSION:
        raise ValueError(f"Claude Code image must be built for version {CLAUDE_CODE_VERSION}, found {revision!r}")
    return {"tag": image, "id": value["Id"], "harness_revision": revision}


def _gateway_env(value) -> list:
    """Validate claude.gateway_env (PLAN §4.1, §10) into NAME=VALUE pairs."""
    if not isinstance(value, dict):
        raise ValueError("claude.gateway_env must be an object of variable names to string values")
    pairs = []
    for name, setting in value.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
            raise ValueError(f"claude.gateway_env: {name!r} is not an environment variable name")
        if name in RESERVED_ENV:
            raise ValueError(f"claude.gateway_env may not set {name}; the backend sets it")
        if SECRET_NAME.search(name):
            raise ValueError(f"claude.gateway_env is for non-secret settings; {name} looks like a credential")
        if not isinstance(setting, str):
            raise ValueError(f"claude.gateway_env.{name} must be a string")
        pairs.append(f"{name}={setting}")
    return pairs


def _options(supplied) -> dict:
    if not isinstance(supplied, dict):
        raise ValueError("claude must be an object")
    unknown = supplied.keys() - OPTION_KEYS
    if unknown:
        raise ValueError(f"Unknown claude settings: {sorted(unknown)}")
    options = {
        "image": supplied.get("image", DEFAULT_IMAGE),
        "task_timeout_seconds": positive_int(supplied.get("task_timeout_seconds", 7200), "claude.task_timeout_seconds"),
        "gateway_env": _gateway_env(supplied.get("gateway_env", {})),
    }
    if not isinstance(options["image"], str) or not options["image"]:
        raise ValueError("claude.image must be a nonempty string")
    if "max_turns" in supplied:
        options["max_turns"] = positive_int(supplied["max_turns"], "claude.max_turns")
    if "max_budget_usd" in supplied:
        budget = supplied["max_budget_usd"]
        if type(budget) not in (int, float) or budget <= 0:
            raise ValueError("claude.max_budget_usd must be a positive number")
        options["max_budget_usd"] = budget
    prompt_file = Path(supplied.get("prompt_file", PACKAGE_DIR / "prompt.txt"))
    if not prompt_file.is_file():
        raise ValueError(f"claude.prompt_file does not exist: {prompt_file}")
    options["prompt"] = prompt_file.read_text(encoding="utf-8").strip()
    if not options["prompt"]:
        raise ValueError("The prompt file is empty")
    return options


def _claude_arguments(model: dict, options: dict) -> list:
    """Arguments after the image: the prompt follows -p and --disallowedTools goes last (PLAN §6.2)."""
    arguments = ["-p", options["prompt"], "--output-format", "stream-json", "--verbose",
                 "--model", model["model"], "--permission-mode", "bypassPermissions"]
    if "reasoning_effort" in model:
        arguments += ["--effort", model["reasoning_effort"]]
    if "max_turns" in options:
        arguments += ["--max-turns", str(options["max_turns"])]
    if "max_budget_usd" in options:
        arguments += ["--max-budget-usd", str(options["max_budget_usd"])]
    return arguments + ["--disallowedTools", *DISALLOWED_TOOLS]


def _run_task(run_id: str, test_data, model: dict, secret_env: dict,
              options: dict, image: dict, evaluate: bool) -> dict:
    run_dir = Path("workspaces").resolve() / run_id
    workspace = run_dir / "workspace"
    workspace.mkdir(parents=True)
    home = run_dir / "claude-home"
    (home / "config").mkdir(parents=True)
    (home / "user").mkdir()
    (workspace / "start.md").write_bytes(Path(test_data.md).read_bytes())
    (run_dir / "prompt.txt").write_text(options["prompt"] + "\n", encoding="utf-8")
    # Secrets and the endpoint reach docker only through its environment, passed by name (PLAN D8).
    env = dict(os.environ, **secret_env)
    arguments = [
        "--init",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--volume", f"{workspace}:/workspace:rw",
        "--volume", f"{home}:/claude-home:rw",
        "--env", "HOME=/claude-home/user",
        "--env", "PATH=/claude-home/user/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
    ]
    for name in secret_env:
        arguments += ["--env", name]
    for pair in model_environment(model) + options["gateway_env"]:
        arguments += ["--env", pair]
    arguments += ["--add-host", "host.docker.internal:host-gateway", image["id"], *_claude_arguments(model, options)]
    result = run_batch_container(arguments, f"claude-{run_id}", run_dir,
                                 options["task_timeout_seconds"], env=env)
    summary = summarize_run(Path(result["stdout_path"]))
    result.update(
        task_uuid=run_id, workspace_path=str(workspace), image=image, claude=summary,
        session_logs_path=str(home / "config" / "projects"),
    )
    # D7: a clean exit is not enough; the stream must end in a successful result event.
    completed = result["generation_status"] == "completed" and summary["status"] == "completed"
    result["status"] = "completed" if completed and not result.get("cleanup_error") else "failed"
    return evaluate_result(result, test_data, evaluate)


def start_claude(config: dict) -> list:
    """Validate every task, option and endpoint before starting any container (PLAN §6.1)."""
    pool_size = positive_int(config.get("max_pool_size", 1), "max_pool_size")
    evaluate = evaluation_enabled(config)
    options = _options(config.get("claude", {}))
    if os.getuid() == 0:
        raise RuntimeError("The claude backend refuses to run as root: Claude Code rejects bypassPermissions "
                           "under uid 0, and artifacts must stay readable. Run as an unprivileged user (PLAN D5).")
    specifications = [(task, *resolve_model(entry)) for entry, _, task in model_tasks(config)]
    image = _image_info(options["image"])
    jobs = []
    for task, model, secret_env in specifications:
        run_id = new_run_id(task.proName, model["model"])
        jobs.append(Job(run_id, "claude", model["model"], task.proName,
                        partial(_run_task, run_id, task, model, secret_env, options, image, evaluate)))
    return run_batch(jobs, pool_size)
