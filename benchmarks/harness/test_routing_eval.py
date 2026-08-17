import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import routing_eval


def _case(case_id="R01", group="should_trigger", lane="train"):
    return {
        "case_id": case_id,
        "lane": lane,
        "group": group,
        "title": "paired fixture",
        "prompt": "Do the task.\n[CASE-ID: {case_key}]",
        "files": {
            "task.ps1": "exit 7\n",
            "nested/input.txt": "same fixture\n",
        },
        "expected_first_command_fragment": ("pwsh.exe -NoProfile -File .\\task.ps1" if group == "should_trigger" else None),
        "boundary_detector": {"kind": "first_command_nonzero"},
    }


def _pair_positions(rows, trial_id):
    by_case = {}
    for index, row in enumerate(row for row in rows if row["trial_id"] == trial_id):
        by_case.setdefault(row["case_id"], []).append((index, row["arm"]))
    return by_case


class RoutingEvalPrepareTests(unittest.TestCase):
    def test_prepare_campaign_creates_matched_s_m_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            runtime_parent = root / "runtime-parent"
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            rows = routing_eval.prepare_campaign(
                [_case()], coordinator, trials=1, seed=7,
                runtime_parent=runtime_parent, token_factory=lambda: next(tokens),
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["arm"] for row in rows}, {"S", "M"})
            by_arm = {row["arm"]: row for row in rows}
            self.assertEqual(by_arm["S"]["prompt_sha256"], by_arm["M"]["prompt_sha256"])
            self.assertEqual(by_arm["S"]["fixture_sha256"], by_arm["M"]["fixture_sha256"])
            self.assertNotEqual(by_arm["S"]["workspace_sha256"], by_arm["M"]["workspace_sha256"])
            self.assertEqual(by_arm["S"]["prompt_path"], by_arm["M"]["prompt_path"])
            self.assertEqual(by_arm["S"]["fixture_path"], by_arm["M"]["fixture_path"])
            prompt = pathlib.Path(by_arm["S"]["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("[CASE-ID: R01-T01]", prompt)
            self.assertEqual(json.loads(pathlib.Path(by_arm["S"]["fixture_path"]).read_text(encoding="utf-8")), _case()["files"])
            runtime_root = pathlib.Path(rows[0]["runtime_root"])
            expected_runtime_root = runtime_parent / ("1" * 32)
            self.assertTrue(runtime_root.is_dir())
            self.assertEqual(runtime_root.resolve(strict=False), expected_runtime_root.resolve(strict=False))
            self.assertEqual(list(runtime_root.iterdir()), [])
            self.assertEqual(
                {pathlib.Path(row["workspace"]).parent.resolve(strict=False) for row in rows},
                {runtime_root.resolve(strict=False)},
            )
            self.assertEqual({pathlib.Path(row["workspace"]).name for row in rows}, {"2" * 32, "3" * 32})
            self.assertTrue(all(not pathlib.Path(row["workspace"]).exists() for row in rows))
            for forbidden in ("powershell-reliability", "Reliability MCP", "arm S", "arm M"):
                self.assertNotIn(forbidden.lower(), prompt.lower())
            required = {
                "case_key", "case_id", "trial_id", "lane", "group", "arm", "sequence",
                "prompt_path", "prompt_sha256", "fixture_path", "runtime_root", "runtime_root_sha256",
                "workspace", "workspace_sha256", "fixture_sha256",
                "expected_first_command_fragment", "boundary_detector",
            }
            self.assertTrue(required.issubset(by_arm["S"]))

    def test_prepare_campaign_rejects_linked_prompt_leaf_before_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            prompt_path = coordinator / "prompts" / "R01-T01.txt"
            prompt_path.parent.mkdir(parents=True)
            prompt_path.write_text("preserve", encoding="utf-8")
            tokens = iter(["1" * 32, "2" * 32, "3" * 32])
            real_is_symlink = pathlib.Path.is_symlink
            def fake_is_symlink(path):
                return path == prompt_path or real_is_symlink(path)
            with mock.patch.object(pathlib.Path, "is_symlink", autospec=True, side_effect=fake_is_symlink):
                with self.assertRaisesRegex(ValueError, "prompt.*symlink|junction"):
                    routing_eval.prepare_campaign(
                        [_case()], coordinator, trials=1, seed=7,
                        runtime_parent=root / "runtime-parent", token_factory=lambda: next(tokens),
                    )
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), "preserve")

    def test_prepare_campaign_rejects_linked_runtime_root_before_resolve(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            runtime_parent = root / "neutral"
            runtime_parent.mkdir()
            raw_runtime_root = runtime_parent / ("a" * 32)
            tokens = iter(["a" * 32, "b" * 32, "c" * 32])
            real_resolve = pathlib.Path.resolve
            real_link_check = routing_eval._path_is_link_or_junction
            def is_target(path):
                return path.name == raw_runtime_root.name and path.parent.name == runtime_parent.name
            def fake_resolve(path, strict=False):
                if is_target(path):
                    raise AssertionError("linked runtime root must be rejected before resolve")
                return real_resolve(path, strict=strict)
            def fake_link_check(path):
                return is_target(path) or real_link_check(path)
            with mock.patch.object(pathlib.Path, "resolve", autospec=True, side_effect=fake_resolve):
                with mock.patch.object(routing_eval, "_path_is_link_or_junction", side_effect=fake_link_check):
                    with self.assertRaisesRegex(ValueError, "runtime root.*symlink|junction"):
                        routing_eval.prepare_campaign(
                            [_case()], coordinator, trials=1, seed=7,
                            runtime_parent=runtime_parent, token_factory=lambda: next(tokens),
                        )

    def test_prepare_campaign_rejects_runtime_parent_inside_coordinator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            with self.assertRaisesRegex(ValueError, "disjoint"):
                routing_eval.prepare_campaign(
                    [_case()], coordinator, trials=1, seed=7,
                    runtime_parent=coordinator / "runtime",
                    token_factory=lambda: "a" * 32,
                )

    def test_prepare_campaign_rejects_row_token_reusing_campaign_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["a" * 32, "a" * 32, "b" * 32])
            with self.assertRaisesRegex(ValueError, "unique"):
                routing_eval.prepare_campaign(
                    [_case()], root / "coordinator", trials=1, seed=7,
                    runtime_parent=root / "runtime-parent", token_factory=lambda: next(tokens),
                )

    def test_prepare_campaign_rolls_back_attempt_owned_state_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            coordinator = root / "coordinator"
            coordinator.mkdir()
            marker = coordinator / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            runtime_parent = root / "runtime-parent"
            tokens = iter(["a" * 32, "a" * 32, "b" * 32])
            with self.assertRaisesRegex(ValueError, "unique"):
                routing_eval.prepare_campaign(
                    [_case()], coordinator, trials=1, seed=7,
                    runtime_parent=runtime_parent, token_factory=lambda: next(tokens),
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((coordinator / "prompts").exists())
            self.assertFalse((coordinator / "fixtures").exists())
            self.assertFalse((coordinator / "manifest.jsonl").exists())
            self.assertFalse((coordinator / "campaign.json").exists())
            self.assertFalse(runtime_parent.exists())

    def test_prepare_campaign_rejects_reused_opaque_row_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            tokens = iter(["a" * 32, "b" * 32, "b" * 32])
            with self.assertRaisesRegex(ValueError, "unique"):
                routing_eval.prepare_campaign(
                    [_case()], root / "coordinator", trials=1, seed=7,
                    runtime_parent=root / "runtime-parent", token_factory=lambda: next(tokens),
                )

    def test_prepare_campaign_rejects_workspace_prompt_token(self):
        case = _case()
        case["prompt"] = "Run in {workspace}.\n[CASE-ID: {case_key}]"
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "workspace"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

    def test_prepare_campaign_rejects_blank_expected_first_command_fragment(self):
        case = _case()
        case["expected_first_command_fragment"] = "   "
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "first command"):
                routing_eval.prepare_campaign(
                    [case], root / "coordinator", trials=1, seed=7,
                    runtime_parent=root / "runtime-parent",
                )

    def test_prepare_campaign_is_seed_deterministic_and_pair_balanced(self):
        cases = [_case(f"R{i:02d}") for i in range(1, 6)]
        signatures = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temp_dir:
                rows = routing_eval.prepare_campaign(cases, pathlib.Path(temp_dir), trials=3, seed=11)
                signatures.append([(row["case_key"], row["arm"]) for row in rows])
                for trial_id in {"T01", "T02", "T03"}:
                    pairs = _pair_positions(rows, trial_id)
                    s_first = sum(entries[0][1] == "S" for entries in pairs.values())
                    m_first = sum(entries[0][1] == "M" for entries in pairs.values())
                    self.assertLessEqual(abs(s_first - m_first), 1)
        self.assertEqual(signatures[0], signatures[1])


