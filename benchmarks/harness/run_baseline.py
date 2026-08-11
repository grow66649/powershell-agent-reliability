import json
import pathlib
import subprocess
import sys
import time

WORKER = pathlib.Path(__file__).with_name("fixture_worker.py")
FIXTURES = [f"PSR-{i:03d}" for i in range(1, 9)]


def run_fixture(fixture_id: str) -> dict:
    started = time.perf_counter()
    try:
        cp = subprocess.run(
            [sys.executable, "-u", str(WORKER), fixture_id],
            text=True,
            capture_output=True,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        return {
            "id": fixture_id,
            "runner_timeout": True,
            "runner_wall_ms": round((time.perf_counter() - started) * 1000, 3),
            "reproduced": False,
            "cleanup_pass": False,
        }
    if cp.returncode != 0:
        return {
            "id": fixture_id,
            "runner_timeout": False,
            "runner_exit_code": cp.returncode,
            "runner_stderr": cp.stderr[:512],
            "reproduced": False,
            "cleanup_pass": False,
        }
    row = json.loads(cp.stdout)
    row["runner_timeout"] = False
    row["runner_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return row

def main() -> int:
    trials_per_fixture = 3
    results = {}
    for fixture_id in FIXTURES:
        trials = [run_fixture(fixture_id) for _ in range(trials_per_fixture)]
        results[fixture_id] = {
            "trials": trials,
            "all_reproduced": all(t.get("reproduced") is True for t in trials),
            "all_cleanup": all(t.get("cleanup_pass") is True for t in trials),
            "no_runner_timeout": all(t.get("runner_timeout") is False for t in trials),
        }
    report = {
        "schema_version": 1,
        "trials_per_fixture": trials_per_fixture,
        "runner": "one fixture worker process per trial",
        "results": results,
        "all_reproduced": all(v["all_reproduced"] for v in results.values()),
        "all_cleanup": all(v["all_cleanup"] for v in results.values()),
        "no_runner_timeout": all(v["no_runner_timeout"] for v in results.values()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_reproduced"] and report["all_cleanup"] and report["no_runner_timeout"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
