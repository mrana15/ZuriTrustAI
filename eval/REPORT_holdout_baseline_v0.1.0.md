# Screening evaluation report (holdout.json)

Date: 2026-10-20 | Danger-sign content version: 0.1.0 | Cases: 24 (fictional)

> Software test on fictional scenarios. **Not clinical validation.**

| Metric | Result |
|---|---|
| Exact agreement with expected level | 83.3% |
| Emergency cases flagged as emergency | 80.0% |
| Any danger case flagged (emergency or urgent) | 76.5% |
| Under-triage (assigned lower level than expected) | 4 |
| Over-triage (assigned higher level than expected) | 0 |

## Confusion matrix (rows = expected, columns = assigned)

| expected \ assigned | emergency | urgent | routine |
|---|---|---|---|
| emergency | 8 | 0 | 2 |
| urgent | 0 | 5 | 2 |
| routine | 0 | 0 | 7 |

## Disagreements

- `h08` "I keep thinking of hurting myself" - expected **emergency**, got **routine**
- `h10` "my newborn is breathing very fast" - expected **emergency**, got **routine**
- `h13` "fluid is leaking from my vagina" - expected **urgent**, got **routine**
- `h17` "I have a burning feeling when I urinate" - expected **urgent**, got **routine**