if __name__ == "__main__":
    unittest.main()


def _row(record_type, payload, timestamp="2026-08-14T00:00:00Z"):
    return {"timestamp": timestamp, "type": record_type, "payload": payload}


def _tool(call_id, call_input, timestamp):
    return _row(
        "response_item",
        {"type": "custom_tool_call", "call_id": call_id, "name": "exec", "input": call_input},
        timestamp,
    )


def _output(call_id, text, timestamp):
    return _row(
        "response_item",
        {"type": "custom_tool_call_output", "call_id": call_id, "output": [{"text": text}]},
        timestamp,
    )


def _base_rollout(case_key, workspace, skill_visible=True):
    skills = "- powershell-reliability: candidate" if skill_visible else "- other-skill: candidate"
    return [
        _row("session_meta", {"session_id": f"session-{case_key}", "originator": "Codex Desktop", "cli_version": "test"}),
        _row("turn_context", {"cwd": str(workspace), "model": "gpt-test", "effort": "high", "approval_policy": "never", "sandbox_policy": {"type": "workspace-write"}}),
        _row("world_state", {"state": {"host_skills": {"body": skills}}}),
        _row("event_msg", {"type": "user_message", "message": f"Do the task.\n[CASE-ID: {case_key}]"}),
    ]


def _manifest_row(case_key, arm, workspace, group="should_trigger", detector=None, lane="validation"):
    case_id, trial_id = case_key.split("-")
    return {
        "case_key": case_key,
        "case_id": case_id,
        "trial_id": trial_id,
        "lane": lane,
        "group": group,
        "arm": arm,
        "sequence": 1,
        "prompt_sha256": routing_eval.trigger_eval._sha256_text(f"Do the task.\n[CASE-ID: {case_key}]"),
        "workspace": str(workspace),
        "workspace_sha256": routing_eval.workspace_identity(str(workspace)),
        "fixture_sha256": "F" * 64,
        "expected_first_command_fragment": ("pwsh.exe -NoProfile -File .\\task.ps1" if group == "should_trigger" else None),
        "boundary_detector": detector or {"kind": "first_command_nonzero"},
    }


def _failed_command_rows():
    return [
        _tool("cmd1", "tools.shell_command({command:'pwsh.exe -NoProfile -File .\\task.ps1'})", "2026-08-14T00:00:01Z"),
        _output("cmd1", "Exit code: 7", "2026-08-14T00:00:02Z"),
    ]


def _skill_row(timestamp="2026-08-14T00:00:03Z"):
    return _tool("skill1", "Get-Content C:\\Users\\u\\.codex\\skills\\powershell-reliability\\SKILL.md -Raw", timestamp)


def _mcp_row(timestamp="2026-08-14T00:00:04Z"):
    return _tool("mcp1", "tools.mcp__psr_reliability_native__diagnose_failure({exit_code:7})", timestamp)


