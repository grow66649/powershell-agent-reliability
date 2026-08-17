import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import tomllib
import unittest
from unittest import mock

import codex_automation


PSR_SKILL = "C:/Users/example/.mirasim/skills/powershell-reliability/SKILL.md"
PSR_MCP = "C:/repo/target/release/powershell-agent-reliability.exe"


def _live_config():
    return {
        "approval_policy": "never",
        "disable_response_storage": True,
        "model_reasoning_effort": "max",
        "model_reasoning_summary": "none",
        "model_verbosity": "low",
        "sandbox_mode": "danger-full-access",
        "service_tier": "default",
        "model_provider": "codex_local_access",
        "model": "gpt-5.6-luna",
        "notify": ["secret-sidecar.exe"],
        "features": {"plugins": True, "fast_mode": True, "memories": True},
        "model_providers": {
            "codex_local_access": {
                "name": "Codex API Service",
                "base_url": "http://localhost:52567/v1",
                "wire_api": "responses",
                "requires_openai_auth": False,
                "experimental_bearer_token": "TOP-SECRET",
                "http_headers": {"x-private": "SECRET-HEADER"},
            }
        },
        "mcp_servers": {
            "unrelated": {"command": "other.exe", "enabled": True},
            "psr_reliability_native": {"command": PSR_MCP, "args": [], "startup_timeout_sec": 10},
        },
    }


class ProfileMaterializerTests(unittest.TestCase):
    def test_build_profile_copies_only_allowlisted_runtime_provider_and_psr_mcp(self):
        text = codex_automation.build_profile_text(_live_config(), "S", PSR_SKILL, PSR_MCP)
        self.assertIn('model = "gpt-5.6-luna"', text)
        self.assertIn('model_provider = "codex_local_access"', text)
        self.assertIn('[model_providers.codex_local_access]', text)
        self.assertIn('experimental_bearer_token = "TOP-SECRET"', text)
        self.assertIn('[mcp_servers.psr_reliability_native]', text)
        self.assertNotIn('[mcp_servers.unrelated]', text)
        self.assertNotIn('notify =', text)
        self.assertIn('plugins = false', text)

    def test_build_profile_sets_only_psr_skill_for_s_and_disables_it_for_m(self):
        s_text = codex_automation.build_profile_text(_live_config(), "S", PSR_SKILL, PSR_MCP)
        m_text = codex_automation.build_profile_text(_live_config(), "M", PSR_SKILL, PSR_MCP)
        self.assertIn('path = "' + PSR_SKILL + '"', s_text)
        self.assertIn('enabled = true', s_text)
        self.assertIn('path = "' + PSR_SKILL + '"', m_text)
        self.assertIn('enabled = false', m_text)

    def test_profile_receipt_never_contains_provider_secrets(self):
        receipt = codex_automation.profile_receipt(_live_config(), "S", "A" * 64, "B" * 64, "C" * 64)
        encoded = json.dumps(receipt, sort_keys=True)
        self.assertNotIn("TOP-SECRET", encoded)
        self.assertNotIn("SECRET-HEADER", encoded)
        self.assertEqual(receipt["model"], "gpt-5.6-luna")
        self.assertEqual(receipt["provider"], "codex_local_access")
        self.assertEqual(receipt["arm"], "S")


class SurfaceConformanceTests(unittest.TestCase):
    def _prompt_payload(self, skill_lines):
        text = "Available skills:\n" + "\n".join(skill_lines)
        return [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": text}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "probe"}]},
        ]

    def test_parse_prompt_input_skills_extracts_names_and_paths(self):
        payload = self._prompt_payload([
            "- powershell-reliability: failure-only helper (file: r1/powershell-reliability/SKILL.md)",
            "- other-skill: unrelated (file: r0/other-skill/SKILL.md)",
        ])
        skills = codex_automation.parse_prompt_input_skills(payload)
        self.assertEqual([item["name"] for item in skills], ["powershell-reliability", "other-skill"])
        self.assertEqual(skills[0]["path"], "r1/powershell-reliability/SKILL.md")

    def test_verify_arm_catalog_accepts_minimal_s_and_minimal_m(self):
        codex_automation.verify_arm_catalog("S", [{"name": "powershell-reliability", "path": PSR_SKILL}])
        codex_automation.verify_arm_catalog("M", [])

    def test_verify_arm_catalog_rejects_missing_or_unrelated_skills(self):
        with self.assertRaisesRegex(ValueError, "S catalog"):
            codex_automation.verify_arm_catalog("S", [])
        with self.assertRaisesRegex(ValueError, "unrelated"):
            codex_automation.verify_arm_catalog("S", [
                {"name": "powershell-reliability", "path": PSR_SKILL},
                {"name": "other", "path": "C:/skills/other/SKILL.md"},
            ])
        with self.assertRaisesRegex(ValueError, "M catalog"):
            codex_automation.verify_arm_catalog("M", [{"name": "powershell-reliability", "path": PSR_SKILL}])

    def test_verify_mcp_profile_requires_exactly_psr_reliability_native(self):
        profile = tomllib.loads(codex_automation.build_profile_text(_live_config(), "S", PSR_SKILL, PSR_MCP))
        codex_automation.verify_mcp_profile(profile)
        profile["mcp_servers"]["extra"] = {"command": "extra.exe"}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            codex_automation.verify_mcp_profile(profile)


class CliExecutionTests(unittest.TestCase):
    def test_verify_cli_identity_checks_hash_and_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = pathlib.Path(temp_dir) / "codex.exe"
            exe.write_bytes(b"fake-codex")
            expected_hash = hashlib.sha256(b"fake-codex").hexdigest().upper()
            completed = mock.Mock(returncode=0, stdout="codex-cli 0.148.0-alpha.9\n", stderr="")
            runner = mock.Mock(return_value=completed)
            result = codex_automation.verify_cli_identity(exe, "0.148.0-alpha.9", expected_hash, runner=runner)
            self.assertEqual(result["version"], "0.148.0-alpha.9")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                codex_automation.verify_cli_identity(exe, "0.148.0-alpha.9", "0" * 64, runner=runner)
            with self.assertRaisesRegex(ValueError, "version"):
                codex_automation.verify_cli_identity(exe, "0.147.0", expected_hash, runner=runner)

    def test_codex_argv_uses_ephemeral_json_workspace_and_stdin(self):
        argv = codex_automation.codex_argv(pathlib.Path("C:/Codex/codex.exe"), pathlib.Path("C:/workspace"), model="gpt-5.6-luna")
        self.assertEqual(argv, ["C:/Codex/codex.exe", "exec", "--ephemeral", "--json", "--model", "gpt-5.6-luna", "-C", "C:/workspace", "-"])
        self.assertNotIn("dangerously", " ".join(argv).lower())

    def test_remove_profile_deletes_directory_and_fails_if_leftover(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir) / "profile"
            root.mkdir()
            (root / "config.toml").write_text("model='x'\n", encoding="utf-8")
            codex_automation.remove_profile(root)
            self.assertFalse(root.exists())

    def test_run_codex_process_records_timeout_separately(self):
        class FakeProcess:
            pid = 4321
            returncode = None
            def communicate(self, input=None, timeout=None):
                if input is not None:
                    raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)
                self.returncode = 1
                return (None, None)
        fake = FakeProcess()
        popen = mock.Mock(return_value=fake)
        killer = mock.Mock()
        clock = mock.Mock(side_effect=[10.0, 10.125])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            profile = root / "profile"
            workspace = root / "workspace"
            profile.mkdir(); workspace.mkdir()
            result = codex_automation.run_codex_process(
                pathlib.Path("C:/Codex/codex.exe"), workspace, profile, b"exact prompt\n",
                root / "stdout.jsonl", root / "stderr.log", 12, popen_factory=popen, tree_killer=killer, clock=clock, model="gpt-5.6-luna",
            )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["task_wall_clock_ms"], 125)
        self.assertEqual(result["termination_reason"], "timeout")
        killer.assert_called_once_with(fake)
        self.assertIn("gpt-5.6-luna", popen.call_args.args[0])
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["CODEX_HOME"], str(profile))
        self.assertEqual(kwargs["env"]["CODEX_SQLITE_HOME"], str(profile))

    def test_run_codex_process_forces_parent_kill_if_tree_kill_does_not_settle(self):
        fake = mock.Mock(pid=4321, returncode=None)
        fake.communicate = mock.Mock(side_effect=[
            subprocess.TimeoutExpired(cmd="codex", timeout=12),
            subprocess.TimeoutExpired(cmd="codex", timeout=10),
            (None, None),
        ])
        popen = mock.Mock(return_value=fake)
        killer = mock.Mock()
        clock = mock.Mock(side_effect=[20.0, 20.25])
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir); profile = root / "profile"; workspace = root / "workspace"
            profile.mkdir(); workspace.mkdir()
            result = codex_automation.run_codex_process(
                pathlib.Path("C:/Codex/codex.exe"), workspace, profile, b"exact prompt\n",
                root / "stdout.jsonl", root / "stderr.log", 12, popen_factory=popen, tree_killer=killer, clock=clock,
            )
        self.assertTrue(result["timed_out"])
        killer.assert_called_once_with(fake)
        fake.kill.assert_called_once_with()
        self.assertEqual(fake.communicate.call_count, 3)


