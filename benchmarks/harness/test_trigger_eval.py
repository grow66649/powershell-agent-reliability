import json
import pathlib
import tempfile
import unittest

import trigger_eval


def _row(record_type, payload, timestamp="2026-08-13T00:00:00Z"):
    return {"timestamp": timestamp, "type": record_type, "payload": payload}


class TriggerEvalRolloutTests(unittest.TestCase):
    def test_extracts_skill_selection_after_first_failed_command(self):
        rows = [
            _row("session_meta", {"session_id": "s1", "originator": "Codex Desktop", "cli_version": "x"}),
            _row("turn_context", {"model": "gpt-test", "effort": "max", "approval_policy": "never", "sandbox_policy": {"type": "danger-full-access"}}),
            _row("world_state", {"state": {"host_skills": {"body": "- powershell-reliability: candidate"}}}),
            _row("event_msg", {"type": "user_message", "message": "Do the task.\n[CASE-ID: C01-T01]"}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "cmd1", "name": "exec", "input": "tools.shell_command({command:'pwsh.exe -NoProfile -File .\\task.ps1'})"}),
            _row("response_item", {"type": "custom_tool_call_output", "call_id": "cmd1", "output": [{"type": "input_text", "text": "Exit code: 7"}]}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "skill1", "name": "exec", "input": "Get-Content C:\\Users\\u\\.codex\\skills\\powershell-reliability\\SKILL.md -Raw"}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "mcp1", "name": "exec", "input": "tools.mcp__psr_reliability_native__diagnose_failure({exit_code:7})"}),
        ]
        record = trigger_eval.extract_rollout(rows, pathlib.Path("rollout.jsonl"))
        self.assertEqual(record["case_key"], "C01-T01")
        self.assertTrue(record["psr_skill_selected"])
        self.assertFalse(record["psr_skill_selected_before_first_command"])
        self.assertEqual(record["reliability_mcp_calls"], 1)
        self.assertEqual(record["first_command_exit_code"], 7)

    def test_flags_skill_selection_before_first_command(self):
        rows = [
            _row("session_meta", {"session_id": "s2"}),
            _row("event_msg", {"type": "user_message", "message": "Try it.\n[CASE-ID: C02-T01]"}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "skill1", "name": "exec", "input": "Get-Content C:\\Users\\u\\.codex\\skills\\powershell-reliability\\SKILL.md -Raw"}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "cmd1", "name": "exec", "input": "tools.shell_command({command:'pwsh.exe -NoProfile -File .\\task.ps1'})"}),
        ]
        record = trigger_eval.extract_rollout(rows, pathlib.Path("r.jsonl"))
        self.assertTrue(record["psr_skill_selected_before_first_command"])
        self.assertEqual(record["reliability_mcp_calls_before_first_command"], 0)

    def test_records_other_skill_reads_as_collisions(self):
        rows = [
            _row("session_meta", {"session_id": "s3"}),
            _row("event_msg", {"type": "user_message", "message": "Explain it.\n[CASE-ID: C11-T01]"}),
            _row("response_item", {"type": "custom_tool_call", "call_id": "s1", "name": "exec", "input": "Get-Content C:\\Users\\u\\.codex\\skills\\concise-planning\\SKILL.md -Raw"}),
        ]
        record = trigger_eval.extract_rollout(rows, pathlib.Path("r.jsonl"))
        self.assertFalse(record["psr_skill_selected"])
        self.assertEqual(record["selected_other_skills"], ["concise-planning"])