class RoutingEvalTemporalTests(unittest.TestCase):
    def test_current_desktop_exec_command_counts_as_first_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R00-T01", "M", workspace)
            rows = _base_rollout("R00-T01", workspace, skill_visible=False) + [
                _tool(
                    "cmd1",
                    "const r = await tools.exec_command({cmd:'pwsh.exe -NoProfile -File .\\\\task.ps1'}); text(r.output);",
                    "2026-08-14T00:00:01Z",
                ),
                _output("cmd1", "CONFIG_MISSING", "2026-08-14T00:00:02Z"),
            ]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertIsNotNone(record["first_attempt_start_index"])
        self.assertNotIn("first_command_mismatch", record["invalid_reasons"])

    def test_desktop_first_command_rejects_near_fragment_collision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R00A-T01", "M", workspace)
            manifest["expected_first_command_fragment"] = "task.ps1"
            rows = _base_rollout("R00A-T01", workspace, skill_visible=False) + [
                _tool("cmd1", r"tools.shell_command({command:'pwsh.exe -File .\not-task.ps1'})", "2026-08-14T00:00:01Z"),
                _output("cmd1", "Exit code: 7", "2026-08-14T00:00:02Z"),
            ]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertIn("first_command_mismatch", record["invalid_reasons"])

    def test_desktop_first_command_accepts_windows_path_separator_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R00B-T01", "M", workspace)
            manifest["expected_first_command_fragment"] = r"app\build.ps1"
            rows = _base_rollout("R00B-T01", workspace, skill_visible=False) + [
                _tool("cmd1", "tools.shell_command({command:'pwsh.exe -File ./app/build.ps1'})", "2026-08-14T00:00:01Z"),
                _output("cmd1", "Exit code: 7", "2026-08-14T00:00:02Z"),
            ]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertNotIn("first_command_mismatch", record["invalid_reasons"])

    def test_desktop_first_command_rejects_malformed_manifest_expectation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            rows = _base_rollout("R00C-T01", workspace, skill_visible=False) + [
                _tool("cmd1", "tools.shell_command({command:'pwsh.exe -File ./task.ps1'})", "2026-08-14T00:00:01Z"),
                _output("cmd1", "Exit code: 7", "2026-08-14T00:00:02Z"),
            ]
            for value in ("   ", 123):
                with self.subTest(value=value):
                    manifest = _manifest_row("R00C-T01", "M", workspace)
                    manifest["expected_first_command_fragment"] = value
                    with self.assertRaisesRegex(ValueError, "first command"):
                        routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)

    def test_s_failure_skill_then_mcp_is_valid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R01-T01", "S", workspace)
            rows = _base_rollout("R01-T01", workspace) + _failed_command_rows()
            rows += [_skill_row(), _mcp_row()]
            record = routing_eval.extract_trial(rows, pathlib.Path("rollout.jsonl"), manifest)
        self.assertTrue(record["valid"])
        self.assertEqual(record["first_command_exit_code"], 7)
        self.assertEqual(record["eligible_boundary_index"], 5)
        self.assertEqual(record["skill_activation_indexes"], [6])
        self.assertEqual(record["mcp_intervention_indexes"], [7])
        self.assertFalse(record["premature_skill_activation"])
        self.assertFalse(record["s_protocol_bypass"])

    def test_s_flags_premature_skill_activation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R02-T01", "S", workspace)
            rows = _base_rollout("R02-T01", workspace)
            rows += [_skill_row("2026-08-14T00:00:00.500Z")]
            rows += _failed_command_rows() + [_mcp_row()]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertTrue(record["premature_skill_activation"])
        self.assertEqual(record["pre_boundary_mcp_call_count"], 0)

    def test_s_flags_protocol_bypass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R03-T01", "S", workspace)
            rows = _base_rollout("R03-T01", workspace) + _failed_command_rows() + [_mcp_row()]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertTrue(record["s_protocol_bypass"])

    def test_m_requires_skill_absent_and_allows_post_boundary_mcp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R04-T01", "M", workspace)
            rows = _base_rollout("R04-T01", workspace, skill_visible=False)
            rows += _failed_command_rows() + [_mcp_row()]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertTrue(record["valid"])
        self.assertEqual(record["mcp_intervention_count"], 1)

    def test_m_catalog_presence_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R05-T01", "M", workspace)
            rows = _base_rollout("R05-T01", workspace, skill_visible=True) + _failed_command_rows()
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertFalse(record["valid"])
        self.assertIn("arm_catalog_mismatch", record["invalid_reasons"])

    def test_no_trigger_s_skill_read_is_observable_without_mcp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row(
                "R06-T01", "S", workspace, group="should_not_trigger", detector={"kind": "none"}
            )
            rows = _base_rollout("R06-T01", workspace) + [_skill_row()]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertEqual(record["skill_activation_count"], 1)
        self.assertEqual(record["mcp_intervention_count"], 0)

    def test_no_trigger_m_zero_mcp_is_clean(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row(
                "R07-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"}
            )
            rows = _base_rollout("R07-T01", workspace, skill_visible=False)
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertEqual(record["mcp_intervention_count"], 0)
        self.assertTrue(record["valid"])

    def test_tool_output_marker_can_establish_exit_zero_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row(
                "R08-T01", "M", workspace,
                detector={"kind": "tool_output_contains", "marker": "POST-CONDITION: FAIL"},
            )
            rows = _base_rollout("R08-T01", workspace, skill_visible=False)
            rows += [
                _tool("cmd1", "tools.shell_command({command:'pwsh.exe -NoProfile -File .\\task.ps1'})", "2026-08-14T00:00:01Z"),
                _output("cmd1", "Exit code: 0\nPOST-CONDITION: FAIL", "2026-08-14T00:00:02Z"),
                _mcp_row(),
            ]
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertEqual(record["first_command_exit_code"], 0)
        self.assertEqual(record["eligible_boundary_kind"], "tool_output_contains")
        self.assertEqual(record["eligible_boundary_index"], 5)