class ProfileAclAndRowCleanupTests(unittest.TestCase):
    def test_restrict_profile_acl_uses_current_identity_and_verifies_no_inheritance(self):
        whoami = mock.Mock(return_value=mock.Mock(returncode=0, stdout="growu\\growu\n", stderr=""))
        calls = []
        def icacls(argv, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                return mock.Mock(returncode=0, stdout="Successfully processed 1 files\n", stderr="")
            return mock.Mock(returncode=0, stdout="C:\\profile growu\\growu:(OI)(CI)(F)\n", stderr="")
        codex_automation.restrict_profile_acl(pathlib.Path("C:/profile"), identity_runner=whoami, icacls_runner=icacls)
        self.assertIn("growu\\growu:(OI)(CI)F", calls[0])
        self.assertNotIn("(I)", calls[1])

    def test_run_row_always_removes_secret_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            profile = root / "profile"
            profile.mkdir()
            executor = mock.Mock(side_effect=RuntimeError("boom"))
            with self.assertRaisesRegex(RuntimeError, "boom"):
                codex_automation.run_with_profile_cleanup(profile, executor)
            self.assertFalse(profile.exists())


class ProfileAclRegressionTests(unittest.TestCase):
    def test_restrict_profile_acl_refuses_preexisting_children(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = pathlib.Path(temp_dir) / "profile"
            profile.mkdir()
            (profile / "config.toml").write_text("secret='x'\n", encoding="utf-8")
            whoami = mock.Mock(return_value=mock.Mock(returncode=0, stdout="growu\\growu\n", stderr=""))
            icacls = mock.Mock()
            with self.assertRaisesRegex(RuntimeError, "empty profile"):
                codex_automation.restrict_profile_acl(profile, identity_runner=whoami, icacls_runner=icacls)
            icacls.assert_not_called()


class FeatureIsolationTests(unittest.TestCase):
    def test_profile_disables_apps_remote_plugins_and_plugin_sharing(self):
        text = codex_automation.build_profile_text(_live_config(), "S", PSR_SKILL, PSR_MCP)
        self.assertIn("apps = false", text)
        self.assertIn("remote_plugin = false", text)
        self.assertIn("plugin_sharing = false", text)


class CliJsonAdapterTests(unittest.TestCase):
    def _write_jsonl(self, root, rows):
        path = pathlib.Path(root) / "events.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def test_parse_cli_jsonl_counts_started_command_mcp_and_exact_usage(self):
        rows = [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "Get-ChildItem D:\\coord", "cwd": "D:\\runtime\\abc", "exit_code": None, "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": "Get-ChildItem D:\\coord", "cwd": "D:\\runtime\\abc", "exit_code": 0, "status": "completed"}},
            {"type": "item.started", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "inspect_environment", "arguments": {}, "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "inspect_environment", "arguments": {}, "status": "completed", "error": None}},
            {"type": "item.completed", "item": {"id": "a1", "type": "agent_message", "text": "READY"}},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 20, "cache_write_input_tokens": 0, "output_tokens": 7, "reasoning_output_tokens": 3}},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            parsed = codex_automation.parse_cli_jsonl(self._write_jsonl(temp_dir, rows))
        self.assertEqual(parsed["thread_id"], "thread-1")
        self.assertEqual(parsed["native_command_count"], 1)
        self.assertEqual(parsed["mcp_call_count"], 1)
        self.assertEqual(parsed["reliability_mcp_call_count"], 1)
        self.assertEqual(parsed["commands"][0]["command"], "Get-ChildItem D:\\coord")
        self.assertEqual(parsed["commands"][0]["cwd"], "D:\\runtime\\abc")
        self.assertEqual(parsed["tokens"]["input_tokens"], 100)
        self.assertIsNone(parsed["tokens"]["total_tokens"])
        self.assertEqual(parsed["final_message"], "READY")

    def test_parse_cli_jsonl_rejects_orphan_tool_completions(self):
        orphan_items = [
            {"id": "c1", "type": "command_execution", "exit_code": 0, "status": "completed"},
            {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "status": "completed"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for item in orphan_items:
                with self.subTest(item_type=item["type"]):
                    path = self._write_jsonl(temp_dir, [{"type": "item.completed", "item": item}])
                    with self.assertRaisesRegex(ValueError, "completion without matching start"):
                        codex_automation.parse_cli_jsonl(path)

    def test_parse_cli_jsonl_counts_started_attempts_and_deduplicates_completion(self):
        rows = [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "slow.exe", "status": "in_progress"}},
            {"type": "item.started", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "arguments": {}, "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "arguments": {}, "status": "completed"}},
            {"type": "turn.failed", "error": {"message": "stopped"}},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            parsed = codex_automation.parse_cli_jsonl(self._write_jsonl(temp_dir, rows))
        self.assertEqual(parsed["native_command_count"], 1)
        self.assertEqual(parsed["incomplete_native_command_count"], 1)
        self.assertEqual(parsed["mcp_call_count"], 1)
        self.assertEqual(parsed["incomplete_mcp_call_count"], 0)
        self.assertEqual(parsed["reliability_mcp_call_count"], 1)


    def test_completed_failed_or_declined_items_are_terminal_not_incomplete(self):
        rows = [
            {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "status": "failed", "exit_code": 7}},
            {"type": "item.started", "item": {"id": "c2", "type": "command_execution", "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "c2", "type": "command_execution", "status": "declined"}},
            {"type": "item.started", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "status": "failed"}},
            {"type": "turn.failed", "error": {"message": "done"}},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            parsed = codex_automation.parse_cli_jsonl(self._write_jsonl(temp_dir, rows))
        self.assertEqual(parsed["native_command_count"], 2)
        self.assertEqual(parsed["incomplete_native_command_count"], 0)
        self.assertEqual(parsed["mcp_call_count"], 1)
        self.assertEqual(parsed["incomplete_mcp_call_count"], 0)
        self.assertEqual(parsed["commands"][0]["exit_code"], 7)
        self.assertEqual(parsed["commands"][0]["terminal_status"], "failed")
        self.assertLess(parsed["commands"][0]["started_event_index"], parsed["commands"][0]["completed_event_index"])

    def test_timeout_can_salvage_only_a_truncated_final_jsonl_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            path = root / "timeout.jsonl"
            path.write_text(
                json.dumps({"type": "item.started", "item": {"id": "m1", "type": "mcp_tool_call", "server": "psr_reliability_native", "tool": "diagnose_failure", "status": "in_progress"}})
                + "\n" + '{"type":"item.com', encoding="utf-8")
            parsed = codex_automation.parse_cli_jsonl(path, allow_truncated_tail=True)
            self.assertTrue(parsed["truncated_jsonl_tail"])
            self.assertEqual(parsed["mcp_call_count"], 1)
            self.assertEqual(parsed["incomplete_mcp_call_count"], 1)
            with self.assertRaisesRegex(ValueError, "malformed"):
                codex_automation.parse_cli_jsonl(path)
            middle = root / "middle.jsonl"
            middle.write_text('{"type":"item.started"}\n{"type":\n' + json.dumps({"type": "turn.failed", "error": {"message": "x"}}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "malformed"):
                codex_automation.parse_cli_jsonl(middle, allow_truncated_tail=True)

    def test_parse_cli_jsonl_keeps_missing_token_fields_none_and_rejects_malformed_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            path = self._write_jsonl(root, [{"type": "turn.completed", "usage": {"input_tokens": 2}}])
            parsed = codex_automation.parse_cli_jsonl(path)
            self.assertEqual(parsed["tokens"]["input_tokens"], 2)
            self.assertIsNone(parsed["tokens"]["output_tokens"])
            self.assertIsNone(parsed["tokens"]["total_tokens"])
            bad = root / "bad.jsonl"
            bad.write_text('{"type":"turn.started"}\n{"type":', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                codex_automation.parse_cli_jsonl(bad)

    def test_validate_cli_terminal_state_rejects_clean_exit_without_terminal_event(self):
        with self.assertRaisesRegex(ValueError, "terminal turn event"):
            codex_automation.validate_cli_terminal_state(
                {"timed_out": False, "exit_code": 0}, {"turn_status": "unknown"}
            )
        codex_automation.validate_cli_terminal_state(
            {"timed_out": True, "exit_code": 1}, {"turn_status": "unknown"}
        )
        codex_automation.validate_cli_terminal_state(
            {"timed_out": False, "exit_code": 1}, {"turn_status": "failed"}
        )

    def test_evaluate_manifest_row_uses_workspace_truth_not_process_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = {
                "case_id": "X1",
                "post_condition": {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]},
            }
            result = codex_automation.evaluate_manifest_row(manifest, workspace)
            self.assertFalse(result["passed"])
            (workspace / "result.txt").write_text("ok", encoding="utf-8")
            result = codex_automation.evaluate_manifest_row(manifest, workspace)
            self.assertTrue(result["passed"])

    def test_evaluate_manifest_row_rejects_workspace_root_link_before_grading(self):
        workspace = pathlib.Path("C:/opaque/runtime/row")
        manifest = {
            "case_id": "X1",
            "post_condition": {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]},
        }
        with mock.patch.object(codex_automation, "_path_is_link_or_junction", return_value=True):
            with mock.patch.object(codex_automation.routing_eval, "evaluate_workspace_state") as evaluate:
                with self.assertRaisesRegex(ValueError, "symlink|junction"):
                    codex_automation.evaluate_manifest_row(manifest, workspace)
        evaluate.assert_not_called()

    def test_normalized_receipt_combines_process_catalog_tool_tokens_and_post_condition(self):
        manifest = {"case_key": "X1-T01", "case_id": "X1", "trial_id": "T01", "arm": "S", "sequence": 1, "prompt_sha256": "A" * 64, "workspace_sha256": "B" * 64, "fixture_sha256": "C" * 64}
        process = {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 321}
        parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 2, "mcp_call_count": 1, "reliability_mcp_call_count": 1, "commands": [{"id": "c1", "type": "command_execution", "command": "Get-ChildItem D:\\private", "cwd": "D:\\private", "exit_code": 0, "terminal_status": "completed"}], "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
        parsed["tokens"]["input_tokens"] = 12
        profile = {"cli_version": "0.148.0-alpha.9", "cli_sha256": "D" * 64, "profile_fingerprint": "E" * 64, "mcp_sha256": "F" * 64}
        receipt = codex_automation.normalized_execution_receipt(manifest, process, parsed, profile, [{"name": "powershell-reliability", "path": PSR_SKILL}], {"passed": True, "source": "evaluator_workspace"}, True, True)
        self.assertEqual(receipt["post_condition_passed"], True)
        self.assertEqual(receipt["reliability_mcp_call_count"], 1)
        self.assertEqual(receipt["input_tokens"], 12)
        self.assertEqual(receipt["task_wall_clock_ms"], 321)
        self.assertEqual(receipt["skill_catalog"], ["powershell-reliability"])
        self.assertEqual(receipt["native_commands"], [{"id": "c1", "type": "command_execution", "exit_code": 0, "terminal_status": "completed"}])
        self.assertNotIn("D:\\private", json.dumps(receipt))
        self.assertTrue(receipt["profile_cleanup_ok"])
        self.assertTrue(receipt["workspace_cleanup_ok"])
        self.assertTrue(receipt["cleanup_ok"])


class ContaminationDetectionTests(unittest.TestCase):
    def test_text_mentions_windows_path_rejects_near_prefix(self):
        target = pathlib.Path("C:/campaign/coordinator")
        self.assertTrue(codex_automation._text_mentions_windows_path(f"Get-ChildItem '{target}'", target))
        self.assertTrue(codex_automation._text_mentions_windows_path(f"Get-ChildItem '{target}/fixtures/x.json'", target))
        self.assertFalse(codex_automation._text_mentions_windows_path(f"Get-ChildItem '{target}-cache'", target))

    def test_detect_campaign_contamination_resolves_coordinator_before_hashing(self):
        relative = pathlib.Path("relative-coordinator")
        resolved = relative.resolve(strict=False)
        current = {"case_id": "X1", "trial_id": "T01", "arm": "S", "workspace": "C:/runtime/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
        parsed = {"commands": [{"id": "c1", "type": "command_execution", "command": f"Get-ChildItem '{resolved}'"}]}
        evidence = codex_automation.detect_campaign_contamination(parsed, [current], current, relative)
        self.assertEqual(evidence, [{
            "kind": "coordinator_access", "command_id": "c1",
            "path_sha256": codex_automation._known_path_sha256(resolved),
        }])

    def test_detect_campaign_contamination_reports_only_known_coordinator_or_other_row_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            current_workspace = root / "runtime" / ("a" * 32) / ("b" * 32)
            other_workspace = root / "runtime" / ("a" * 32) / ("c" * 32)
            parsed = {
                "commands": [
                    {"id": "c1", "type": "command_execution", "command": f"Get-ChildItem '{coordinator}'"},
                    {"id": "c2", "type": "command_execution", "cwd": str(current_workspace), "command": "Get-ChildItem ."},
                    {"id": "c3", "type": "command_execution", "workdir": str(other_workspace), "command": "Get-ChildItem ."},
                ]
            }
            current = {"case_id": "X1", "trial_id": "T01", "arm": "S", "workspace": str(current_workspace)}
            other = {"case_id": "X1", "trial_id": "T01", "arm": "M", "workspace": str(other_workspace)}
            evidence = codex_automation.detect_campaign_contamination(parsed, [current, other], current, coordinator)
        self.assertEqual([item["kind"] for item in evidence], ["coordinator_access", "other_row_workspace_access"])
        self.assertEqual([item["command_id"] for item in evidence], ["c1", "c3"])
        self.assertTrue(all(set(item) == {"kind", "command_id", "path_sha256"} for item in evidence))
        self.assertTrue(all(len(item["path_sha256"]) == 64 for item in evidence))
        self.assertNotIn(str(coordinator), json.dumps(evidence))
        self.assertNotIn(str(other_workspace), json.dumps(evidence))


class RuntimeSurfaceProbeTests(unittest.TestCase):
    def test_probe_skill_catalog_uses_isolated_profile_and_parses_json(self):
        payload = [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "- powershell-reliability: helper (file: r1/powershell-reliability/SKILL.md)"}]}]
        runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=json.dumps(payload), stderr=""))
        skills = codex_automation.probe_skill_catalog(pathlib.Path("C:/Codex/codex.exe"), pathlib.Path("C:/profile"), runner=runner)
        self.assertEqual([item["name"] for item in skills], ["powershell-reliability"])
        self.assertEqual(runner.call_args.kwargs["env"]["CODEX_HOME"], str(pathlib.Path("C:/profile")))

    def test_probe_mcp_catalog_requires_one_enabled_reliability_server(self):
        payload = [{"name": "psr_reliability_native", "enabled": True, "transport": {"type": "stdio", "command": PSR_MCP, "args": []}}]
        runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=json.dumps(payload), stderr=""))
        result = codex_automation.probe_mcp_catalog(pathlib.Path("C:/Codex/codex.exe"), pathlib.Path("C:/profile"), runner=runner)
        self.assertEqual(result[0]["name"], "psr_reliability_native")
        bad = mock.Mock(return_value=mock.Mock(returncode=0, stdout=json.dumps(payload + [{"name": "other", "enabled": True}]), stderr=""))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            codex_automation.probe_mcp_catalog(pathlib.Path("C:/Codex/codex.exe"), pathlib.Path("C:/profile"), runner=bad)


