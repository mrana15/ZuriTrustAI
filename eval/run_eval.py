"""Evaluate the danger-sign screener on fictional test scenarios.

Usage:  python -m eval.run_eval            (writes eval/REPORT.md)

Reports overall agreement, emergency sensitivity, under-triage (the most
important safety metric) and over-triage. These are SOFTWARE TEST results on
fictional data, not clinical validation.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.screening import DangerSignScreener  # noqa: E402

LEVELS = ["emergency", "urgent", "routine"]
RANK = {"routine": 1, "urgent": 2, "emergency": 3}


def evaluate(cases: list[dict], screener: DangerSignScreener) -> dict:
    rows, confusion = [], Counter()
    for c in cases:
        r = screener.screen_text(c["text"])
        got = r.level
        flag = bool(r.model and r.model.get("flag"))
        confusion[(c["expected"], got)] += 1
        rows.append({**c, "got": got, "ok": got == c["expected"], "model_flag": flag})
    n = len(rows)
    correct = sum(r["ok"] for r in rows)
    emerg = [r for r in rows if r["expected"] == "emergency"]
    danger = [r for r in rows if r["expected"] != "routine"]
    under = [r for r in rows if RANK[r["got"]] < RANK[r["expected"]]]
    over = [r for r in rows if RANK[r["got"]] > RANK[r["expected"]]]
    return {
        "n": n,
        "accuracy": correct / n,
        "emergency_sensitivity": sum(r["got"] == "emergency" for r in emerg) / max(len(emerg), 1),
        "danger_sensitivity": sum(r["got"] != "routine" for r in danger) / max(len(danger), 1),
        "under_triage": under,
        "over_triage": over,
        "confusion": confusion,
        "model_loaded": screener.model is not None,
        "model_notes_on_routine": sum(r["model_flag"] for r in rows if r["expected"] == "routine"),
        "model_rescues": sum(r["model_flag"] for r in rows if r["expected"] != "routine" and r["got"] == "routine"),
        "rows": rows,
    }


def to_markdown(res: dict, version: str) -> str:
    pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731
    lines = [
        "# Screening evaluation report",
        "",
        f"Date: {date.today().isoformat()} | Danger-sign content version: {version} | Cases: {res['n']} (fictional)",
        "",
        "> Software test on fictional scenarios. **Not clinical validation.**",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Exact agreement with expected level | {pct(res['accuracy'])} |",
        f"| Emergency cases flagged as emergency | {pct(res['emergency_sensitivity'])} |",
        f"| Any danger case flagged (emergency or urgent) | {pct(res['danger_sensitivity'])} |",
        f"| Under-triage (assigned lower level than expected) | {len(res['under_triage'])} |",
        f"| Over-triage (assigned higher level than expected) | {len(res['over_triage'])} |",
        f"| AI caution note added to routine cases (trained model) | {res['model_notes_on_routine'] if res['model_loaded'] else 'model not loaded'} |",
        f"| Danger cases missed by rules but caught by AI caution note | {res['model_rescues'] if res['model_loaded'] else 'model not loaded'} |",
        "",
        "## Confusion matrix (rows = expected, columns = assigned)",
        "",
        "| expected \\ assigned | " + " | ".join(LEVELS) + " |",
        "|---|" + "---|" * len(LEVELS),
    ]
    for e in LEVELS:
        lines.append(f"| {e} | " + " | ".join(str(res["confusion"][(e, g)]) for g in LEVELS) + " |")
    misses = [r for r in res["rows"] if not r["ok"]]
    lines += ["", "## Disagreements", ""]
    if not misses:
        lines.append("None.")
    for r in misses:
        lines.append(f"- `{r['id']}` \"{r['text']}\" - expected **{r['expected']}**, got **{r['got']}**")
    return "\n".join(lines) + "\n"


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "cases.json"
    cases = json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))["cases"]
    screener = DangerSignScreener()
    res = evaluate(cases, screener)
    report = to_markdown(res, screener.version)
    out = "REPORT.md" if name == "cases.json" else f"REPORT_{Path(name).stem}.md"
    report = report.replace("# Screening evaluation report", f"# Screening evaluation report ({name})")
    (ROOT / "eval" / out).write_text(report, encoding="utf-8")
    print(report)
    # Fail CI if any emergency is missed entirely.
    missed = [r for r in res["rows"] if r["expected"] == "emergency" and r["got"] == "routine"]
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
