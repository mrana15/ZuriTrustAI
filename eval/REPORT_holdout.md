# Screening evaluation report (holdout.json)

Date: 2026-10-22 | Danger-sign content version: 0.1.1 | Cases: 24 (fictional)

> Software test on fictional scenarios. **Not clinical validation.**

| Metric | Result |
|---|---|
| Exact agreement with expected level | 100.0% |
| Emergency cases flagged as emergency | 100.0% |
| Any danger case flagged (emergency or urgent) | 100.0% |
| Under-triage (assigned lower level than expected) | 0 |
| Over-triage (assigned higher level than expected) | 0 |
| AI caution note added to routine cases (trained model) | 0 |
| Danger cases missed by rules but caught by AI caution note | 0 |

## Confusion matrix (rows = expected, columns = assigned)

| expected \ assigned | emergency | urgent | routine |
|---|---|---|---|
| emergency | 10 | 0 | 0 |
| urgent | 0 | 7 | 0 |
| routine | 0 | 0 | 7 |

## Disagreements

None.