class CliParserTests(unittest.TestCase):
    def _common(self):
        return [
            "--arm", "S", "--live-config", "C:/Users/test/.codex/config.toml",
            "--codex", "C:/Codex/codex.exe", "--codex-version", "0.148.0-alpha.9",
            "--codex-sha256", "A" * 64, "--skill-path", PSR_SKILL,
            "--skill-sha256", "B" * 64, "--mcp-path", PSR_MCP,
            "--mcp-sha256", "C" * 64, "--evidence-root", "C:/evidence",
            "--identity-lock", "C:/evidence/campaign-identity.json", "--model", "gpt-5.6-luna", "--public-main-sha", "0" * 40,
        ]

    def test_profile_check_parser_requires_runtime_identity_and_arm(self):
        args = codex_automation.parse_args(["profile-check", *self._common()])
        self.assertEqual(args.command, "profile-check")
        self.assertEqual(args.arm, "S")
        self.assertEqual(args.codex_version, "0.148.0-alpha.9")
        self.assertEqual(args.identity_lock, pathlib.Path("C:/evidence/campaign-identity.json"))
        self.assertEqual(args.model, "gpt-5.6-luna")
        self.assertEqual(args.public_main_sha, "0" * 40)
        self.assertFalse(args.initialize_identity_lock)

    def test_profile_check_parser_requires_explicit_identity_lock_initialization(self):
        args = codex_automation.parse_args(["profile-check", *self._common(), "--initialize-identity-lock"])
        self.assertTrue(args.initialize_identity_lock)

    def test_run_row_parser_requires_manifest_sequence_and_timeout(self):
        args = codex_automation.parse_args(["run-row", *self._common(), "--manifest", "C:/campaign/manifest.jsonl", "--sequence", "7", "--timeout", "360"])
        self.assertEqual(args.command, "run-row")
        self.assertEqual(args.sequence, 7)
        self.assertEqual(args.timeout, 360)


