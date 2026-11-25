"""Result recording and Markdown/JSON rendering for scripts/live_e2e.py."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HARD = "hard"      # a rule the contract itself enforces: must hold on every network
SOFT = "soft"      # depends on a language model or on the environment: reported, never fails the run
INFO = "info"      # recorded for the reader only

PASS, FAIL = "PASS", "FAIL"
ALIGNED, DIVERGED = "ALIGNED", "DIVERGED"
NOTE, ERROR, SKIP = "NOTE", "ERROR", "SKIP"


@dataclass
class Step:
    scenario: str
    title: str
    kind: str
    status: str
    expected: str = ""
    observed: str = ""
    tx: str = ""
    seconds: float = 0.0
    note: str = ""


@dataclass
class Tx:
    label: str
    method: str
    sender: str
    tx_hash: str
    ok: bool
    status: str
    detail: str
    seconds: float
    agree: str = ""


def _cell(value: Any) -> str:
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= 220 else text[:217] + "..."


def _short(value: str, head: int = 10, tail: int = 6) -> str:
    return value if len(value) <= head + tail + 3 else f"{value[:head]}...{value[-tail:]}"


@dataclass
class Report:
    meta: Dict[str, Any] = field(default_factory=dict)
    steps: List[Step] = field(default_factory=list)
    txs: List[Tx] = field(default_factory=list)
    tables: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None
    aborted: str = ""
    coverage_gaps: List[str] = field(default_factory=list)
    partial_path: str = ""

    # ---- recording -----------------------------------------------------

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        self.save_partial()
        return step

    def add_tx(self, tx: Tx) -> None:
        self.txs.append(tx)

    def table(self, name: str, rows: List[Dict[str, Any]]) -> None:
        self.tables[name] = rows

    def note(self, text: str) -> None:
        self.notes.append(text)

    # ---- summary -------------------------------------------------------

    def counts(self) -> Dict[str, int]:
        out = {"hard_pass": 0, "hard_fail": 0, "soft_aligned": 0, "soft_diverged": 0, "errors": 0, "skipped": 0, "info": 0}
        for step in self.steps:
            if step.status == PASS:
                out["hard_pass"] += 1
            elif step.status == FAIL:
                out["hard_fail"] += 1
            elif step.status == ALIGNED:
                out["soft_aligned"] += 1
            elif step.status == DIVERGED:
                out["soft_diverged"] += 1
            elif step.status == ERROR:
                out["errors"] += 1
            elif step.status == SKIP:
                out["skipped"] += 1
            else:
                out["info"] += 1
        return out

    def verdict(self) -> str:
        counts = self.counts()
        if self.aborted:
            return "INCOMPLETE"
        if counts["hard_fail"] or counts["errors"]:
            return "FAIL"
        if self.coverage_gaps:
            return "INCOMPLETE"
        return "PASS"

    # ---- persistence ---------------------------------------------------

    def to_json(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict(),
            "aborted": self.aborted,
            "coverage_gaps": self.coverage_gaps,
            "counts": self.counts(),
            "meta": self.meta,
            "started_utc": datetime.fromtimestamp(self.started, timezone.utc).isoformat(),
            "duration_seconds": round((self.finished or time.time()) - self.started, 1),
            "steps": [asdict(step) for step in self.steps],
            "transactions": [asdict(tx) for tx in self.txs],
            "tables": self.tables,
            "notes": self.notes,
        }

    def save_partial(self) -> None:
        if not self.partial_path:
            return
        try:
            with open(self.partial_path, "w", encoding="utf-8") as handle:
                json.dump(self.to_json(), handle, indent=2, default=str)
        except OSError:
            pass

    def write(self, out_dir: str, stem: str) -> Dict[str, str]:
        self.finished = time.time()
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, stem + ".json")
        md_path = os.path.join(out_dir, stem + ".md")
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_json(), handle, indent=2, default=str)
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(self.markdown())
        if self.partial_path and os.path.exists(self.partial_path):
            try:
                os.remove(self.partial_path)
            except OSError:
                pass
        return {"json": json_path, "markdown": md_path}

    # ---- rendering -----------------------------------------------------

    def markdown(self) -> str:
        counts = self.counts()
        meta = self.meta
        verdict = self.verdict()
        lines: List[str] = []
        add = lines.append

        add(f"# Primacy end-to-end report: {verdict}")
        add("")
        if meta.get("rehearsal"):
            add("> **Rehearsal run.** This was executed against a local simulator with scripted model answers. "
                "It checks the script and the contract logic. It is **not** a Studionet result.")
            add("")
        add("| | |")
        add("|---|---|")
        for key in ("network", "rpc", "chain_id", "contract", "deployer", "started_utc", "duration", "clock_skew", "versions", "model_mode"):
            if key in meta:
                add(f"| {key.replace('_', ' ')} | {_cell(meta[key])} |")
        add("")
        if self.aborted:
            add(f"**Run aborted:** {self.aborted}")
            add("")

        if self.coverage_gaps:
            add("**Coverage gaps (the run cannot be called complete):**")
            add("")
            for gap in self.coverage_gaps:
                add(f"- {gap}")
            add("")

        add("## Summary")
        add("")
        add("| Measure | Count |")
        add("|---|---|")
        add(f"| Contract rules verified (hard checks passed) | {counts['hard_pass']} |")
        add(f"| Contract rules violated (hard checks failed) | {counts['hard_fail']} |")
        add(f"| Model/environment expectations aligned | {counts['soft_aligned']} |")
        add(f"| Model/environment expectations diverged | {counts['soft_diverged']} |")
        add(f"| Steps that could not be evaluated (errors) | {counts['errors']} |")
        add(f"| Skipped | {counts['skipped']} |")
        add(f"| Transactions sent | {len(self.txs)} |")
        add("")
        add("Hard checks are rules the contract enforces itself (access control, ordering, deadlines, bond and reward "
            "accounting). They must hold on every network. Soft checks depend on what a language model decides or on "
            "how the network handles value; a divergence is reported but does not make the run fail.")
        add("")

        problems = [s for s in self.steps if s.status in (FAIL, ERROR)]
        if problems:
            add("## Problems")
            add("")
            add("| Scenario | Step | Status | Expected | Observed | Note |")
            add("|---|---|---|---|---|---|")
            for step in problems:
                add(f"| {_cell(step.scenario)} | {_cell(step.title)} | {step.status} | {_cell(step.expected)} | {_cell(step.observed)} | {_cell(step.note)} |")
            add("")

        scenarios: List[str] = []
        for step in self.steps:
            if step.scenario not in scenarios:
                scenarios.append(step.scenario)
        add("## Steps")
        for scenario in scenarios:
            add("")
            add(f"### {scenario}")
            add("")
            add("| Step | Kind | Status | Expected | Observed | Tx | Seconds |")
            add("|---|---|---|---|---|---|---|")
            for step in self.steps:
                if step.scenario != scenario:
                    continue
                note = f" ({_cell(step.note)})" if step.note else ""
                add(f"| {_cell(step.title)}{note} | {step.kind} | {step.status} | {_cell(step.expected)} | "
                    f"{_cell(step.observed)} | {_short(step.tx)} | {step.seconds:.1f} |")

        for name, rows in self.tables.items():
            if not rows:
                continue
            add("")
            add(f"## {name}")
            add("")
            columns = list(rows[0].keys())
            add("| " + " | ".join(columns) + " |")
            add("|" + "|".join("---" for _ in columns) + "|")
            for row in rows:
                add("| " + " | ".join(_cell(row.get(column, "")) for column in columns) + " |")

        add("")
        add("## Transactions")
        add("")
        add("| # | Label | Method | Sender | Result | Consensus | Seconds | Hash |")
        add("|---|---|---|---|---|---|---|---|")
        for index, tx in enumerate(self.txs, 1):
            result = "ok" if tx.ok else "reverted/failed: " + tx.detail
            add(f"| {index} | {_cell(tx.label)} | {tx.method} | {_short(tx.sender)} | {_cell(result)} | "
                f"{tx.status} {tx.agree} | {tx.seconds:.1f} | {tx.tx_hash} |")

        if self.notes:
            add("")
            add("## Notes")
            add("")
            for note in self.notes:
                add(f"- {note}")
        add("")
        return "\n".join(lines)