class TriggerEvalScoringTests(unittest.TestCase):
    def test_scores_recall_false_positive_stability_and_timing(self):
        records = [
            {"case_id": "C01", "trial_id": "T01", "group": "should_trigger", "psr_skill_selected": True, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 1, "selected_other_skills": []},
            {"case_id": "C01", "trial_id": "T02", "group": "should_trigger", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": []},
            {"case_id": "C11", "trial_id": "T01", "group": "should_not_trigger", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": []},
            {"case_id": "C12", "trial_id": "T01", "group": "should_not_trigger", "psr_skill_selected": True, "psr_skill_selected_before_first_command": True, "reliability_mcp_calls": 1, "selected_other_skills": ["other-skill"]},
            {"case_id": "C21", "trial_id": "T01", "group": "boundary", "psr_skill_selected": True, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": []},
        ]
        report = trigger_eval.score_records(records)
        self.assertEqual(report["implicit_should_trigger"]["selection_recall"], 0.5)
        self.assertEqual(report["implicit_should_not_trigger"]["false_positive_rate"], 0.5)
        self.assertEqual(report["implicit_overall"]["pre_first_attempt_selection_violations"], 1)
        self.assertEqual(report["implicit_overall"]["collision_trial_count"], 1)
        self.assertEqual(report["boundary"]["trial_count"], 1)

    def test_rejects_duplicate_case_trial_records(self):
        record = {"case_id": "C01", "trial_id": "T01", "group": "should_trigger", "psr_skill_selected": True, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": []}
        with self.assertRaises(ValueError):
            trigger_eval.score_records([record, dict(record)])


class TriggerEvalCampaignTests(unittest.TestCase):
    def test_prepare_campaign_creates_three_trials_per_case(self):
        cases = [
            {"case_id": "C01", "group": "should_trigger", "title": "failure", "prompt": "Run in {workspace}.\n[CASE-ID: {case_key}]", "files": {"task.ps1": "exit 7\n"}, "expected_first_command_fragment": "pwsh.exe -NoProfile -File .\\task.ps1"},
            {"case_id": "C11", "group": "should_not_trigger", "title": "explain", "prompt": "Explain Get-ChildItem.\n[CASE-ID: {case_key}]", "files": {}},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            manifest = trigger_eval.prepare_campaign(cases, root, trials=3, seed=7)
            self.assertEqual(len(manifest), 6)
            self.assertEqual(len({row["case_key"] for row in manifest}), 6)
            self.assertTrue((root / "manifest.jsonl").is_file())
            self.assertEqual(len(list((root / "prompts").glob("*.txt"))), 6)
            self.assertTrue(any((root / "workspaces" / row["case_key"] / "task.ps1").is_file() for row in manifest if row["case_id"] == "C01"))

    def test_prepare_campaign_rejects_blank_expected_first_command_fragment(self):
        cases = [{
            "case_id": "C01", "group": "should_trigger", "title": "failure",
            "prompt": "Run in {workspace}.\n[CASE-ID: {case_key}]", "files": {},
            "expected_first_command_fragment": "   ",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "first command"):
                trigger_eval.prepare_campaign(cases, pathlib.Path(temp_dir), trials=1, seed=7)

    def test_attach_manifest_rejects_malformed_first_command_expectation(self):
        record = {"case_key": "C01-T01", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "first_command_input": "tools.shell_command pwsh.exe"}
        for value in ("   ", 123):
            with self.subTest(value=value):
                manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": value}]
                with self.assertRaisesRegex(ValueError, "first command"):
                    trigger_eval.attach_manifest([record], manifest)

    def test_collect_rejects_malformed_manifest_expectation_without_rollout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            for value in ("   ", 123):
                with self.subTest(value=value):
                    manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": value}]
                    with self.assertRaisesRegex(ValueError, "first command"):
                        trigger_eval.collect_rollouts(root, manifest)

    def test_attach_manifest_labels_collected_records(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": "pwsh.exe"}]
        record = {"case_key": "C01-T01", "psr_skill_selected": True, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 1, "selected_other_skills": [], "first_command_input": "tools.shell_command pwsh.exe"}
        attached = trigger_eval.attach_manifest([record], manifest)
        self.assertEqual(attached[0]["group"], "should_trigger")
        self.assertTrue(attached[0]["first_command_matches_expectation"])

    def test_attach_manifest_rejects_near_first_command_fragment_collision(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": "helper.cmd"}]
        record = {"case_key": "C01-T01", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "first_command_input": r"tools.shell_command pwsh.exe .\not-helper.cmd"}
        attached = trigger_eval.attach_manifest([record], manifest)
        self.assertFalse(attached[0]["first_command_matches_expectation"])

    def test_attach_manifest_accepts_windows_path_separator_variant(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": r"app\build.ps1"}]
        record = {"case_key": "C01-T01", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "first_command_input": "tools.shell_command pwsh.exe -File ./app/build.ps1"}
        attached = trigger_eval.attach_manifest([record], manifest)
        self.assertTrue(attached[0]["first_command_matches_expectation"])

    def test_attach_manifest_rejects_windows_component_character_collisions(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": "helper.cmd"}]
        for command in (r"tools.shell_command pwsh.exe .\not+helper.cmd", r"tools.shell_command pwsh.exe .\not~helper.cmd"):
            with self.subTest(command=command):
                record = {"case_key": "C01-T01", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "first_command_input": command}
                attached = trigger_eval.attach_manifest([record], manifest)
                self.assertFalse(attached[0]["first_command_matches_expectation"])

    def test_attach_manifest_accepts_quote_equivalent_first_command_fragment(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_not_trigger", "title": "native version", "expected_first_command_fragment": "cmd.exe /d /c ver"}]
        record = {"case_key": "C01-T01", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "first_command_input": r'"C:\Program Files\PowerShell\7\pwsh.exe" -Command ''cmd.exe /d /c "ver > native-version.txt"'''}
        attached = trigger_eval.attach_manifest([record], manifest)
        self.assertTrue(attached[0]["first_command_matches_expectation"])

    def test_quote_equivalence_does_not_bypass_component_collision_guard(self):
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", r'pwsh.exe -File .\not+"helper.cmd"'))
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", r'pwsh.exe -File .\not~"helper.cmd"'))

    def test_quote_equivalence_preserves_literal_apostrophe_inside_quoted_token(self):
        actual = "pwsh.exe -File \".\\app\\o'brien.ps1\""
        self.assertFalse(trigger_eval.command_fragment_matches(r"app\obrien.ps1", actual))


    def test_quote_equivalence_preserves_escaped_apostrophe_inside_single_quoted_token(self):
        actual = "pwsh.exe -File '.\\app\\o''brien.ps1'"
        self.assertFalse(trigger_eval.command_fragment_matches(r"app\obrien.ps1", actual))


    def test_quote_equivalence_preserves_literal_apostrophe_inside_unquoted_token(self):
        actual = "pwsh.exe -File .\\app\\o'brien.ps1"
        self.assertFalse(trigger_eval.command_fragment_matches(r"app\obrien.ps1", actual))


    def test_quote_equivalence_preserves_literal_double_quote_inside_single_quoted_token(self):
        actual = "cmd.exe /d /c 'echo a\"b'"
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c echo ab", actual))


    def test_quote_equivalence_preserves_doubled_double_quote_inside_double_quoted_token(self):
        actual = 'cmd.exe /d /c "echo a""b"'
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c echo ab", actual))


    def test_quote_equivalence_preserves_apostrophe_after_space_inside_double_quoted_token(self):
        actual = 'cmd.exe /d /c "echo \'ab"'
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c echo ab", actual))

    def test_quote_equivalence_preserves_double_quote_after_space_inside_single_quoted_token(self):
        actual = "cmd.exe /d /c 'echo \"ab'"
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c echo ab", actual))


    def test_quote_equivalence_ignores_quoted_cmd_text_in_wrapper_justification(self):
        actual = "tools.shell_command({command:'echo wrong', justification:'run cmd.exe /d /c \"ver > native-version.txt\"'})"
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_quote_equivalence_rejects_equals_component_collision(self):
        actual = "tools.shell_command({command:'pwsh.exe -File .\\not=\"helper.cmd\"'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_command_field_still_matches(self):
        actual = "tools.shell_command({command:'helper.cmd', justification:'do it'})"
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_ignores_wrapper_text_inside_metadata_before_command(self):
        actual = """tools.shell_command({justification:'tools.shell_command({command:"helper.cmd"})', command:'echo wrong'})"""
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_supports_execution_field_after_metadata(self):
        actual = "tools.shell_command({justification:'do it', command:'helper.cmd'})"
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_malformed_execution_field_suffix(self):
        actual = "tools.shell_command({command:'helper.cmd'junk})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_quote_equivalence_rejects_suffix_after_closed_quoted_token(self):
        actual = 'cmd.exe /d /c "ver"suffix'
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_raw_command_with_wrapper_marker_inside_quotes_stays_raw(self):
        actual = '''pwsh.exe -Command "Write-Output 'tools.shell_command({'; helper.cmd"'''
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_exec_wrapper_supports_execution_field_after_metadata(self):
        actual = "const r = await tools.exec_command({timeout_ms:1000, cmd:'helper.cmd'}); text(r.output);"
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_double_quoted_structured_command_decodes_escaped_quotes(self):
        actual = r'tools.shell_command({command:"cmd.exe /d /c \"ver > native-version.txt\""})'
        self.assertTrue(trigger_eval.command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_structured_command_decodes_escaped_apostrophe_without_identity_loss(self):
        actual = r"tools.shell_command({command:'not\'helper.cmd'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_duplicate_execution_fields(self):
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({command:'helper.cmd', command:'echo wrong'})"))
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({command:'echo wrong', command:'helper.cmd'})"))

    def test_structured_wrapper_requires_closing_parenthesis(self):
        actual = "tools.shell_command({command:'helper.cmd'}"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_even_backslash_run_closes_field(self):
        actual = r'tools.shell_command({command:"helper.cmd\\", justification:"x"})'
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_odd_backslash_run_preserves_literal_quote_identity(self):
        actual = r'tools.shell_command({command:"not\\\"helper.cmd"})'
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_empty_metadata_values(self):
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({justification:, command:'helper.cmd'})"))
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({command:'helper.cmd', justification:})"))

    def test_quote_equivalence_rejects_colon_component_collision(self):
        actual = r'pwsh.exe -File .\not:"helper.cmd"'
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_supports_observed_quoted_property_names(self):
        actual = r'tools.shell_command({"justification":"do it","command":"helper.cmd"})'
        self.assertTrue(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_shell_call_detection_ignores_wrapper_marker_inside_other_tool_string(self):
        actual = 'tools.read_file({path:"literal tools.shell_command({ marker"})'
        self.assertFalse(trigger_eval._is_shell_call(actual))

    def test_shell_call_detection_ignores_wrapper_marker_inside_template_literal(self):
        actual = 'tools.other({value:`literal tools.shell_command({ marker`})'
        self.assertFalse(trigger_eval._is_shell_call(actual))


    def test_escaped_literal_quote_suffix_does_not_create_right_boundary(self):
        actual = r'tools.shell_command({command:"cmd.exe /d /c \"ver\\\"suffix\""})'
        self.assertFalse(trigger_eval.command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_structured_wrapper_requires_lexical_case_sensitive_tool_name(self):
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "nottools.shell_command({command:'helper.cmd'})"))
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "TOOLS.SHELL_COMMAND({command:'helper.cmd'})"))

    def test_structured_wrapper_rejects_multiple_execution_wrappers(self):
        actual = "tools.shell_command({command:'helper.cmd'}); tools.shell_command({command:'echo wrong'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_whitespace_split_metadata_scalar(self):
        actual = "tools.shell_command({justification:foo bar, command:'helper.cmd'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))


    def test_raw_fragment_rejects_whitespace_boundaries_inside_larger_quoted_token(self):
        actual = 'pwsh.exe -File ".\\not helper.cmd suffix"'
        self.assertFalse(trigger_eval.raw_command_fragment_matches("helper.cmd", actual))

    def test_raw_fragment_rejects_long_backslash_run_before_literal_quote_suffix(self):
        actual = 'cmd.exe /d /c "ver\\\\"suffix"'
        self.assertFalse(trigger_eval.raw_command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_structured_wrapper_execution_property_is_case_sensitive(self):
        actual = "tools.shell_command({COMMAND:'helper.cmd'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_invalid_unquoted_metadata_scalar(self):
        actual = "tools.shell_command({justification:@, command:'helper.cmd'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))

    def test_structured_wrapper_rejects_nested_execution_wrapper_in_metadata(self):
        actual = "tools.shell_command({command:'helper.cmd', justification:tools.exec_command({cmd:'echo wrong'})})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))


    def test_structured_wrapper_rejects_unsupported_complex_metadata_values(self):
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({metadata:{x:1}, command:'helper.cmd'})"))
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", "tools.shell_command({command:'helper.cmd', metadata:[1,2]})"))


    def test_shell_call_detection_preserves_legacy_unstructured_input(self):
        actual = "tools.shell_command pwsh.exe -File helper.cmd"
        self.assertTrue(trigger_eval._is_shell_call(actual))

    def test_structured_wrapper_rejects_template_interpolation_nested_execution_wrapper(self):
        actual = "tools.shell_command({justification:`${tools.exec_command({cmd:'echo wrong'})}`, command:'helper.cmd'})"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))


    def test_cmd_quote_variant_rejects_arbitrary_quoted_suffix(self):
        actual = 'cmd.exe /d /c "ver suffix"'
        self.assertFalse(trigger_eval.raw_command_fragment_matches("cmd.exe /d /c ver", actual))

    def test_wrapper_like_pseudo_name_does_not_fall_back_to_raw_matching(self):
        actual = "tools.shell_command_extra helper.cmd"
        self.assertFalse(trigger_eval.command_fragment_matches("helper.cmd", actual))


class TriggerEvalDatasetContractTests(unittest.TestCase):
    def test_load_cases_rejects_malformed_first_command_expectation(self):
        case = {"case_id": "C01", "group": "should_trigger", "title": "failure", "prompt": "Do task", "expected_first_command_fragment": 123}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "cases.json"
            path.write_text(json.dumps([case]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "first command"):
                trigger_eval.load_cases(path)

    def test_repository_dataset_has_balanced_implicit_groups(self):
        cases_path = pathlib.Path(__file__).resolve().parents[1] / "trigger_eval" / "cases.json"
        cases = trigger_eval.load_cases(cases_path)
        counts = {group: sum(case["group"] == group for case in cases) for group in trigger_eval.VALID_GROUPS}
        self.assertEqual(len(cases), 25)
        self.assertEqual(counts, {"should_trigger": 10, "should_not_trigger": 10, "boundary": 5})
        for case in cases:
            lower = case["prompt"].lower()
            self.assertNotIn("powershell-reliability", lower)
            self.assertNotIn("load the skill", lower)
            self.assertIn("[case-id: {case_key}]", lower)


class TriggerEvalEnvironmentTests(unittest.TestCase):
    def test_score_flags_model_or_effort_drift(self):
        base = {"group": "should_not_trigger", "psr_skill_selected": False, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 0, "selected_other_skills": [], "psr_available_in_catalog": True, "cli_version": "0.1", "approval_policy": "never", "sandbox_type": "danger-full-access"}
        first = dict(base, case_id="C11", trial_id="T01", model="gpt-a", effort="max")
        second = dict(base, case_id="C12", trial_id="T01", model="gpt-b", effort="max")
        report = trigger_eval.score_records([first, second])
        self.assertFalse(report["environment_consistency"]["constant"])
        self.assertEqual(report["environment_consistency"]["model"], ["gpt-a", "gpt-b"])


class TriggerEvalPrivacyTests(unittest.TestCase):
    def test_manifest_attachment_removes_raw_command_text(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": "pwsh.exe"}]
        record = {"case_key": "C01-T01", "psr_skill_selected": True, "psr_skill_selected_before_first_command": False, "reliability_mcp_calls": 1, "selected_other_skills": [], "first_command_input": "tools.shell_command({command:'pwsh.exe secret-path'})"}
        attached = trigger_eval.attach_manifest([record], manifest)[0]
        self.assertNotIn("first_command_input", attached)
        self.assertRegex(attached["first_command_input_sha256"], r"^[0-9A-F]{64}$")

if __name__ == "__main__":
    unittest.main()


class TriggerEvalLiteralPromptTests(unittest.TestCase):
    def test_prepare_campaign_preserves_literal_braces_in_prompt(self):
        cases = [{"case_id": "C99", "group": "boundary", "title": "brace", "prompt": "Explain token '}' and use {workspace}.\n[CASE-ID: {case_key}]", "files": {}}]
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = trigger_eval.prepare_campaign(cases, pathlib.Path(temp_dir), trials=1, seed=1)
        self.assertIn("token '}'", manifest[0]["prompt"])
        self.assertIn("C99-T01", manifest[0]["prompt"])


class TriggerEvalCollectorRobustnessTests(unittest.TestCase):
    def test_collect_ignores_invalid_unrelated_rollout_files(self):
        manifest = [{"case_key": "C01-T01", "case_id": "C01", "trial_id": "T01", "group": "should_trigger", "title": "failure", "expected_first_command_fragment": "pwsh.exe", "sequence": 1}]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            (root / "rollout-bad.jsonl").write_text('{"type":"event_msg","payload":"unterminated', encoding="utf-8")
            records = trigger_eval.collect_rollouts(root, manifest)
        self.assertEqual(records, [])


class TriggerEvalCampaignOrderingTests(unittest.TestCase):
    def test_prepare_campaign_stratifies_repetitions_by_round(self):
        cases = [
            {"case_id": f"C{i:02d}", "group": "boundary", "title": str(i), "prompt": "Do it.\n[CASE-ID: {case_key}]", "files": {}}
            for i in range(1, 6)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = trigger_eval.prepare_campaign(cases, pathlib.Path(temp_dir), trials=3, seed=11)
        first_round = manifest[:5]
        second_round = manifest[5:10]
        self.assertEqual({row["case_id"] for row in first_round}, {f"C{i:02d}" for i in range(1, 6)})
        self.assertEqual({row["trial_id"] for row in first_round}, {"T01"})
        self.assertEqual({row["trial_id"] for row in second_round}, {"T02"})
