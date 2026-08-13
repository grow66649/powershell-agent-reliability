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
        "prompt": "Work only in the current workspace.\n[CASE-ID: {case_key}]",
        "files": {
            "task.ps1": "exit 7\n",
            "nested/input.txt": "same fixture\n",
        },
        "expected_first_command_fragment": "pwsh.exe -NoProfile -File .\\task.ps1",
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
