"""Summarize a Claude Code stream-json run from stdout.jsonl (PLAN §7)."""

import json
from pathlib import Path

DELEGATION_TOOLS = {"Agent", "Workflow", "Skill"}


def summarize_run(stdout_path: Path) -> dict:
    """Find events by type and subtype; tolerate truncated or unparsable lines."""
    init, result = None, None
    compactions = api_retries = delegations = unparsable = 0
    try:
        lines = Path(stdout_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        lines = []
        unparsable = -1
        read_error = f"Cannot read {stdout_path}: {type(exc).__name__}"
    else:
        read_error = None
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            unparsable += 1  # A timeout can cut the last line short.
            continue
        if not isinstance(event, dict):
            continue
        kind, subtype = event.get("type"), event.get("subtype")
        if kind == "system" and subtype == "init" and init is None:
            init = event
        elif kind == "system" and subtype == "compact_boundary":
            compactions += 1
        elif kind == "system" and subtype == "api_retry":
            api_retries += 1
        elif kind == "result":
            result = event  # Keep the last one.
        if kind in {"assistant", "user"}:
            if event.get("parent_tool_use_id") is not None:
                delegations += 1
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in DELEGATION_TOOLS:
                    delegations += 1

    errors = [read_error] if read_error else []
    summary = {"compactions": compactions, "api_retries": api_retries, "delegations": delegations,
               "unparsable_lines": unparsable}
    if init:
        summary.update(claude_code_version=init.get("claude_code_version"), model=init.get("model"),
                       tools=init.get("tools"))
    else:
        errors.append("No system/init event in stdout.jsonl")
    if result:
        denials = result.get("permission_denials") or []
        summary.update(
            result_subtype=result.get("subtype"), is_error=result.get("is_error"),
            stop_reason=result.get("stop_reason"), num_turns=result.get("num_turns"),
            session_id=result.get("session_id"), total_cost_usd=result.get("total_cost_usd"),
            usage=result.get("usage"), model_usage=result.get("modelUsage"),
            permission_denials=len(denials),
            denied_tool_calls=[{"tool_name": d.get("tool_name"), "tool_input": d.get("tool_input")}
                               for d in denials if isinstance(d, dict)],
        )
        if result.get("subtype") != "success" or result.get("is_error") is not False:
            errors.append(f"Final result is {result.get('subtype')!r} with is_error={result.get('is_error')!r}")
            for item in result.get("errors") or []:
                errors.append(str(item)[:500])
    else:
        errors.append("No result event in stdout.jsonl")
    summary["status"] = "completed" if not errors else "incomplete"
    summary["errors"] = errors
    return summary
