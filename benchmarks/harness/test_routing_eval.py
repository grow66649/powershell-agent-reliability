import json
import pathlib
import tempfile
import unittest

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
            rows = routing_eval.prepare_campaign([_case()], root, trials=1, seed=7)
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["arm"] for row in rows}, {"S", "M"})
            by_arm = {row["arm"]: row for row in rows}
            self.assertEqual(by_arm["S"]["prompt_sha256"], by_arm["M"]["prompt_sha256"])
            self.assertEqual(by_arm["S"]["fixture_sha256"], by_arm["M"]["fixture_sha256"])
            self.assertNotEqual(by_arm["S"]["workspace_sha256"], by_arm["M"]["workspace_sha256"])
            self.assertEqual(by_arm["S"]["prompt_path"], by_arm["M"]["prompt_path"])
            prompt = pathlib.Path(by_arm["S"]["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("[CASE-ID: R01-T01]", prompt)
            for forbidden in ("powershell-reliability", "Reliability MCP", "arm S", "arm M"):
                self.assertNotIn(forbidden.lower(), prompt.lower())
            required = {
                "case_key", "case_id", "trial_id", "lane", "group", "arm", "sequence",
                "prompt_path", "prompt_sha256", "workspace", "workspace_sha256",
                "fixture_sha256", "expected_first_command_fragment", "boundary_detector",
            }
            self.assertTrue(required.issubset(by_arm["S"]))
            for relative in ("task.ps1", "nested/input.txt"):
                s_bytes = (pathlib.Path(by_arm["S"]["workspace"]) / relative).read_bytes()
                m_bytes = (pathlib.Path(by_arm["M"]["workspace"]) / relative).read_bytes()
                self.assertEqual(s_bytes, m_bytes)

    def test_prepare_campaign_rejects_workspace_prompt_token(self):
        case = _case()
        case["prompt"] = "Run in {workspace}.\n[CASE-ID: {case_key}]"
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "workspace"):
                routing_eval.prepare_campaign([case], pathlib.Path(temp_dir), trials=1, seed=7)

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
