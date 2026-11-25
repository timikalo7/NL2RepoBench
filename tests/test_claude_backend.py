"""Offline checks for the claude backend (PLAN §8, T5). Run: python3 -m unittest tests.test_claude_backend"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from claude.config import model_environment, resolve_model
from claude.runner import ALLOWED_TOOLS, DISALLOWED_TOOLS, SECCOMP_PROFILE, _claude_arguments, _docker_arguments, _gateway_env
from claude.session_summary import summarize_run

INIT = {"type": "system", "subtype": "init", "model": "m", "tools": ["Bash", "Read"], "claude_code_version": "2.1.325"}
HOOK = {"type": "system", "subtype": "hook_started", "hook_name": "SessionStart"}
TOOL_USE = {"type": "assistant", "parent_tool_use_id": None,
            "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}


def _result(subtype, is_error, **extra):
    return {"type": "result", "subtype": subtype, "is_error": is_error, "num_turns": 3,
            "session_id": "s", "total_cost_usd": 0, "usage": {}, "modelUsage": {"m": {}},
            "permission_denials": [], **extra}


class SummarizeRunTest(unittest.TestCase):
    def _write(self, lines):
        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        handle.write("\n".join(lines) + "\n")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return Path(handle.name)

    def test_success_stream_completes(self):
        path = self._write([json.dumps(e) for e in (INIT, TOOL_USE, _result("success", False))])
        summary = summarize_run(path)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["delegations"], 0)
        self.assertEqual(summary["claude_code_version"], "2.1.325")

    def test_max_turns_is_incomplete(self):
        path = self._write([json.dumps(e) for e in (INIT, _result("error_max_turns", True, errors=["max turns"]))])
        summary = summarize_run(path)
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["result_subtype"], "error_max_turns")

    def test_truncated_file_is_incomplete_without_raising(self):
        path = self._write([json.dumps(INIT), json.dumps(TOOL_USE), '{"type": "assistant", "mess'])
        summary = summarize_run(path)
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["unparsable_lines"], 1)

    def test_init_found_by_type_not_position(self):
        path = self._write([json.dumps(e) for e in (HOOK, INIT, _result("success", False))])
        self.assertEqual(summarize_run(path)["model"], "m")

    def test_delegation_counted(self):
        sub = {"type": "assistant", "parent_tool_use_id": "toolu_1", "message": {"content": []}}
        agent = {"type": "assistant", "parent_tool_use_id": None,
                 "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {}}]}}
        path = self._write([json.dumps(e) for e in (INIT, sub, agent, _result("success", False))])
        self.assertEqual(summarize_run(path)["delegations"], 2)

    def test_missing_file(self):
        self.assertEqual(summarize_run(Path("/nonexistent/stdout.jsonl"))["status"], "incomplete")


class LaunchArgumentsTest(unittest.TestCase):
    def test_prompt_follows_p_and_disallowed_tools_last(self):
        args = _claude_arguments({"model": "m"}, {"prompt": "do it", "max_turns": 2})
        self.assertEqual(args[:2], ["-p", "do it"])
        self.assertEqual(args[-len(DISALLOWED_TOOLS) - 1:], ["--disallowedTools", *DISALLOWED_TOOLS])
        self.assertIn("Bash(claude *)", args)
        start = args.index("--allowedTools")
        self.assertEqual(args[start:start + len(ALLOWED_TOOLS) + 1], ["--allowedTools", *ALLOWED_TOOLS])

    def test_gateway_env_rejects_reserved_and_secret_names(self):
        self.assertEqual(_gateway_env({"API_TIMEOUT_MS": "600000"}), ["API_TIMEOUT_MS=600000"])
        for bad in ({"ANTHROPIC_BASE_URL": "x"}, {"MY_API_KEY": "x"}, {"lower": "x"}, {"A": 1}):
            with self.assertRaises(ValueError):
                _gateway_env(bad)


class DockerArgumentsTest(unittest.TestCase):
    def setUp(self):
        self.args = _docker_arguments(Path("/w"), Path("/h"), {"model": "m", "context_window": 262144},
                                      {"ANTHROPIC_AUTH_TOKEN": "dummy-value", "ANTHROPIC_BASE_URL": "http://h:4000"},
                                      {"prompt": "p", "gateway_env": ["API_TIMEOUT_MS=1"]}, {"id": "sha256:img"})

    def test_security_options_and_no_privilege(self):
        self.assertIn(f"seccomp={SECCOMP_PROFILE}", self.args)
        self.assertIn("systempaths=unconfined", self.args)
        self.assertTrue(SECCOMP_PROFILE.is_file())
        for forbidden in ("--privileged", "--cap-add", "seccomp=unconfined"):
            self.assertNotIn(forbidden, self.args)
        self.assertEqual(self.args[:2], ["--init", "--user"])

    def test_secrets_passed_by_name_only(self):
        self.assertNotIn("dummy-value", " ".join(self.args))
        self.assertIn("ANTHROPIC_AUTH_TOKEN", self.args)
        self.assertIn("ANTHROPIC_BASE_URL", self.args)

    def test_image_precedes_claude_arguments(self):
        position = self.args.index("sha256:img")
        self.assertEqual(self.args[position + 1:position + 3], ["-p", "p"])
        self.assertIn("API_TIMEOUT_MS=1", self.args[:position])
        self.assertEqual(self.args[position - 2:position], ["--add-host", "host.docker.internal:host-gateway"])

    def test_seccomp_profile_extends_default(self):
        profile = json.loads(SECCOMP_PROFILE.read_text())
        self.assertEqual(profile["defaultAction"], "SCMP_ACT_ERRNO")
        added = profile["syscalls"][-1]
        self.assertEqual(sorted(added["names"]),
                         ["clone", "mount", "pivot_root", "sethostname", "umount2", "unshare"])
        self.assertNotIn("includes", added)


class ResolveModelTest(unittest.TestCase):
    def setUp(self):
        os.environ["CLAUDE_TEST_KEY"] = "dummy-value"
        self.addCleanup(os.environ.pop, "CLAUDE_TEST_KEY")

    def test_bearer_strips_v1_and_sets_window(self):
        public, secret = resolve_model({"moduleName": "q", "baseUrl": "http://h:4000/v1/", "authHeader": "bearer",
                                        "apiKeyEnv": "CLAUDE_TEST_KEY", "contextWindow": 262144})
        self.assertEqual(secret, {"ANTHROPIC_AUTH_TOKEN": "dummy-value", "ANTHROPIC_BASE_URL": "http://h:4000"})
        self.assertIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW=262144", model_environment(public))
        self.assertNotIn("dummy-value", json.dumps(public))

    def test_baseurl_required_without_fallback(self):
        os.environ["NL2REPO_BASE_URL"] = "http://127.0.0.1:9"
        self.addCleanup(os.environ.pop, "NL2REPO_BASE_URL")
        with self.assertRaises(ValueError):
            resolve_model({"moduleName": "q", "baseUrl": "", "apiKeyEnv": "CLAUDE_TEST_KEY"})


if __name__ == "__main__":
    unittest.main()