class EvidenceRootBoundaryTests(unittest.TestCase):
    def test_evidence_root_must_stay_outside_repository(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            codex_automation.ensure_external_evidence_root(repo / "evidence")
        with tempfile.TemporaryDirectory() as temp_dir:
            external = pathlib.Path(temp_dir) / "evidence"
            self.assertEqual(codex_automation.ensure_external_evidence_root(external), external.resolve())


class MaterializeProfileTests(unittest.TestCase):
    def test_materialize_profile_bootstraps_disables_unrelated_and_preserves_live_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            live_path = root / "live.toml"
            live_path.write_text(codex_automation.build_profile_text(_live_config(), "S", PSR_SKILL, PSR_MCP), encoding="utf-8")
            before = hashlib.sha256(live_path.read_bytes()).hexdigest().upper()
            probes = iter([
                [{"name": "powershell-reliability", "path": PSR_SKILL}, {"name": "other", "path": "C:/skills/other/SKILL.md"}],
                [{"name": "powershell-reliability", "path": PSR_SKILL}],
            ])
            skill_probe = mock.Mock(side_effect=lambda *_args: next(probes))
            mcp_probe = mock.Mock(return_value=[{"name": "psr_reliability_native", "enabled": True, "transport": {"type": "stdio", "command": PSR_MCP, "args": []}}])
            profile, meta, skills, _ = codex_automation.materialize_profile(
                live_path, "S", pathlib.Path(PSR_SKILL), pathlib.Path(PSR_MCP), pathlib.Path("C:/Codex/codex.exe"),
                temp_parent=root, acl_func=mock.Mock(), skill_probe=skill_probe, mcp_probe=mcp_probe,
            )
            try:
                final_text = (profile / "config.toml").read_text(encoding="utf-8")
                self.assertIn('path = "C:/skills/other/SKILL.md"\nenabled = false', final_text)
                self.assertEqual([item["name"] for item in skills], ["powershell-reliability"])
                self.assertEqual(meta["live_config_sha256"], before)
                self.assertEqual(hashlib.sha256(live_path.read_bytes()).hexdigest().upper(), before)
            finally:
                codex_automation.remove_profile(profile)


class CommandWorkflowTests(unittest.TestCase):
    def test_load_manifest_row_selects_exact_sequence_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "manifest.jsonl"
            path.write_text(json.dumps({"sequence": 1, "arm": "S"}) + "\n" + json.dumps({"sequence": 2, "arm": "M"}) + "\n", encoding="utf-8")
            self.assertEqual(codex_automation.load_manifest_row(path, 2)["arm"], "M")
            path.write_text(json.dumps({"sequence": 2}) + "\n" + json.dumps({"sequence": 2}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                codex_automation.load_manifest_row(path, 2)

    def test_execute_profile_check_cleans_profile_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            profile = root / "secret-profile"; profile.mkdir()
            materialize = mock.Mock(return_value=(profile, {"live_config_sha256": "1" * 64, "profile_fingerprint": "2" * 64, "provider": "codex_local_access", "model": "gpt-5.6-luna", "effort": "max"}, [{"name": "powershell-reliability", "path": PSR_SKILL}], [{"name": "psr_reliability_native", "enabled": True}]))
            args = mock.Mock(arm="S", model="gpt-5.6-luna", public_main_sha="0"*40, initialize_identity_lock=True, live_config=root/"config.toml", codex=root/"codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root/"codex.exe"), skill_path=root/"skill.md", skill_sha256=codex_automation.sha256_file(root/"skill.md"), mcp_path=root/"mcp.exe", mcp_sha256=codex_automation.sha256_file(root/"mcp.exe"), evidence_root=root/"evidence", identity_lock=root/"campaign-identity.json")
            result = codex_automation.execute_profile_check(args, verify_cli=mock.Mock(return_value={"version":"0.148.0-alpha.9","sha256":args.codex_sha256,"path":str(args.codex)}), materialize=materialize)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(profile.exists())
            self.assertTrue((args.evidence_root / "profile-check-S.json").exists())


class ManifestTopologyTests(unittest.TestCase):
    def test_validate_manifest_row_paths_accepts_opaque_runtime_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            runtime_parent = root / "neutral"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                }],
                coordinator, trials=1, seed=7, runtime_parent=runtime_parent,
                token_factory=lambda: next(tokens),
            )[0]
            codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", row)
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

            bad = dict(row); bad["prompt_path"] = str(coordinator / "other.txt")
            with self.assertRaisesRegex(ValueError, "prompt path"):
                codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", bad)

            bad_fixture = dict(row); bad_fixture["fixture_path"] = str(coordinator / "other.json")
            with self.assertRaisesRegex(ValueError, "fixture path"):
                codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", bad_fixture)

            traversal = dict(row); traversal["case_key"] = "../escape"
            with self.assertRaisesRegex(ValueError, "case_key"):
                codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", traversal)

    def test_validate_manifest_row_paths_rejects_linked_fixture_leaf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{"case_id": "X1", "lane": "train", "group": "should_not_trigger", "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {}}],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral", token_factory=lambda: next(tokens),
            )[0]
            fixture = pathlib.Path(row["fixture_path"])
            real_check = codex_automation._path_is_link_or_junction
            with mock.patch.object(codex_automation, "_path_is_link_or_junction", side_effect=lambda path: pathlib.Path(path) == fixture or real_check(path)):
                with self.assertRaisesRegex(ValueError, "fixture.*symlink|junction"):
                    codex_automation.validate_manifest_row_paths(root / "coordinator" / "manifest.jsonl", row)

    def test_validate_runtime_topology_rejects_nested_roots_in_both_directions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            runtime_root = root / "runtime" / ("a" * 32)
            workspace = runtime_root / ("b" * 32)
            coordinator.mkdir()
            runtime_root.mkdir(parents=True)
            codex_automation.validate_runtime_topology(coordinator, runtime_root, workspace)

            nested_runtime = coordinator / ("c" * 32)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                codex_automation.validate_runtime_topology(coordinator, nested_runtime, nested_runtime / ("d" * 32))

            nested_coordinator = runtime_root / "coordinator"
            with self.assertRaisesRegex(ValueError, "disjoint"):
                codex_automation.validate_runtime_topology(nested_coordinator, runtime_root, workspace)


class CampaignIdentityLockTests(unittest.TestCase):
    def test_campaign_identity_uses_explicit_public_main_without_local_main_ref(self):
        cli = {"path": "C:/Codex/codex.exe", "version": "0.148.0-alpha.9", "sha256": "A" * 64}
        meta = {"live_config_sha256": "B" * 64, "provider": "codex_local_access", "model": None, "effort": "max", "approval_policy": "never", "sandbox_mode": "danger-full-access"}
        def git_ref(ref):
            if ref == "HEAD":
                return "1" * 40
            raise RuntimeError("main ref unavailable")
        with mock.patch.object(codex_automation, "_git_rev_parse", side_effect=git_ref):
            payload = codex_automation.campaign_identity_payload(
                cli, pathlib.Path("C:/skill.md"), "C" * 64, pathlib.Path("C:/mcp.exe"), "D" * 64, meta,
                model="gpt-5.6-luna", public_main_sha="2" * 40,
            )
        self.assertEqual(payload["harness_git_head"], "1" * 40)
        self.assertEqual(payload["public_main_sha"], "2" * 40)

    def test_identity_lock_concurrent_initializer_cannot_overwrite_existing_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            lock = root / "campaign-identity.json"
            payload = {"model": "candidate", "harness_git_head": "1" * 40}
            winner = {"model": "other", "harness_git_head": "2" * 40}
            real_open = pathlib.Path.open

            def racing_open(path, mode="r", *args, **kwargs):
                if path == lock and mode == "x":
                    with real_open(lock, "w", encoding="utf-8", newline="\n") as handle:
                        handle.write(json.dumps(winner, sort_keys=True) + "\n")
                    raise FileExistsError(str(lock))
                return real_open(path, mode, *args, **kwargs)

            with mock.patch.object(pathlib.Path, "open", autospec=True, side_effect=racing_open):
                with self.assertRaisesRegex(ValueError, "campaign identity"):
                    codex_automation.verify_or_create_campaign_identity_lock(lock, payload, allow_create=True)
            self.assertEqual(json.loads(lock.read_text(encoding="utf-8")), winner)

    def test_profile_check_creates_lock_and_rejects_cli_identity_drift(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            identity_lock = root / "campaign-identity.json"
            evidence = root / "evidence"
            live_hash = codex_automation.sha256_file(root / "config.toml")

            def materialize_once(*_args):
                profile = pathlib.Path(tempfile.mkdtemp(dir=root, prefix="profile-"))
                meta = {
                    "live_config_sha256": live_hash,
                    "profile_fingerprint": "2" * 64,
                    "provider": "codex_local_access",
                    "model": None,
                    "effort": "max",
                    "approval_policy": "never",
                    "sandbox_mode": "danger-full-access",
                }
                return profile, meta, [{"name": "powershell-reliability", "path": PSR_SKILL}], [{"name": "psr_reliability_native", "enabled": True}]

            args = mock.Mock(
                arm="S", model="gpt-5.6-luna", public_main_sha="0"*40, initialize_identity_lock=True, live_config=root/"config.toml", codex=root/"codex.exe",
                codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root/"codex.exe"),
                skill_path=root/"skill.md", skill_sha256=codex_automation.sha256_file(root/"skill.md"),
                mcp_path=root/"mcp.exe", mcp_sha256=codex_automation.sha256_file(root/"mcp.exe"),
                evidence_root=evidence, identity_lock=identity_lock,
            )
            verify = mock.Mock(return_value={"version":"0.148.0-alpha.9","sha256":args.codex_sha256,"path":str(args.codex)})
            first = codex_automation.execute_profile_check(args, verify_cli=verify, materialize=materialize_once)
            self.assertTrue(identity_lock.exists())
            self.assertEqual(first["campaign_identity_sha256"], codex_automation.sha256_file(identity_lock))
            self.assertEqual(json.loads(identity_lock.read_text(encoding="utf-8"))["model"], "gpt-5.6-luna")

            args.initialize_identity_lock = False
            drift_verify = mock.Mock(return_value={"version":"0.148.0-alpha.9","sha256":"F"*64,"path":str(args.codex)})
            with self.assertRaisesRegex(ValueError, "campaign identity"):
                codex_automation.execute_profile_check(args, verify_cli=drift_verify, materialize=materialize_once)

            identity_lock.unlink()
            with self.assertRaisesRegex(ValueError, "identity lock is required"):
                codex_automation.execute_profile_check(args, verify_cli=verify, materialize=materialize_once)
            self.assertFalse(identity_lock.exists())


class RunRowWorkflowTests(unittest.TestCase):
    def _prepared_run(self, root, post_condition=None):
        coordinator = root / "coordinator"
        tokens = iter(["1" * 32, "2" * 32, "3" * 32])
        rows = codex_automation.routing_eval.prepare_campaign(
            [{
                "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                "post_condition": post_condition or {"kind": "none"},
            }],
            coordinator, trials=1, seed=7, runtime_parent=root / "neutral",
            token_factory=lambda: next(tokens),
        )
        row = next(item for item in rows if item["arm"] == "M")
        for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
            (root / name).write_bytes(name.encode())
        profile = root / "secret-profile"; profile.mkdir()
        live_hash = codex_automation.sha256_file(root / "config.toml")
        meta = {"live_config_sha256": live_hash, "profile_fingerprint": "2" * 64, "provider": "codex_local_access", "model": "gpt-5.6-luna", "effort": "max", "approval_policy": "never", "sandbox_mode": "danger-full-access"}
        materialize = mock.Mock(return_value=(profile, meta, [], [{"name": "psr_reliability_native", "enabled": True}]))
        args = mock.Mock(arm="M", model="gpt-5.6-luna", public_main_sha="0" * 40, live_config=root / "config.toml", codex=root / "codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root / "codex.exe"), skill_path=root / "skill.md", skill_sha256=codex_automation.sha256_file(root / "skill.md"), mcp_path=root / "mcp.exe", mcp_sha256=codex_automation.sha256_file(root / "mcp.exe"), evidence_root=coordinator / "row-evidence", identity_lock=coordinator / "campaign-identity.json", manifest=coordinator / "manifest.jsonl", sequence=row["sequence"], timeout=360)
        cli_identity = {"version": "0.148.0-alpha.9", "sha256": args.codex_sha256, "path": str(args.codex)}
        identity = codex_automation.campaign_identity_payload(cli_identity, args.skill_path, args.skill_sha256, args.mcp_path, args.mcp_sha256, meta, model=args.model, public_main_sha=args.public_main_sha)
        codex_automation.verify_or_create_campaign_identity_lock(args.identity_lock, identity, allow_create=True)
        return row, args, profile, materialize, cli_identity

    def test_materialize_row_workspace_creates_only_active_fixture_and_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            runtime_parent = root / "neutral"
            content = "@echo off\r\nexit /b 0\r\n"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"},
                    "files": {"helper.cmd": content, "nested/input.txt": "same\n"},
                }],
                coordinator, trials=1, seed=7, runtime_parent=runtime_parent,
                token_factory=lambda: next(tokens),
            )[0]
            runtime_root = pathlib.Path(row["runtime_root"])
            self.assertEqual(list(runtime_root.iterdir()), [])
            workspace = codex_automation.materialize_row_workspace(row)
            self.assertEqual(list(runtime_root.iterdir()), [workspace])
            self.assertEqual((workspace / "helper.cmd").read_bytes(), content.encode("utf-8"))
            self.assertEqual(codex_automation.workspace_fixture_sha256(workspace), row["fixture_sha256"])

    def test_materialize_row_workspace_rejects_tampered_workspace_outside_runtime_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"},
                    "files": {"safe.txt": "safe"},
                }],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            outside = root / "unrelated" / ("e" * 32)
            tampered = dict(row)
            tampered["workspace"] = str(outside)
            tampered["workspace_sha256"] = codex_automation.routing_eval.workspace_identity(str(outside))
            with self.assertRaisesRegex(ValueError, "direct child"):
                codex_automation.materialize_row_workspace(tampered)
            self.assertFalse(outside.exists())
            self.assertEqual(list(pathlib.Path(row["runtime_root"]).iterdir()), [])

    def test_materialize_row_workspace_rejects_tampered_parent_escape_before_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"},
                    "files": {"safe.txt": "safe"},
                }],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            fixture_path = pathlib.Path(row["fixture_path"])
            fixture_path.write_text(json.dumps({"../escape.txt": "owned"}) + "\n", encoding="utf-8")
            escape = pathlib.Path(row["runtime_root"]) / "escape.txt"
            with self.assertRaisesRegex(ValueError, "fixture path"):
                codex_automation.materialize_row_workspace(row)
            self.assertFalse(escape.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_materialize_row_workspace_does_not_delete_workspace_won_by_race(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                }],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            workspace = pathlib.Path(row["workspace"])
            marker = workspace / "preexisting.txt"
            real_mkdir = pathlib.Path.mkdir

            def race_mkdir(path, mode=0o777, parents=False, exist_ok=False):
                if path == workspace:
                    real_mkdir(path, mode=mode, parents=True, exist_ok=True)
                    marker.write_text("preserve", encoding="utf-8")
                    if not exist_ok:
                        raise FileExistsError(str(path))
                    return None
                return real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

            with mock.patch.object(pathlib.Path, "mkdir", autospec=True, side_effect=race_mkdir):
                with self.assertRaises(FileExistsError):
                    codex_automation.materialize_row_workspace(row)
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_materialize_row_workspace_rejects_stale_peer_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                }],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            runtime_root = pathlib.Path(row["runtime_root"])
            (runtime_root / ("f" * 32)).mkdir()
            with self.assertRaisesRegex(RuntimeError, "runtime root.*empty"):
                codex_automation.materialize_row_workspace(row)
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_materialize_row_workspace_rejects_link_before_resolving_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{"case_id": "X1", "lane": "train", "group": "should_not_trigger", "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {}}],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            raw_runtime = pathlib.Path(row["runtime_root"])
            real_resolve = pathlib.Path.resolve
            real_is_symlink = pathlib.Path.is_symlink
            def fake_resolve(path, strict=False):
                if path == raw_runtime:
                    raise AssertionError("link must be rejected before resolve")
                return real_resolve(path, strict=strict)
            def fake_is_symlink(path):
                if path == raw_runtime:
                    return True
                return real_is_symlink(path)
            with mock.patch.object(pathlib.Path, "resolve", autospec=True, side_effect=fake_resolve), mock.patch.object(pathlib.Path, "is_symlink", autospec=True, side_effect=fake_is_symlink):
                with self.assertRaisesRegex(ValueError, "symlink|junction"):
                    codex_automation.materialize_row_workspace(row)

    def test_materialize_row_workspace_rejects_symlinked_runtime_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            row = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                }],
                root / "coordinator", trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )[0]
            write_fixture = mock.Mock()
            with mock.patch.object(pathlib.Path, "is_symlink", return_value=True), mock.patch.object(codex_automation.routing_eval, "_write_fixture", write_fixture):
                with self.assertRaisesRegex(ValueError, "symlink|junction"):
                    codex_automation.materialize_row_workspace(row)
            write_fixture.assert_not_called()

    def test_remove_runtime_workspace_fails_closed_on_dangling_symlink(self):
        workspace = pathlib.Path("C:/opaque/dangling")
        with mock.patch.object(pathlib.Path, "exists", return_value=False), \
             mock.patch.object(pathlib.Path, "is_symlink", return_value=True), \
             mock.patch.object(pathlib.Path, "unlink") as unlink:
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                codex_automation.remove_runtime_workspace(workspace)
        unlink.assert_called_once_with()

    def test_workspace_fixture_sha256_matches_prepared_text_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            (workspace / "nested").mkdir()
            (workspace / "a.txt").write_text("A\n", encoding="utf-8", newline="\n")
            (workspace / "nested" / "b.ps1").write_text("Write-Output B\n", encoding="utf-8", newline="\n")
            expected = codex_automation.routing_eval._fixture_sha256({"a.txt": "A\n", "nested/b.ps1": "Write-Output B\n"})
            self.assertEqual(codex_automation.workspace_fixture_sha256(workspace), expected)

    def test_workspace_fixture_sha256_preserves_crlf_fixture_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            content = "@echo off\r\nexit /b 0\r\n"
            (workspace / "helper.cmd").write_bytes(content.encode("utf-8"))
            expected = codex_automation.routing_eval._fixture_sha256({"helper.cmd": content})
            self.assertEqual(codex_automation.workspace_fixture_sha256(workspace), expected)

    def test_execute_run_row_rejects_preexisting_target_workspace_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            row, args, _profile, materialize, cli_identity = self._prepared_run(root)
            workspace = pathlib.Path(row["workspace"])
            workspace.mkdir()
            marker = workspace / "unexpected.txt"
            marker.write_text("preserve", encoding="utf-8")
            process = mock.Mock()
            with self.assertRaisesRegex(RuntimeError, "runtime root.*empty"):
                codex_automation.execute_run_row(
                    args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                    process_runner=process,
                )
            materialize.assert_not_called()
            process.assert_not_called()
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_execute_run_row_rejects_mutated_fixture_before_profile_or_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            rows = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                    "post_condition": {"kind": "none"},
                }],
                coordinator, trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )
            row = next(item for item in rows if item["arm"] == "M")
            pathlib.Path(row["fixture_path"]).write_text(json.dumps({"stale.txt": "stale"}) + "\n", encoding="utf-8")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            args = mock.Mock(arm="M", model="gpt-5.6-luna", public_main_sha="0" * 40, live_config=root / "config.toml", codex=root / "codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root / "codex.exe"), skill_path=root / "skill.md", skill_sha256=codex_automation.sha256_file(root / "skill.md"), mcp_path=root / "mcp.exe", mcp_sha256=codex_automation.sha256_file(root / "mcp.exe"), evidence_root=coordinator / "row-evidence", identity_lock=coordinator / "campaign-identity.json", manifest=coordinator / "manifest.jsonl", sequence=row["sequence"], timeout=360)
            materialize = mock.Mock()
            process = mock.Mock()
            with self.assertRaisesRegex(ValueError, "fixture SHA256 mismatch"):
                codex_automation.execute_run_row(args, verify_cli=mock.Mock(return_value={"version": "0.148.0-alpha.9", "sha256": args.codex_sha256, "path": str(args.codex)}), materialize=materialize, process_runner=process)
            materialize.assert_not_called()
            process.assert_not_called()
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_execute_run_row_preserves_task_failure_and_cleans_workspace_and_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            rows = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                    "post_condition": {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]},
                }],
                coordinator, trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )
            row = next(item for item in rows if item["arm"] == "M")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            profile = root / "secret-profile"; profile.mkdir()
            live_hash = codex_automation.sha256_file(root / "config.toml")
            meta = {"live_config_sha256": live_hash, "profile_fingerprint": "2" * 64, "provider": "codex_local_access", "model": "gpt-5.6-luna", "effort": "max", "approval_policy": "never", "sandbox_mode": "danger-full-access"}
            materialize = mock.Mock(return_value=(profile, meta, [], [{"name": "psr_reliability_native", "enabled": True}]))
            observed = {}
            def process_runner(_exe, workspace, _profile, _prompt, _stdout, _stderr, _timeout, model=None):
                observed["workspace"] = workspace
                self.assertTrue(workspace.is_dir())
                self.assertEqual(list(workspace.parent.iterdir()), [workspace])
                return {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 1}
            parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 1, "incomplete_native_command_count": 0, "mcp_call_count": 0, "incomplete_mcp_call_count": 0, "reliability_mcp_call_count": 0, "commands": [], "mcp_calls": [], "truncated_jsonl_tail": False, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
            args = mock.Mock(arm="M", model="gpt-5.6-luna", public_main_sha="0" * 40, live_config=root / "config.toml", codex=root / "codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root / "codex.exe"), skill_path=root / "skill.md", skill_sha256=codex_automation.sha256_file(root / "skill.md"), mcp_path=root / "mcp.exe", mcp_sha256=codex_automation.sha256_file(root / "mcp.exe"), evidence_root=coordinator / "row-evidence", identity_lock=coordinator / "campaign-identity.json", manifest=coordinator / "manifest.jsonl", sequence=row["sequence"], timeout=360)
            cli_identity = {"version": "0.148.0-alpha.9", "sha256": args.codex_sha256, "path": str(args.codex)}
            identity = codex_automation.campaign_identity_payload(cli_identity, args.skill_path, args.skill_sha256, args.mcp_path, args.mcp_sha256, meta, model=args.model, public_main_sha=args.public_main_sha)
            codex_automation.verify_or_create_campaign_identity_lock(args.identity_lock, identity, allow_create=True)
            receipt = codex_automation.execute_run_row(args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize, process_runner=process_runner, json_parser=mock.Mock(return_value=parsed))
            self.assertFalse(receipt["post_condition_passed"])
            self.assertTrue(receipt["workspace_cleanup_ok"])
            self.assertTrue(receipt["profile_cleanup_ok"])
            self.assertTrue(receipt["cleanup_ok"])
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())
            self.assertEqual(list(pathlib.Path(row["runtime_root"]).iterdir()), [])
            self.assertTrue((args.evidence_root / f"{row['sequence']:04d}-{row['case_key']}-M" / "receipt.json").exists())

    def test_execute_run_row_fails_cleanup_when_runtime_root_has_sibling_after_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            row, args, _profile, materialize, cli_identity = self._prepared_run(root)
            sibling = pathlib.Path(row["runtime_root"]) / "unexpected.txt"
            parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 0, "incomplete_native_command_count": 0, "mcp_call_count": 0, "incomplete_mcp_call_count": 0, "reliability_mcp_call_count": 0, "commands": [], "mcp_calls": [], "truncated_jsonl_tail": False, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
            def process_runner(_exe, workspace, _profile, _prompt, _stdout, _stderr, _timeout, model=None):
                sibling.write_text("preserve", encoding="utf-8")
                return {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 1}
            with self.assertRaisesRegex(RuntimeError, "runtime root.*empty|row cleanup failed"):
                codex_automation.execute_run_row(
                    args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                    process_runner=process_runner, json_parser=mock.Mock(return_value=parsed),
                )
            self.assertTrue(sibling.is_file())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_execute_run_row_cleans_workspace_and_profile_when_parser_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            post = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}
            row, args, profile, materialize, cli_identity = self._prepared_run(root, post_condition=post)
            def process_runner(_exe, workspace, _profile, _prompt, _stdout, _stderr, _timeout, model=None):
                (workspace / "result.txt").write_text("READY\n", encoding="utf-8", newline="\n")
                return {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 1}
            evaluate = mock.Mock(side_effect=codex_automation.evaluate_manifest_row)
            with mock.patch.object(codex_automation, "evaluate_manifest_row", evaluate):
                with self.assertRaisesRegex(ValueError, "malformed"):
                    codex_automation.execute_run_row(
                        args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                        process_runner=process_runner, json_parser=mock.Mock(side_effect=ValueError("malformed CLI JSONL")),
                    )
            evaluate.assert_called_once()
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())
            self.assertEqual(list(pathlib.Path(row["runtime_root"]).iterdir()), [])

    def test_execute_run_row_cleans_workspace_and_profile_when_process_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            post = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}
            row, args, profile, materialize, cli_identity = self._prepared_run(root, post_condition=post)
            def process_runner(_exe, workspace, _profile, _prompt, _stdout, _stderr, _timeout, model=None):
                (workspace / "result.txt").write_text("READY\n", encoding="utf-8", newline="\n")
                raise RuntimeError("launch failed")
            evaluate = mock.Mock(side_effect=codex_automation.evaluate_manifest_row)
            with mock.patch.object(codex_automation, "evaluate_manifest_row", evaluate):
                with self.assertRaisesRegex(RuntimeError, "launch failed"):
                    codex_automation.execute_run_row(
                        args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                        process_runner=process_runner,
                    )
            evaluate.assert_called_once()
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())
            self.assertEqual(list(pathlib.Path(row["runtime_root"]).iterdir()), [])

    def test_execute_run_row_timeout_evaluates_post_condition_before_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            post = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}
            row, args, profile, materialize, cli_identity = self._prepared_run(root, post_condition=post)
            def process_runner(_exe, workspace, _profile, _prompt, _stdout, _stderr, _timeout, model=None):
                (workspace / "result.txt").write_text("READY\n", encoding="utf-8", newline="\n")
                return {"exit_code": 124, "timed_out": True, "termination_reason": "timeout", "task_wall_clock_ms": 10}
            parsed = {"thread_id": "t", "turn_status": "unknown", "native_command_count": 1, "incomplete_native_command_count": 1, "mcp_call_count": 0, "incomplete_mcp_call_count": 0, "reliability_mcp_call_count": 0, "commands": [], "mcp_calls": [], "truncated_jsonl_tail": True, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": None, "errors": []}
            receipt = codex_automation.execute_run_row(
                args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                process_runner=process_runner, json_parser=mock.Mock(return_value=parsed),
            )
            self.assertTrue(receipt["timed_out"])
            self.assertTrue(receipt["post_condition_passed"])
            self.assertTrue(receipt["cleanup_ok"])
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_execute_run_row_marks_bounded_protocol_contamination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            row, args, profile, materialize, cli_identity = self._prepared_run(root)
            coordinator = args.manifest.parent
            process = mock.Mock(return_value={"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 1})
            parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 1, "incomplete_native_command_count": 0, "mcp_call_count": 0, "incomplete_mcp_call_count": 0, "reliability_mcp_call_count": 0, "commands": [{"id": "c1", "type": "command_execution", "command": f"Get-ChildItem '{coordinator}'", "exit_code": 0}], "mcp_calls": [], "truncated_jsonl_tail": False, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
            with self.assertRaisesRegex(RuntimeError, "protocol contamination"):
                codex_automation.execute_run_row(
                    args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                    process_runner=process, json_parser=mock.Mock(return_value=parsed),
                )
            receipt_path = args.evidence_root / f"{row['sequence']:04d}-{row['case_key']}-M" / "receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(receipt["protocol_contamination"])
            self.assertEqual([item["kind"] for item in receipt["contamination_evidence"]], ["coordinator_access"])
            evidence_text = json.dumps(receipt["contamination_evidence"])
            self.assertNotIn(str(coordinator), evidence_text)
            self.assertTrue(receipt["cleanup_ok"])
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_execute_run_row_rejects_identity_drift_and_cleans_workspace_before_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            rows = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                    "post_condition": {"kind": "none"},
                }],
                coordinator, trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )
            row = next(item for item in rows if item["arm"] == "M")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            profile = root / "secret-profile"; profile.mkdir()
            live_hash = codex_automation.sha256_file(root / "config.toml")
            meta = {"live_config_sha256": live_hash, "profile_fingerprint": "2" * 64, "provider": "codex_local_access", "model": "gpt-5.6-luna", "effort": "max", "approval_policy": "never", "sandbox_mode": "danger-full-access"}
            materialize = mock.Mock(return_value=(profile, meta, [], [{"name": "psr_reliability_native", "enabled": True}]))
            cli_identity = {"version": "0.148.0-alpha.9", "sha256": codex_automation.sha256_file(root / "codex.exe"), "path": str(root / "codex.exe")}
            identity_lock = coordinator / "campaign-identity.json"
            drifted = codex_automation.campaign_identity_payload(cli_identity, root / "skill.md", codex_automation.sha256_file(root / "skill.md"), root / "mcp.exe", codex_automation.sha256_file(root / "mcp.exe"), meta, model="gpt-5.6-luna", public_main_sha="0" * 40)
            drifted["model"] = "different-model"
            codex_automation.verify_or_create_campaign_identity_lock(identity_lock, drifted, allow_create=True)
            args = mock.Mock(arm="M", model="gpt-5.6-luna", public_main_sha="0" * 40, live_config=root / "config.toml", codex=root / "codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=cli_identity["sha256"], skill_path=root / "skill.md", skill_sha256=codex_automation.sha256_file(root / "skill.md"), mcp_path=root / "mcp.exe", mcp_sha256=codex_automation.sha256_file(root / "mcp.exe"), evidence_root=coordinator / "row-evidence", identity_lock=identity_lock, manifest=coordinator / "manifest.jsonl", sequence=row["sequence"], timeout=360)
            process = mock.Mock()
            with self.assertRaisesRegex(ValueError, "campaign identity"):
                codex_automation.execute_run_row(args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize, process_runner=process)
            process.assert_not_called()
            self.assertFalse(profile.exists())
            self.assertFalse(pathlib.Path(row["workspace"]).exists())
            self.assertFalse((args.evidence_root / f"{row['sequence']:04d}-{row['case_key']}-M").exists())

    def test_execute_run_row_rejects_evidence_root_inside_runtime_root_before_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            row, args, _profile, materialize, cli_identity = self._prepared_run(root)
            args.evidence_root = pathlib.Path(row["runtime_root"]) / "evidence"
            process = mock.Mock(return_value={"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 1})
            parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 0, "incomplete_native_command_count": 0, "mcp_call_count": 0, "incomplete_mcp_call_count": 0, "reliability_mcp_call_count": 0, "commands": [], "mcp_calls": [], "truncated_jsonl_tail": False, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
            with self.assertRaisesRegex(ValueError, "evidence root.*runtime"):
                codex_automation.execute_run_row(
                    args, verify_cli=mock.Mock(return_value=cli_identity), materialize=materialize,
                    process_runner=process, json_parser=mock.Mock(return_value=parsed),
                )
            process.assert_not_called()
            self.assertFalse(pathlib.Path(row["workspace"]).exists())

    def test_execute_run_row_rejects_evidence_root_inside_workspace_before_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            rows = codex_automation.routing_eval.prepare_campaign(
                [{
                    "case_id": "X1", "lane": "train", "group": "should_not_trigger",
                    "prompt": "do task", "boundary_detector": {"kind": "none"}, "files": {},
                    "post_condition": {"kind": "none"},
                }],
                coordinator, trials=1, seed=7, runtime_parent=root / "neutral",
                token_factory=lambda: next(tokens),
            )
            row = next(item for item in rows if item["arm"] == "M")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            args = mock.Mock(
                arm="M", model="gpt-5.6-luna", public_main_sha="0" * 40,
                live_config=root / "config.toml", codex=root / "codex.exe",
                codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root / "codex.exe"),
                skill_path=root / "skill.md", skill_sha256=codex_automation.sha256_file(root / "skill.md"),
                mcp_path=root / "mcp.exe", mcp_sha256=codex_automation.sha256_file(root / "mcp.exe"),
                evidence_root=pathlib.Path(row["workspace"]) / "evidence",
                identity_lock=coordinator / "campaign-identity.json",
                manifest=coordinator / "manifest.jsonl", sequence=row["sequence"], timeout=360,
            )
            with self.assertRaisesRegex(ValueError, "evidence root.*workspace"):
                codex_automation.execute_run_row(
                    args,
                    verify_cli=mock.Mock(return_value={"version": "0.148.0-alpha.9", "sha256": args.codex_sha256, "path": str(args.codex)}),
                    materialize=mock.Mock(), process_runner=mock.Mock(),
                )
            self.assertFalse(pathlib.Path(row["workspace"]).exists())




class OperatorArtifactTests(unittest.TestCase):
    def test_launcher_is_thin_and_runbook_preserves_desktop_authority(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        launcher = repo / "scripts" / "run-routing-automation.ps1"
        runbook = repo / "docs" / "runbooks" / "routing-eval-cli-automation.md"
        self.assertTrue(launcher.exists())
        self.assertTrue(runbook.exists())
        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn("ValueFromRemainingArguments", launcher_text)
        self.assertNotIn("Invoke-Expression", launcher_text)
        runbook_text = runbook.read_text(encoding="utf-8")
        for phrase in ("profile-check", "run-row", "screening", "Windows Codex Desktop", "concurrency is 1", "--runtime-parent", "opaque", "leakage canary", "Before any fresh scored CLI campaign"):
            self.assertIn(phrase, runbook_text)
        desktop_runbook = (repo / "docs" / "runbooks" / "routing-eval-desktop.md").read_text(encoding="utf-8")
        self.assertIn("prompt_sha256", desktop_runbook)
        self.assertIn("hashlib.sha256", desktop_runbook)

    def test_verify_local_runs_and_compiles_automation_tests(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        text = (repo / "scripts" / "verify-local.ps1").read_text(encoding="utf-8")
        self.assertIn("test_codex_automation.py", text)
        self.assertIn("codex_automation.py", text)
