import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

fixture_id = sys.argv[1]
root = pathlib.Path(tempfile.mkdtemp(prefix=f"{fixture_id.lower()}-"))


def run(shell, script, cwd=None, timeout=3):
    started = time.perf_counter()
    try:
        cp = subprocess.run([shell, "-NoProfile", "-Command", script], cwd=cwd, text=True, capture_output=True, timeout=timeout)
        return {
            "exit_code": cp.returncode,
            "stdout": cp.stdout[:512],
            "stderr": cp.stderr[:512],
            "timed_out": False,
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "", "timed_out": True, "wall_ms": round((time.perf_counter() - started) * 1000, 3)}


try:
    if fixture_id == "PSR-001":
        r = run("powershell.exe", "$x=$null; $nested=\"Write-Output '$x'\"; $out=& powershell.exe -NoProfile -NonInteractive -Command $nested; Write-Output $out; exit $LASTEXITCODE")
        result = {"id": fixture_id, "class": "QUOTING_EXPANSION", "observed": r, "reproduced": r["exit_code"] == 0 and r["stdout"].strip() == ""}
    elif fixture_id == "PSR-002":
        (root / "expected").mkdir(); (root / "wrong").mkdir(); (root / "expected" / "artifact.txt").write_text("ok", encoding="utf-8")
        r = run("powershell.exe", "Get-Content -LiteralPath .\\artifact.txt", cwd=str(root / "wrong"))
        result = {"id": fixture_id, "class": "CWD_PATH_IDENTITY", "observed": r, "reproduced": r["exit_code"] != 0}
    elif fixture_id == "PSR-003":
        script = "'{}' | ConvertFrom-Json -AsHashtable | Out-Null"
        a = run("powershell.exe", script); b = run("pwsh.exe", script)
        result = {"id": fixture_id, "class": "SHELL_VERSION_MISMATCH", "observed": {"powershell": a, "pwsh": b}, "reproduced": a["exit_code"] != 0 and b["exit_code"] == 0}
    elif fixture_id == "PSR-004":
        r = run("powershell.exe", "& cmd.exe /d /c 'echo OUT&echo ERR 1>&2&exit /b 7'; exit $LASTEXITCODE")
        result = {"id": fixture_id, "class": "NATIVE_PROCESS_OUTCOME", "observed": r, "reproduced": r["exit_code"] == 7 and "OUT" in r["stdout"] and "ERR" in r["stderr"]}
    elif fixture_id == "PSR-005":
        r = run("powershell.exe", "Start-Sleep -Seconds 5", timeout=0.4)
        result = {"id": fixture_id, "class": "TIMEOUT_CANCELLATION", "observed": r, "reproduced": r["timed_out"] is True}
    elif fixture_id == "PSR-006":
        required = root / "required.txt"
        r = run("powershell.exe", "exit 0", cwd=str(root))
        post = required.exists()
        result = {"id": fixture_id, "class": "POST_CONDITION_FALSE_POSITIVE", "observed": {**r, "post_condition": post}, "reproduced": r["exit_code"] == 0 and not post}
    elif fixture_id == "PSR-007":
        produced = root / "produced.txt"; lit = str(produced).replace("'", "''")
        r = run("powershell.exe", f"Set-Content -LiteralPath '{lit}' -Value ok; exit 7", cwd=str(root))
        post = produced.exists()
        result = {"id": fixture_id, "class": "POST_CONDITION_FALSE_NEGATIVE", "observed": {**r, "post_condition": post}, "reproduced": r["exit_code"] == 7 and post}
    elif fixture_id == "PSR-008":
        a = root / "a"; b = root / "b"; a.mkdir(); b.mkdir()
        (a / "psrprobe.cmd").write_text("@echo A\r\n", encoding="ascii"); (b / "psrprobe.cmd").write_text("@echo B\r\n", encoding="ascii")
        al = str(a).replace("'", "''"); bl = str(b).replace("'", "''")
        script = f"$old=$env:PATH; $env:PATH='{al};'+$old; $one=(Get-Command psrprobe.cmd).Source; $env:PATH='{bl};'+$old; $two=(Get-Command psrprobe.cmd).Source; Write-Output $one; Write-Output $two"
        r = run("powershell.exe", script)
        lines = [x.strip() for x in r["stdout"].splitlines() if x.strip()]
        changed = len(lines) >= 2 and lines[0] != lines[1]
        result = {"id": fixture_id, "class": "ENVIRONMENT_STALENESS", "observed": {**r, "resolution_changed": changed}, "reproduced": changed}
    else:
        raise SystemExit(f"unknown fixture {fixture_id}")
finally:
    cleanup_root = str(root)
    shutil.rmtree(root, ignore_errors=True)

result["cleanup_pass"] = not pathlib.Path(cleanup_root).exists()
print(json.dumps(result, ensure_ascii=False))
