#!/usr/bin/env python3
"""One command: static checks, every automated test, then a live Studionet run, and one combined report.

    python scripts/run_report.py                 # everything, including the live Studionet run
    python scripts/run_report.py --fast          # live run without the time-gated phase (saves roughly 20 minutes)
    python scripts/run_report.py --no-live       # static checks and tests only
    python scripts/run_report.py --skip-tests    # only static checks and the live run

Phases
  1. static   - the GenVM linter, and a check that artifacts/primacy.abi.json matches the contract
  2. tests    - Direct Mode suite (normal, adversarial, fuzz) and the script rehearsals on a local simulator
  3. live     - scripts/live_e2e.py against Studionet with real validators

The combined report is written to reports/primacy-report-<time>.md and .json. Exit status is 0 only when
every phase that ran passed; 2 means the live run could not start (for example, the network was unreachable).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, GENVM_VERSION=os.environ.get("GENVM_VERSION", "v0.2.16"))


def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), env=ENV, capture_output=True, text=True, timeout=timeout)


def say(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}", flush=True)


def tool(name: str) -> List[str]:
    """Prefer a console script next to this interpreter, then the PATH."""
    candidate = Path(sys.executable).parent / name
    return [str(candidate)] if candidate.exists() else [name]


# ----------------------------------------------------------------------------
# Phase 1: static
# ----------------------------------------------------------------------------


def phase_static() -> Dict[str, Any]:
    say("static: genvm-lint check")
    out: Dict[str, Any] = {"name": "static", "checks": []}
    lint = run(tool("genvm-lint") + ["check", "contracts/primacy.py"])
    out["checks"].append({"name": "genvm-lint check contracts/primacy.py", "ok": lint.returncode == 0,
                          "detail": (lint.stdout + lint.stderr).strip()[-600:]})
    say("static: ABI drift check")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "abi.json"
        schema = run(tool("genvm-lint") + ["schema", "contracts/primacy.py", "--output", str(target)])
        committed = ROOT / "artifacts" / "primacy.abi.json"
        if schema.returncode != 0 or not target.exists():
            out["checks"].append({"name": "ABI matches the contract", "ok": False, "detail": (schema.stdout + schema.stderr)[-400:]})
        elif not committed.exists():
            out["checks"].append({"name": "ABI matches the contract", "ok": False, "detail": "artifacts/primacy.abi.json is missing"})
        else:
            same = json.loads(target.read_text()) == json.loads(committed.read_text())
            out["checks"].append({"name": "artifacts/primacy.abi.json matches the contract", "ok": same,
                                  "detail": "" if same else "regenerate with: genvm-lint schema contracts/primacy.py --output artifacts/primacy.abi.json"})
    out["ok"] = all(check["ok"] for check in out["checks"])
    return out


# ----------------------------------------------------------------------------
# Phase 2: tests
# ----------------------------------------------------------------------------


def count_marker(marker: str) -> int:
    result = run([sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-m", marker, "-p", "no:cacheprovider"])
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def phase_tests() -> Dict[str, Any]:
    say("tests: pytest tests (Direct Mode suite and script rehearsals)")
    out: Dict[str, Any] = {"name": "tests"}
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        started = time.time()
        proc = run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"])
        out["seconds"] = round(time.time() - started, 1)
        out["returncode"] = proc.returncode
        out["tail"] = "\n".join(proc.stdout.strip().splitlines()[-12:])
        files: Dict[str, Dict[str, Any]] = {}
        if junit.exists():
            root = ET.parse(junit).getroot()
            for case in root.iter("testcase"):
                name = case.get("classname", "?").split(".")[-1]
                entry = files.setdefault(name, {"tests": 0, "failed": 0, "skipped": 0, "seconds": 0.0})
                entry["tests"] += 1
                entry["seconds"] += float(case.get("time", 0))
                if case.find("failure") is not None or case.find("error") is not None:
                    entry["failed"] += 1
                if case.find("skipped") is not None:
                    entry["skipped"] += 1
        out["files"] = {name: {**entry, "seconds": round(entry["seconds"], 1)} for name, entry in sorted(files.items())}
    out["total"] = sum(entry["tests"] for entry in out["files"].values())
    out["failed"] = sum(entry["failed"] for entry in out["files"].values())
    out["skipped"] = sum(entry["skipped"] for entry in out["files"].values())
    out["adversarial"] = count_marker("adversarial")
    out["fuzz"] = count_marker("fuzz")
    out["rehearsal"] = count_marker("rehearsal")
    out["ok"] = out["returncode"] == 0 and out["failed"] == 0 and out["total"] > 0
    return out


# ----------------------------------------------------------------------------
# Phase 3: live
# ----------------------------------------------------------------------------


def phase_live(extra: List[str]) -> Dict[str, Any]:
    say("live: scripts/live_e2e.py")
    out: Dict[str, Any] = {"name": "live"}
    started = time.time()
    before = {p.name for p in (ROOT / "reports").glob("live-e2e-*.json")} if (ROOT / "reports").exists() else set()
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "live_e2e.py"), *extra], cwd=str(ROOT), env=ENV)
    out["returncode"] = proc.returncode
    out["seconds"] = round(time.time() - started, 1)
    fresh = sorted(p for p in (ROOT / "reports").glob("live-e2e-*.json") if p.name not in before)
    if fresh:
        out["json"] = str(fresh[-1])
        out["markdown"] = str(fresh[-1].with_suffix(".md"))
        out["data"] = json.loads(fresh[-1].read_text())
    out["ok"] = proc.returncode == 0
    return out


# ----------------------------------------------------------------------------
# Combined report
# ----------------------------------------------------------------------------


def mark(ok: Optional[bool]) -> str:
    return "not run" if ok is None else ("PASS" if ok else "FAIL")


def render(phases: Dict[str, Optional[Dict[str, Any]]], stamp: str, args: argparse.Namespace) -> str:
    static, tests, live = phases["static"], phases["tests"], phases["live"]
    lines: List[str] = []
    add = lines.append
    add(f"# Primacy report {stamp}")
    add("")
    add("| Phase | Result | Detail |")
    add("|---|---|---|")
    add(f"| Static checks | {mark(static and static['ok'])} | linter and ABI drift |")
    if tests:
        add(f"| Automated tests | {mark(tests['ok'])} | {tests['total']} tests, {tests['failed']} failed, "
            f"{tests['skipped']} skipped, {tests['seconds']}s |")
    else:
        add("| Automated tests | not run | |")
    if live:
        verdict = live.get("data", {}).get("verdict", "NO REPORT")
        counts = live.get("data", {}).get("counts", {})
        add(f"| Live Studionet run | {verdict} | hard passed {counts.get('hard_pass', '-')}, hard failed "
            f"{counts.get('hard_fail', '-')}, model aligned {counts.get('soft_aligned', '-')}, "
            f"model diverged {counts.get('soft_diverged', '-')}, {live['seconds']}s |")
    else:
        add("| Live Studionet run | not run | |")
    add("")

    if static:
        add("## Static checks")
        add("")
        for check in static["checks"]:
            add(f"- **{mark(check['ok'])}** {check['name']}" + (f": `{check['detail'][:200]}`" if check["detail"] and not check["ok"] else ""))
        add("")

    if tests:
        add("## Automated tests")
        add("")
        add(f"Of the {tests['total']} tests, {tests['adversarial']} are tagged adversarial, {tests['fuzz']} are seeded fuzz "
            f"runs and {tests['rehearsal']} rehearse the live script on a local simulator.")
        add("")
        add("| File | Tests | Failed | Skipped | Seconds |")
        add("|---|---|---|---|---|")
        for name, entry in tests["files"].items():
            add(f"| {name} | {entry['tests']} | {entry['failed']} | {entry['skipped']} | {entry['seconds']} |")
        if not tests["ok"]:
            add("")
            add("```")
            add(tests["tail"])
            add("```")
        add("")

    if live:
        add("## Live Studionet run")
        add("")
        if "markdown" in live and Path(live["markdown"]).exists():
            add(f"Full report: `{Path(live['markdown']).relative_to(ROOT)}`")
            data = live["data"]
            add("")
            add(f"- Contract: `{data['meta'].get('contract', 'not deployed')}`")
            add(f"- Verdict: **{data['verdict']}**" + (f" ({data['aborted']})" if data.get("aborted") else ""))
            for gap in data.get("coverage_gaps", []):
                add(f"- Coverage gap: {gap}")
            problems = [s for s in data["steps"] if s["status"] in ("FAIL", "ERROR")]
            diverged = [s for s in data["steps"] if s["status"] == "DIVERGED"]
            if problems:
                add("")
                add("Failed or errored steps:")
                for step in problems:
                    add(f"- {step['scenario']}: {step['title']} (expected {step['expected']}, observed {step['observed']})")
            if diverged:
                add("")
                add("Model or environment expectations that diverged (informational):")
                for step in diverged:
                    add(f"- {step['scenario']}: {step['title']} (expected {step['expected']}, observed {step['observed']})")
            rows = data.get("tables", {}).get("Adjudications", [])
            if rows:
                add("")
                add("Model verdicts:")
                add("")
                add("| Finding | Status | In scope | Actionable | Duplicate of | Confidence |")
                add("|---|---|---|---|---|---|")
                for row in rows:
                    add(f"| {row['finding']} | {row['status']} | {row['in_scope']} | {row['actionable']} | {row['duplicate_of']} | {row['confidence']} |")
        else:
            add("The live script did not produce a report. See the console output above.")
        add("")
    elif args.no_live:
        add("## Live Studionet run")
        add("")
        add("Not run (`--no-live`).")
        add("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run static checks, tests and the live Studionet E2E, then write one report.")
    parser.add_argument("--no-live", action="store_true", help="skip the live Studionet run")
    parser.add_argument("--skip-tests", action="store_true", help="skip pytest")
    parser.add_argument("--fast", action="store_true", help="live run without the time-gated phase")
    parser.add_argument("--rpc", default=None, help="Studionet RPC endpoint override")
    parser.add_argument("--tx-timeout", type=int, default=None)
    args = parser.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    phases: Dict[str, Optional[Dict[str, Any]]] = {"static": None, "tests": None, "live": None}
    phases["static"] = phase_static()
    if not args.skip_tests:
        phases["tests"] = phase_tests()
    live_args: List[str] = []
    if args.fast:
        live_args.append("--fast")
    if args.rpc:
        live_args += ["--rpc", args.rpc]
    if args.tx_timeout:
        live_args += ["--tx-timeout", str(args.tx_timeout)]

    gate_ok = phases["static"]["ok"] and (phases["tests"] is None or phases["tests"]["ok"])
    if not args.no_live:
        if gate_ok:
            phases["live"] = phase_live(live_args)
        else:
            say("live run skipped: the static checks or tests failed, so Studionet time would be wasted")

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    markdown = render(phases, stamp, args)
    md_path = reports / f"primacy-report-{stamp}.md"
    md_path.write_text(markdown, encoding="utf-8")
    json_path = reports / f"primacy-report-{stamp}.json"
    json_path.write_text(json.dumps({k: (None if v is None else {kk: vv for kk, vv in v.items() if kk != "data"}) for k, v in phases.items()},
                                    indent=2, default=str), encoding="utf-8")
    print()
    print(markdown.split("## ")[0])
    print(f"Combined report: {md_path}")

    ran = [phase for phase in phases.values() if phase]
    if not gate_ok:
        return 1
    live = phases["live"]
    if live and live["returncode"] == 2:
        return 2
    if args.no_live:
        return 0 if all(phase["ok"] for phase in ran) else 1
    return 0 if all(phase["ok"] for phase in ran) and live is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