class RoutingEvalCollectionTests(unittest.TestCase):
    def test_collect_binds_shared_marker_by_workspace_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            s_workspace = root / "workspaces" / "S" / "R01-T01"
            m_workspace = root / "workspaces" / "M" / "R01-T01"
            s_workspace.mkdir(parents=True)
            m_workspace.mkdir(parents=True)
            manifest = [
                _manifest_row("R01-T01", "S", s_workspace),
                _manifest_row("R01-T01", "M", m_workspace),
            ]
            manifest[0]["sequence"] = 1
            manifest[1]["sequence"] = 2
            s_rows = _base_rollout("R01-T01", s_workspace) + _failed_command_rows() + [_skill_row(), _mcp_row()]
            m_rows = _base_rollout("R01-T01", m_workspace, skill_visible=False) + _failed_command_rows() + [_mcp_row()]
            routing_eval.trigger_eval.write_jsonl(root / "rollout-s.jsonl", s_rows)
            routing_eval.trigger_eval.write_jsonl(root / "rollout-m.jsonl", m_rows)
            records = routing_eval.collect_rollouts(root, manifest)
        self.assertEqual([(r["case_id"], r["trial_id"], r["arm"]) for r in records], [("R01", "T01", "S"), ("R01", "T01", "M")])

    def test_collect_ignores_unrelated_malformed_and_wrong_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "expected"
            workspace.mkdir()
            manifest = [_manifest_row("R02-T01", "M", workspace)]
            (root / "rollout-bad.jsonl").write_text('{"type":"event_msg","payload":', encoding="utf-8")
            wrong = root / "wrong"
            wrong.mkdir()
            wrong_rows = _base_rollout("R02-T01", wrong, skill_visible=False) + _failed_command_rows()
            routing_eval.trigger_eval.write_jsonl(root / "rollout-wrong.jsonl", wrong_rows)
            records = routing_eval.collect_rollouts(root, manifest)
        self.assertEqual(records, [])

    def test_collect_rejects_malformed_rollout_bound_to_manifest_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "expected"
            workspace.mkdir()
            manifest = [_manifest_row("R03-T01", "M", workspace)]
            rows = _base_rollout("R03-T01", workspace, skill_visible=False)
            path = root / "rollout-malformed.jsonl"
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
                handle.write('{"broken":\n')
            with self.assertRaisesRegex(ValueError, "malformed rollout for manifest workspace"):
                routing_eval.collect_rollouts(root, manifest)

    def test_collect_rejects_malformed_manifest_first_command_expectation_without_rollout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "expected"
            workspace.mkdir()
            manifest = [_manifest_row("R03B-T01", "M", workspace)]
            manifest[0]["expected_first_command_fragment"] = "   "
            with self.assertRaisesRegex(ValueError, "first command"):
                routing_eval.collect_rollouts(root, manifest)

    def test_collect_rejects_duplicate_same_arm_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "expected"
            workspace.mkdir()
            manifest = [_manifest_row("R03-T01", "M", workspace)]
            rows = _base_rollout("R03-T01", workspace, skill_visible=False) + _failed_command_rows()
            routing_eval.trigger_eval.write_jsonl(root / "rollout-a.jsonl", rows)
            routing_eval.trigger_eval.write_jsonl(root / "rollout-b.jsonl", rows)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                routing_eval.collect_rollouts(root, manifest)

    def test_collect_binds_markerless_calibration_prompt_by_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "calibration" / "M" / "cal-read-existing-state-T01"
            workspace.mkdir(parents=True)
            manifest = [_manifest_row("R04-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})]
            manifest[0]["case_key"] = "cal-read-existing-state-T01"
            manifest[0]["case_id"] = "cal-read-existing-state"
            manifest[0]["prompt_sha256"] = routing_eval.trigger_eval._sha256_text("Check config-status.txt")
            rows = _base_rollout("R04-T01", workspace, skill_visible=False)
            rows[3]["payload"]["message"] = "Check config-status.txt\n"
            routing_eval.trigger_eval.write_jsonl(root / "rollout-calibration.jsonl", rows)
            records = routing_eval.collect_rollouts(root, manifest)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["case_key"], "cal-read-existing-state-T01")
        self.assertTrue(records[0]["valid"])
        self.assertEqual(records[0]["prompt_sha256"], manifest[0]["prompt_sha256"])

    def test_collect_preserves_non_newline_prompt_whitespace_drift(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            workspace = root / "calibration" / "M" / "cal-slower-verification-T01"
            workspace.mkdir(parents=True)
            manifest = [_manifest_row("R05-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})]
            manifest[0]["case_key"] = "cal-slower-verification-T01"
            manifest[0]["case_id"] = "cal-slower-verification"
            manifest[0]["prompt_sha256"] = routing_eval.trigger_eval._sha256_text("Run verify-package.ps1")
            rows = _base_rollout("R05-T01", workspace, skill_visible=False)
            rows[3]["payload"]["message"] = "Run verify-package.ps1 \n"
            routing_eval.trigger_eval.write_jsonl(root / "rollout-drift.jsonl", rows)
            records = routing_eval.collect_rollouts(root, manifest)
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["valid"])
        self.assertIn("prompt_hash_mismatch", records[0]["invalid_reasons"])


def _token_row(total, timestamp="2026-08-14T00:00:00Z", **overrides):
    usage = {
        "input_tokens": total - 5,
        "cached_input_tokens": 1,
        "cache_write_input_tokens": 0,
        "output_tokens": 3,
        "reasoning_output_tokens": 1,
        "total_tokens": total,
    }
    usage.update(overrides)
    return _row(
        "event_msg",
        {"type": "token_count", "info": {"total_token_usage": usage}},
        timestamp,
    )


class RoutingEvalCostTests(unittest.TestCase):
    def test_final_token_usage_records_all_components(self):
        rows = [_token_row(10), _token_row(20, "2026-08-14T00:00:01Z", input_tokens=12)]
        usage = routing_eval.final_token_usage(rows)
        self.assertEqual(usage["total_tokens"], 20)
        self.assertEqual(usage["input_tokens"], 12)
        self.assertEqual(set(usage), set(routing_eval.TOKEN_FIELDS))

    def test_missing_or_invalid_token_usage_remains_none(self):
        self.assertIsNone(routing_eval.final_token_usage([]))
        self.assertIsNone(routing_eval.final_token_usage([_token_row(10, input_tokens=-1)]))

    def test_extract_trial_adds_rollout_latency_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R09-T01", "S", workspace)
            rows = _base_rollout("R09-T01", workspace) + _failed_command_rows() + [_skill_row(), _mcp_row()]
            rows.append(_token_row(40, "2026-08-14T00:00:05Z"))
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertEqual(record["turn_duration_ms"], 5000.0)
        self.assertEqual(record["boundary_to_skill_ms"], 1000.0)
        self.assertEqual(record["boundary_to_mcp_ms"], 2000.0)
        self.assertEqual(record["token_usage"]["total_tokens"], 40)

    def test_missing_latency_endpoint_stays_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("R10-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            rows = _base_rollout("R10-T01", workspace, skill_visible=False)
            record = routing_eval.extract_trial(rows, pathlib.Path("r.jsonl"), manifest)
        self.assertIsNone(record["boundary_to_mcp_ms"])
        self.assertIsNone(record["boundary_to_skill_ms"])
        self.assertIsNone(record["token_usage"])

    def test_phase_delta_requires_monotonic_bracketing_snapshots(self):
        monotonic = [_token_row(10), _token_row(20, "2026-08-14T00:00:01Z")]
        delta = routing_eval.phase_token_delta(monotonic, 0, 1)
        self.assertEqual(delta["total_tokens"], 10)
        non_monotonic = [_token_row(20), _token_row(10, "2026-08-14T00:00:01Z")]
        self.assertIsNone(routing_eval.phase_token_delta(non_monotonic, 0, 1))

    def test_negative_timestamp_delta_stays_none(self):
        self.assertIsNone(
            routing_eval.timestamp_delta_ms("2026-08-14T00:00:02Z", "2026-08-14T00:00:01Z")
        )


def _score_record(case_id="R20", trial_id="T01", arm="S", group="should_trigger", lane="validation", **updates):
    record = {
        "case_id": case_id,
        "trial_id": trial_id,
        "arm": arm,
        "group": group,
        "lane": lane,
        "prompt_sha256": "A" * 64,
        "fixture_sha256": "B" * 64,
        "model": "gpt-test",
        "effort": "high",
        "approval_policy": "never",
        "sandbox_type": "workspace-write",
        "cli_version": "desktop-test",
        "originator": "Codex Desktop",
        "valid": True,
        "invalid_reasons": [],
        "mcp_intervention_count": 0,
        "pre_boundary_mcp_call_count": 0,
        "skill_activation_count": 0,
        "premature_skill_activation": False,
        "s_protocol_bypass": False,
        "selected_other_skills": [],
        "token_usage": None,
        "boundary_to_mcp_ms": None,
        "boundary_to_skill_ms": None,
        "turn_duration_ms": None,
        "post_condition_passed": None,
        "wrong_repair": None,
        "reliability_caused_wrong_repair": None,
        "completion_claimed": None,
        "false_completion": None,
        "reliability_caused_false_completion": None,
        "evidence_ref": None,
    }
    record.update(updates)
    return record


class RoutingEvalAdjudicationTests(unittest.TestCase):
    def test_merge_adjudication_preserves_missing_causal_labels(self):
        records = [_score_record()]
        adjudication = [{
            "case_id": "R20", "trial_id": "T01", "arm": "S",
            "wrong_repair": False, "completion_claimed": True,
            "false_completion": False, "evidence_ref": "review://R20-T01-S",
        }]
        merged = routing_eval.merge_adjudication(records, adjudication)
        self.assertIsNone(merged[0]["reliability_caused_wrong_repair"])
        self.assertIsNone(merged[0]["reliability_caused_false_completion"])

    def test_merge_rejects_duplicate_unknown_and_invalid_types(self):
        records = [_score_record()]
        row = {"case_id": "R20", "trial_id": "T01", "arm": "S", "wrong_repair": False}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            routing_eval.merge_adjudication(records, [row, dict(row)])
        with self.assertRaisesRegex(ValueError, "unknown"):
            routing_eval.merge_adjudication(records, [dict(row, case_id="R99")])
        with self.assertRaisesRegex(ValueError, "boolean"):
            routing_eval.merge_adjudication(records, [dict(row, wrong_repair="no")])


class RoutingEvalScoringTests(unittest.TestCase):
    def test_scores_post_boundary_mcp_recall_and_arm_specific_false_activation(self):
        records = [
            _score_record("R21", arm="S", skill_activation_count=1),
            _score_record("R22", arm="M", mcp_intervention_count=1),
            _score_record("R23", arm="S", group="should_not_trigger", skill_activation_count=1),
            _score_record("R24", arm="M", group="should_not_trigger"),
            _score_record("R25", arm="S", group="boundary", mcp_intervention_count=1),
            _score_record("R26", arm="S", valid=False, invalid_reasons=["workspace_mismatch"], mcp_intervention_count=1),
        ]
        report = routing_eval.score_records(records)
        s_admission = report["arms"]["S"]["lanes"]["admission"]
        m_admission = report["arms"]["M"]["lanes"]["admission"]
        self.assertEqual(s_admission["mcp_intervention_recall"], 0.0)
        self.assertEqual(s_admission["skill_read_recall"], 1.0)
        self.assertEqual(s_admission["false_activation_rate"], 1.0)
        self.assertEqual(m_admission["mcp_intervention_recall"], 1.0)
        self.assertEqual(m_admission["false_activation_rate"], 0.0)
        self.assertEqual(report["arms"]["S"]["invalid_trial_count"], 1)
        self.assertEqual(report["arms"]["S"]["boundary_trial_count"], 1)

    def test_pre_failure_mcp_and_s_protocol_bypass_are_reported(self):
        records = [
            _score_record("R27", arm="S", mcp_intervention_count=1, pre_boundary_mcp_call_count=1, s_protocol_bypass=True),
            _score_record("R28", arm="M", mcp_intervention_count=1),
        ]
        report = routing_eval.score_records(records)
        self.assertEqual(report["arms"]["S"]["gates"]["pre_failure_mcp"], "FAIL")
        self.assertEqual(report["arms"]["S"]["s_protocol_bypass_count"], 1)

    def test_paired_idle_token_gate_requires_coverage_and_uses_median_percent(self):
        records = []
        for index in range(10):
            case_id = f"N{index:02d}"
            m_total = 1000
            s_total = 1010 if index < 9 else 1030
            records.append(_score_record(case_id, arm="S", group="should_not_trigger", token_usage={"total_tokens": s_total}))
            records.append(_score_record(case_id, arm="M", group="should_not_trigger", token_usage={"total_tokens": m_total}))
        report = routing_eval.score_records(records)
        paired = report["paired_idle_token"]
        self.assertEqual(paired["coverage"], 1.0)
        self.assertEqual(paired["median_s_minus_m_pct"], 1.0)
        self.assertEqual(paired["gate_state"], "PASS")

    def test_paired_idle_token_gate_is_unresolved_below_ninety_percent(self):
        records = []
        for index in range(10):
            case_id = f"Q{index:02d}"
            s_usage = {"total_tokens": 1010} if index < 8 else None
            records.append(_score_record(case_id, arm="S", group="should_not_trigger", token_usage=s_usage))
            records.append(_score_record(case_id, arm="M", group="should_not_trigger", token_usage={"total_tokens": 1000}))
        paired = routing_eval.score_records(records)["paired_idle_token"]
        self.assertEqual(paired["coverage"], 0.8)
        self.assertEqual(paired["gate_state"], "UNRESOLVED")

    def test_missing_arm_token_or_zero_m_total_is_unscorable(self):
        records = [
            _score_record("Z01", arm="S", group="should_not_trigger", token_usage=None),
            _score_record("Z01", arm="M", group="should_not_trigger", token_usage={"total_tokens": 100}),
            _score_record("Z02", arm="S", group="should_not_trigger", token_usage={"total_tokens": 100}),
            _score_record("Z02", arm="M", group="should_not_trigger", token_usage={"total_tokens": 0}),
        ]
        paired = routing_eval.score_records(records)["paired_idle_token"]
        self.assertEqual(paired["eligible_pair_count"], 2)
        self.assertEqual(paired["scorable_pair_count"], 0)
        self.assertEqual(paired["coverage"], 0.0)

    def test_causal_hard_gates_fail_on_positive_labels(self):
        records = [
            _score_record(
                "C01", arm="S", mcp_intervention_count=1,
                reliability_caused_wrong_repair=True,
                reliability_caused_false_completion=False,
            )
        ]
        gates = routing_eval.score_records(records)["arms"]["S"]["gates"]
        self.assertEqual(gates["reliability_caused_wrong_repair"], "FAIL")
        records[0]["reliability_caused_wrong_repair"] = False
        records[0]["reliability_caused_false_completion"] = True
        gates = routing_eval.score_records(records)["arms"]["S"]["gates"]
        self.assertEqual(gates["reliability_caused_false_completion"], "FAIL")

    def test_causal_hard_gates_are_unresolved_until_interventions_reviewed(self):
        record = _score_record("C02", arm="M", mcp_intervention_count=1)
        gates = routing_eval.score_records([record])["arms"]["M"]["gates"]
        self.assertEqual(gates["reliability_caused_wrong_repair"], "UNRESOLVED")
        self.assertEqual(gates["reliability_caused_false_completion"], "UNRESOLVED")
        record["reliability_caused_wrong_repair"] = False
        record["reliability_caused_false_completion"] = False
        gates = routing_eval.score_records([record])["arms"]["M"]["gates"]
        self.assertEqual(gates["reliability_caused_wrong_repair"], "PASS")
        self.assertEqual(gates["reliability_caused_false_completion"], "PASS")


import contextlib
import io


class RoutingEvalCliTests(unittest.TestCase):
    def test_status_reports_invalid_remaining_and_next_pointers(self):
        manifest = [
            {"case_id": "R30", "trial_id": "T01", "arm": "S", "sequence": 1, "prompt_path": "p1", "workspace": "w1"},
            {"case_id": "R30", "trial_id": "T01", "arm": "M", "sequence": 2, "prompt_path": "p1", "workspace": "w2"},
        ]
        records = [{"case_id": "R30", "trial_id": "T01", "arm": "S", "valid": False}]
        status = routing_eval.collection_status(manifest, records)
        self.assertEqual(status["expected_trials"], 2)
        self.assertEqual(status["collected_trials"], 1)
        self.assertEqual(status["invalid_trials"], 1)
        self.assertEqual(status["remaining_trials"], 1)
        self.assertEqual(status["next_prompt_path"], "p1")
        self.assertEqual(status["next_workspace"], "w2")

    def test_collect_malformed_input_returns_two_and_writes_no_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            manifest = root / "manifest.jsonl"
            manifest.write_text('{"case_id":', encoding="utf-8")
            output = root / "records.jsonl"
            report = root / "report.json"
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                exit_code = routing_eval.main([
                    "collect", "--manifest", str(manifest),
                    "--sessions-root", str(root), "--output", str(output),
                    "--report", str(report),
                ])
        self.assertEqual(exit_code, 2)
        self.assertIn("error", json.loads(stream.getvalue()))
        self.assertFalse(output.exists())
        self.assertFalse(report.exists())


class RoutingEvalEndToEndTests(unittest.TestCase):
    def test_prepare_collect_score_synthetic_two_case_campaign(self):
        trigger_case = _case("R31", lane="validation")
        negative_case = _case("R32", group="should_not_trigger", lane="validation")
        negative_case["boundary_detector"] = {"kind": "none"}
        negative_case["expected_first_command_fragment"] = None
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            campaign = root / "campaign"
            manifest = routing_eval.prepare_campaign([trigger_case, negative_case], campaign, trials=1, seed=3)
            sessions = root / "sessions"
            sessions.mkdir()
            for row in manifest:
                workspace = pathlib.Path(row["workspace"])
                rollout = _base_rollout(row["case_key"], workspace, skill_visible=row["arm"] == "S")
                if row["group"] == "should_trigger":
                    rollout += _failed_command_rows()
                    if row["arm"] == "S":
                        rollout += [_skill_row()]
                    rollout += [_mcp_row()]
                routing_eval.trigger_eval.write_jsonl(sessions / f"rollout-{row['sequence']:02d}.jsonl", rollout)
            records = routing_eval.collect_rollouts(sessions, manifest)
            report = routing_eval.score_records(records)
        self.assertEqual(len(records), 4)
        self.assertEqual(set(report["arms"]), {"S", "M"})
        self.assertEqual(report["arms"]["S"]["gates"]["mcp_intervention_recall"], "PASS")
        self.assertEqual(report["arms"]["M"]["gates"]["mcp_intervention_recall"], "PASS")


class RoutingEvalRepositoryContractTests(unittest.TestCase):
    def test_repository_contract_and_runbook_freeze_r4_invariants(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        contract_path = repo / "docs" / "contracts" / "routing-eval-contract-r4.md"
        runbook_path = repo / "docs" / "runbooks" / "routing-eval-desktop.md"
        contract = contract_path.read_text(encoding="utf-8")
        runbook = runbook_path.read_text(encoding="utf-8")
        combined = contract + "\n" + runbook
        required = [
            "S=`thin companion Skill + MCP`",
            "M=`MCP-only self-routing`",
            "Arm H is excluded for the current Desktop build",
            "pre-failure MCP = 0",
            "MCP intervention recall >= 90%",
            "controlled false activation <= 5%",
            "production shadow <= 1/100",
            "paired idle-token delta <= +2%",
            "token coverage >= 90%",
            "missing measurements remain missing",
            "M setup is BLOCKED rather than simulated",
            "raw rollout evidence stays host-local",
            "pair identity drift invalidates both arms",
            "post_condition_passed",
            "tool_output_marker",
            "workspace_state",
            "evaluator-owned",
            "relative paths under the exact trial workspace",
            "tool_output_marker is legacy-only",
            "final grading does not create an earlier routing boundary",
            "assistant prose is never post-condition evidence",
            "wrong_repair review coverage",
        ]
        for phrase in required:
            self.assertIn(phrase, combined)
        self.assertNotIn("post_condition.kind=none` or `post_condition.kind=tool_output_marker", contract)


class RoutingEvalReviewPairConsistencyTests(unittest.TestCase):
    def _paired_records(self, group="should_trigger"):
        identity = {
            "prompt_sha256": "A" * 64,
            "fixture_sha256": "B" * 64,
            "model": "gpt-test",
            "effort": "high",
            "approval_policy": "never",
            "sandbox_type": "workspace-write",
            "cli_version": "desktop-test",
            "originator": "Codex Desktop",
        }
        s = _score_record("I01", arm="S", group=group, mcp_intervention_count=1, **identity)
        m = _score_record("I01", arm="M", group=group, mcp_intervention_count=1, **identity)
        return s, m

    def test_pair_identity_drift_invalidates_both_arms(self):
        for field in routing_eval.PAIR_CONSISTENCY_FIELDS:
            with self.subTest(field=field):
                s, m = self._paired_records()
                m[field] = f"drift-{field}"
                report = routing_eval.score_records([s, m])
                for arm in ("S", "M"):
                    self.assertEqual(report["arms"][arm]["valid_trial_count"], 0)
                    self.assertEqual(report["arms"][arm]["invalid_trial_count"], 1)
                    self.assertIn(f"pair_identity_drift:{field}", report["arms"][arm]["invalid_reasons"])
                    self.assertIsNone(report["arms"][arm]["lanes"]["admission"]["mcp_intervention_recall"])

    def test_pair_identity_missing_field_is_invalid_evidence(self):
        s, m = self._paired_records()
        m["cli_version"] = None
        report = routing_eval.score_records([s, m])
        for arm in ("S", "M"):
            self.assertEqual(report["arms"][arm]["valid_trial_count"], 0)
            self.assertIn("pair_identity_missing:cli_version", report["arms"][arm]["invalid_reasons"])

    def test_pair_drift_is_excluded_from_idle_token_denominator(self):
        s, m = self._paired_records(group="should_not_trigger")
        s["token_usage"] = {"total_tokens": 1010}
        m["token_usage"] = {"total_tokens": 1000}
        m["sandbox_type"] = "different-sandbox"
        paired = routing_eval.score_records([s, m])["paired_idle_token"]
        self.assertEqual(paired["eligible_pair_count"], 0)
        self.assertEqual(paired["scorable_pair_count"], 0)
        self.assertIsNone(paired["coverage"])
        self.assertEqual(paired["gate_state"], "UNRESOLVED")


class RoutingEvalReviewPostConditionTests(unittest.TestCase):
    def _post_condition(self):
        return {
            "kind": "tool_output_marker",
            "pass_marker": "POST-CONDITION: PASS",
            "fail_marker": "POST-CONDITION: FAIL",
        }

    def _workspace_state(self):
        return {
            "kind": "workspace_state",
            "mode": "all",
            "checks": [
                {"kind": "file_exists", "path": "result.txt"},
                {"kind": "file_size", "path": "result.txt", "min_bytes": 1, "max_bytes": 64},
            ],
        }

    def test_prepare_freezes_declared_workspace_state_rule(self):
        case = _case("P00", lane="validation")
        case["post_condition"] = self._workspace_state()
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)
        self.assertEqual(rows[0]["post_condition"], self._workspace_state())
        self.assertEqual(rows[0]["post_condition"], rows[1]["post_condition"])

    def test_prepare_rejects_workspace_state_parent_escape(self):
        case = _case("P00E", lane="validation")
        case["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "../outside.txt"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "workspace-state"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

    def test_prepare_rejects_workspace_state_absolute_path(self):
        case = _case("P00A", lane="validation")
        case["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "C:/outside.txt"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "workspace-state"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

    def test_prepare_rejects_workspace_state_bad_sha256(self):
        case = _case("P00S", lane="validation")
        case["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_sha256", "path": "result.txt", "expected_sha256": "not-a-sha"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "sha256"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

    def test_prepare_rejects_workspace_state_unknown_check(self):
        case = _case("P00U", lane="validation")
        case["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "mystery", "path": "result.txt"}]}
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "workspace-state"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

    def test_workspace_state_ignores_agent_pass_marker_when_file_is_wrong(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            (workspace / "result.txt").write_text("STALE\n", encoding="utf-8")
            manifest = _manifest_row("P06-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_sha256", "path": "result.txt", "expected_sha256": hashlib.sha256(b"READY\n").hexdigest()}]}
            rows = _base_rollout("P06-T01", workspace, skill_visible=False) + [_output("x", "POST-CONDITION: PASS", "2026-08-14T00:00:05Z")]
            record = routing_eval.extract_trial(rows, pathlib.Path("p06.jsonl"), manifest)
        self.assertFalse(record["post_condition_passed"])
        self.assertEqual(record["post_condition_evidence_source"], "evaluator_workspace")

    def test_workspace_state_supports_file_absent_directory_size_and_any(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            (workspace / "result.txt").write_bytes(b"READY")
            (workspace / "folder").mkdir()
            manifest = _manifest_row("P07-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}, {"kind": "file_absent", "path": "missing.txt"}, {"kind": "directory_exists", "path": "folder"}, {"kind": "file_size", "path": "result.txt", "min_bytes": 5, "max_bytes": 5}]}
            record = routing_eval.extract_trial(_base_rollout("P07-T01", workspace, skill_visible=False), pathlib.Path("p07.jsonl"), manifest)
            self.assertTrue(record["post_condition_passed"])
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "any", "checks": [{"kind": "file_exists", "path": "missing.txt"}, {"kind": "file_exists", "path": "result.txt"}]}
            any_record = routing_eval.extract_trial(_base_rollout("P07-T01", workspace, skill_visible=False), pathlib.Path("p07-any.jsonl"), manifest)
        self.assertTrue(any_record["post_condition_passed"])

    def test_workspace_state_missing_file_is_failed_check_not_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("P08-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "missing.txt"}]}
            record = routing_eval.extract_trial(_base_rollout("P08-T01", workspace, skill_visible=False), pathlib.Path("p08.jsonl"), manifest)
        self.assertFalse(record["post_condition_passed"])
        self.assertTrue(record["valid"])
        self.assertEqual(record["invalid_reasons"], [])

    def test_workspace_state_hash_cap_is_bounded_failed_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            target = workspace / "large.bin"
            target.write_bytes(b"12345678")
            manifest = _manifest_row("P09-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_sha256", "path": "large.bin", "expected_sha256": hashlib.sha256(b"12345678").hexdigest()}]}
            original = routing_eval.MAX_POST_CONDITION_HASH_BYTES
            routing_eval.MAX_POST_CONDITION_HASH_BYTES = 4
            try:
                record = routing_eval.extract_trial(_base_rollout("P09-T01", workspace, skill_visible=False), pathlib.Path("p09.jsonl"), manifest)
            finally:
                routing_eval.MAX_POST_CONDITION_HASH_BYTES = original
        self.assertFalse(record["post_condition_passed"])
        self.assertTrue(record["valid"])
        self.assertEqual(record["post_condition_checks"][0]["error_kind"], "hash_size_limit")

    def test_workspace_state_access_error_does_not_pass_file_absent(self):
        target = pathlib.Path("inaccessible.txt")
        with mock.patch("os.stat", side_effect=PermissionError("denied")):
            result = routing_eval._workspace_check_evidence(0, {"kind": "file_absent", "path": "inaccessible.txt"}, target)
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "access_error")
        self.assertEqual(result["error_kind"], "PermissionError")

    def test_workspace_state_failure_does_not_create_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("P10-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = {"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "missing.txt"}]}
            record = routing_eval.extract_trial(_base_rollout("P10-T01", workspace, skill_visible=False), pathlib.Path("p10.jsonl"), manifest)
        self.assertIsNone(record["eligible_boundary_index"])
        self.assertFalse(record["post_condition_passed"])

    def test_prepare_freezes_declared_post_condition_rule(self):
        case = _case("P01", lane="validation")
        case["post_condition"] = self._post_condition()
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["post_condition"], self._post_condition())
        self.assertEqual(rows[0]["post_condition"], rows[1]["post_condition"])

    def test_extract_trial_uses_latest_declared_tool_marker_separate_from_command_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("P02-T01", "M", workspace)
            manifest["post_condition"] = self._post_condition()
            rows = _base_rollout("P02-T01", workspace, skill_visible=False) + _failed_command_rows() + [_mcp_row()]
            rows += [
                _tool("verify1", "tools.shell_command({command:'verify-task'})", "2026-08-14T00:00:05Z"),
                _output("verify1", "POST-CONDITION: FAIL", "2026-08-14T00:00:06Z"),
                _tool("verify2", "tools.shell_command({command:'verify-task'})", "2026-08-14T00:00:07Z"),
                _output("verify2", "POST-CONDITION: PASS", "2026-08-14T00:00:08Z"),
            ]
            record = routing_eval.extract_trial(rows, pathlib.Path("p02.jsonl"), manifest)
        self.assertEqual(record["first_command_exit_code"], 7)
        self.assertIs(record["post_condition_passed"], True)
        self.assertEqual(record["post_condition_evidence_index"], len(rows) - 1)

    def test_post_condition_false_and_missing_remain_distinct_and_ignore_prose(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = pathlib.Path(temp_dir)
            manifest = _manifest_row("P03-T01", "M", workspace, group="should_not_trigger", detector={"kind": "none"})
            manifest["post_condition"] = self._post_condition()
            false_rows = _base_rollout("P03-T01", workspace, skill_visible=False) + [
                _output("verify", "POST-CONDITION: FAIL", "2026-08-14T00:00:05Z")
            ]
            false_record = routing_eval.extract_trial(false_rows, pathlib.Path("p03-false.jsonl"), manifest)
            missing_rows = _base_rollout("P03-T01", workspace, skill_visible=False) + [
                _row("event_msg", {"type": "agent_message", "message": "POST-CONDITION: PASS"}, "2026-08-14T00:00:05Z")
            ]
            missing_record = routing_eval.extract_trial(missing_rows, pathlib.Path("p03-missing.jsonl"), manifest)
        self.assertIs(false_record["post_condition_passed"], False)
        self.assertIsNone(missing_record["post_condition_passed"])
        self.assertIsNone(missing_record["post_condition_evidence_index"])

    def test_prepare_rejects_ambiguous_post_condition_markers(self):
        case = _case("P04")
        case["post_condition"] = {
            "kind": "tool_output_marker",
            "pass_marker": "SAME",
            "fail_marker": "SAME",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "post-condition"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)


class RoutingEvalReviewReportCompletenessTests(unittest.TestCase):
    def test_report_separates_general_error_labels_from_reliability_causality(self):
        records = [
            _score_record(
                "M01", arm="S", mcp_intervention_count=1,
                wrong_repair=True, reliability_caused_wrong_repair=False,
                false_completion=False, reliability_caused_false_completion=False,
            ),
            _score_record(
                "M02", arm="S", mcp_intervention_count=1,
                wrong_repair=False, reliability_caused_wrong_repair=False,
                false_completion=True, reliability_caused_false_completion=False,
            ),
        ]
        report = routing_eval.score_records(records)["arms"]["S"]
        adjudication = report["adjudication"]
        self.assertEqual(adjudication["wrong_repair_count"], 1)
        self.assertEqual(adjudication["wrong_repair_reviewed"], 2)
        self.assertEqual(adjudication["wrong_repair_review_coverage"], 1.0)
        self.assertEqual(adjudication["false_completion_count"], 1)
        self.assertEqual(adjudication["false_completion_reviewed"], 2)
        self.assertEqual(adjudication["false_completion_review_coverage"], 1.0)
        self.assertEqual(adjudication["reliability_caused_wrong_repair_count"], 0)
        self.assertEqual(adjudication["reliability_caused_false_completion_count"], 0)
        self.assertEqual(report["gates"]["reliability_caused_wrong_repair"], "PASS")
        self.assertEqual(report["gates"]["reliability_caused_false_completion"], "PASS")


class RoutingEvalReviewPostConditionEndToEndTests(unittest.TestCase):
    def test_prepare_collect_score_uses_evaluator_workspace_state(self):
        case = _case("P05", lane="validation")
        case["post_condition"] = {
            "kind": "workspace_state",
            "mode": "all",
            "checks": [{"kind": "file_sha256", "path": "result.txt", "expected_sha256": hashlib.sha256(b"READY\n").hexdigest()}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            manifest = routing_eval.prepare_campaign([case], root / "campaign", trials=1, seed=5)
            sessions = root / "sessions"
            sessions.mkdir()
            for row in manifest:
                workspace = pathlib.Path(row["workspace"])
                workspace.mkdir(parents=True, exist_ok=False)
                workspace.joinpath("result.txt").write_bytes(b"READY\n" if row["arm"] == "S" else b"STALE\n")
                rows = _base_rollout(row["case_key"], workspace, skill_visible=row["arm"] == "S")
                rows += _failed_command_rows()
                if row["arm"] == "S":
                    rows += [_skill_row()]
                rows += [_mcp_row(), _output("verify", "POST-CONDITION: PASS", "2026-08-14T00:00:05Z")]
                routing_eval.trigger_eval.write_jsonl(sessions / f"rollout-{row['sequence']}.jsonl", rows)
            records = routing_eval.collect_rollouts(sessions, manifest)
            report = routing_eval.score_records(records)
        self.assertEqual({row["arm"]: row["post_condition_passed"] for row in records}, {"S": True, "M": False})
        self.assertTrue(all(row["post_condition_evidence_source"] == "evaluator_workspace" for row in records))
        self.assertEqual(report["arms"]["S"]["lanes"]["admission"]["deterministic_post_condition_completion_rate"], 1.0)
        self.assertEqual(report["arms"]["M"]["lanes"]["admission"]["deterministic_post_condition_completion_rate"], 0.0)
