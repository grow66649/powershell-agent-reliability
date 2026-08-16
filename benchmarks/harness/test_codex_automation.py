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
        argv = codex_automation.codex_argv(pathlib.Path("C:/Codex/codex.exe"), pathlib.Path("C:/workspace"))
        self.assertEqual(argv, ["C:/Codex/codex.exe", "exec", "--ephemeral", "--json", "-C", "C:/workspace", "-"])
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
                root / "stdout.jsonl", root / "stderr.log", 12, popen_factory=popen, tree_killer=killer, clock=clock,
            )
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["task_wall_clock_ms"], 125)
        self.assertEqual(result["termination_reason"], "timeout")
        killer.assert_called_once_with(fake)
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

    def test_parse_cli_jsonl_counts_completed_command_mcp_and_exact_usage(self):
        rows = [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": "cmd.exe /c exit 0", "exit_code": 0, "status": "completed"}},
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
        self.assertEqual(parsed["tokens"]["input_tokens"], 100)
        self.assertIsNone(parsed["tokens"]["total_tokens"])
        self.assertEqual(parsed["final_message"], "READY")

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

    def test_normalized_receipt_combines_process_catalog_tool_tokens_and_post_condition(self):
        manifest = {"case_key": "X1-T01", "case_id": "X1", "trial_id": "T01", "arm": "S", "sequence": 1, "prompt_sha256": "A" * 64, "workspace_sha256": "B" * 64, "fixture_sha256": "C" * 64}
        process = {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit", "task_wall_clock_ms": 321}
        parsed = {"thread_id": "t", "turn_status": "completed", "native_command_count": 2, "mcp_call_count": 1, "reliability_mcp_call_count": 1, "tokens": {name: None for name in codex_automation.TOKEN_FIELDS}, "final_message": "done", "errors": []}
        parsed["tokens"]["input_tokens"] = 12
        profile = {"cli_version": "0.148.0-alpha.9", "cli_sha256": "D" * 64, "profile_fingerprint": "E" * 64, "mcp_sha256": "F" * 64}
        receipt = codex_automation.normalized_execution_receipt(manifest, process, parsed, profile, [{"name": "powershell-reliability", "path": PSR_SKILL}], {"passed": True, "source": "evaluator_workspace"}, True)
        self.assertEqual(receipt["post_condition_passed"], True)
        self.assertEqual(receipt["reliability_mcp_call_count"], 1)
        self.assertEqual(receipt["input_tokens"], 12)
        self.assertEqual(receipt["task_wall_clock_ms"], 321)
        self.assertEqual(receipt["skill_catalog"], ["powershell-reliability"])
        self.assertTrue(receipt["cleanup_ok"])


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
        ]

    def test_profile_check_parser_requires_runtime_identity_and_arm(self):
        args = codex_automation.parse_args(["profile-check", *self._common()])
        self.assertEqual(args.command, "profile-check")
        self.assertEqual(args.arm, "S")
        self.assertEqual(args.codex_version, "0.148.0-alpha.9")

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
            args = mock.Mock(arm="S", live_config=root/"config.toml", codex=root/"codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root/"codex.exe"), skill_path=root/"skill.md", skill_sha256=codex_automation.sha256_file(root/"skill.md"), mcp_path=root/"mcp.exe", mcp_sha256=codex_automation.sha256_file(root/"mcp.exe"), evidence_root=root/"evidence")
            result = codex_automation.execute_profile_check(args, verify_cli=mock.Mock(return_value={"version":"0.148.0-alpha.9","sha256":args.codex_sha256,"path":str(args.codex)}), materialize=materialize)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(profile.exists())
            self.assertTrue((args.evidence_root / "profile-check-S.json").exists())


class ManifestTopologyTests(unittest.TestCase):
    def test_validate_manifest_row_paths_requires_campaign_prompt_and_workspace_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            manifest = root / "manifest.jsonl"
            row = {"case_key": "X1-T01", "arm": "M", "prompt_path": str(root/"prompts"/"X1-T01.txt"), "workspace": str(root/"workspaces"/"M"/"X1-T01")}
            codex_automation.validate_manifest_row_paths(manifest, row)
            bad = dict(row); bad["workspace"] = str(root/".."/"elsewhere")
            with self.assertRaisesRegex(ValueError, "workspace path"):
                codex_automation.validate_manifest_row_paths(manifest, bad)
            bad = dict(row); bad["prompt_path"] = str(root/"other.txt")
            with self.assertRaisesRegex(ValueError, "prompt path"):
                codex_automation.validate_manifest_row_paths(manifest, bad)
            traversal = dict(row); traversal["case_key"] = "../escape"
            traversal["prompt_path"] = str(root / "escape.txt")
            traversal["workspace"] = str(root / "workspaces" / "escape")
            with self.assertRaisesRegex(ValueError, "case_key"):
                codex_automation.validate_manifest_row_paths(manifest, traversal)


class RunRowWorkflowTests(unittest.TestCase):
    def test_workspace_fixture_sha256_matches_prepared_text_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            (workspace / "nested").mkdir()
            (workspace / "a.txt").write_text("A\n", encoding="utf-8", newline="\n")
            (workspace / "nested" / "b.ps1").write_text("Write-Output B\n", encoding="utf-8", newline="\n")
            expected = codex_automation.routing_eval._fixture_sha256({"a.txt": "A\n", "nested/b.ps1": "Write-Output B\n"})
            self.assertEqual(codex_automation.workspace_fixture_sha256(workspace), expected)

    def test_execute_run_row_rejects_mutated_fixture_before_profile_or_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "workspaces" / "M" / "X1-T01"; workspace.mkdir(parents=True)
            (workspace / "stale.txt").write_text("stale", encoding="utf-8")
            prompt = root / "prompts" / "X1-T01.txt"; prompt.parent.mkdir(); prompt.write_text("do task\n", encoding="utf-8", newline="\n")
            manifest = root / "manifest.jsonl"
            row = {"sequence": 1, "case_key": "X1-T01", "case_id": "X1", "trial_id": "T01", "arm": "M", "prompt_path": str(prompt), "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest().upper(), "workspace": str(workspace), "workspace_sha256": codex_automation.routing_eval.workspace_identity(str(workspace)), "fixture_sha256": codex_automation.routing_eval._fixture_sha256({}), "post_condition": {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}}
            manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            args = mock.Mock(arm="M", live_config=root/"config.toml", codex=root/"codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root/"codex.exe"), skill_path=root/"skill.md", skill_sha256=codex_automation.sha256_file(root/"skill.md"), mcp_path=root/"mcp.exe", mcp_sha256=codex_automation.sha256_file(root/"mcp.exe"), evidence_root=root/"evidence", manifest=manifest, sequence=1, timeout=360)
            materialize = mock.Mock()
            process = mock.Mock()
            with self.assertRaisesRegex(ValueError, "fixture SHA256 mismatch"):
                codex_automation.execute_run_row(args, verify_cli=mock.Mock(), materialize=materialize, process_runner=process)
            materialize.assert_not_called()
            process.assert_not_called()

    def test_execute_run_row_preserves_task_failure_as_receipt_and_cleans_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "workspaces" / "M" / "X1-T01"; workspace.mkdir(parents=True)
            prompt = root / "prompts" / "X1-T01.txt"; prompt.parent.mkdir(); prompt.write_text("do task\n", encoding="utf-8", newline="\n")
            manifest = root / "manifest.jsonl"
            row = {"sequence": 1, "case_key": "X1-T01", "case_id": "X1", "trial_id": "T01", "arm": "M", "prompt_path": str(prompt), "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest().upper(), "workspace": str(workspace), "workspace_sha256": codex_automation.routing_eval.workspace_identity(str(workspace)), "fixture_sha256": codex_automation.routing_eval._fixture_sha256({}), "post_condition": {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}}
            manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
            for name in ("codex.exe", "skill.md", "mcp.exe", "config.toml"):
                (root / name).write_bytes(name.encode())
            profile = root / "secret-profile"; profile.mkdir()
            live_hash = codex_automation.sha256_file(root/"config.toml")
            materialize = mock.Mock(return_value=(profile, {"live_config_sha256":live_hash,"profile_fingerprint":"2"*64,"provider":"codex_local_access","model":"gpt-5.6-luna","effort":"max"}, [], [{"name":"psr_reliability_native","enabled":True}]))
            process = mock.Mock(return_value={"exit_code":0,"timed_out":False,"termination_reason":"process_exit"})
            parsed = {"thread_id":"t","turn_status":"completed","native_command_count":1,"mcp_call_count":0,"reliability_mcp_call_count":0,"tokens":{name:None for name in codex_automation.TOKEN_FIELDS},"final_message":"done","errors":[]}
            args = mock.Mock(arm="M", live_config=root/"config.toml", codex=root/"codex.exe", codex_version="0.148.0-alpha.9", codex_sha256=codex_automation.sha256_file(root/"codex.exe"), skill_path=root/"skill.md", skill_sha256=codex_automation.sha256_file(root/"skill.md"), mcp_path=root/"mcp.exe", mcp_sha256=codex_automation.sha256_file(root/"mcp.exe"), evidence_root=root/"evidence", manifest=manifest, sequence=1, timeout=360)
            receipt = codex_automation.execute_run_row(args, verify_cli=mock.Mock(return_value={"version":"0.148.0-alpha.9","sha256":args.codex_sha256,"path":str(args.codex)}), materialize=materialize, process_runner=process, json_parser=mock.Mock(return_value=parsed))
            self.assertFalse(receipt["post_condition_passed"])
            self.assertFalse(profile.exists())
            self.assertTrue((args.evidence_root / "0001-X1-T01-M" / "receipt.json").exists())


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
        for phrase in ("profile-check", "run-row", "screening", "Windows Codex Desktop", "concurrency is 1"):
            self.assertIn(phrase, runbook_text)
