# Clinical content review process

Clinical content is stored in:

- `app/data/danger_signs.json` — danger signs, trigger phrases, urgency levels, advice text
- `app/data/knowledge_base.json` — question examples, answers and sources

## Status
Both files are **DRAFT** (`review_status` field). They must be signed off by the Zuri Circle Chief Medical Officer before a pilot.

## Review checklist (per release)
- [ ] Each danger sign's urgency level matches current WHO and national (e.g. Nigeria FMoH) guidance.
- [ ] Advice text is accurate, short, and understandable at a low literacy level.
- [ ] Each knowledge-base answer is accurate, cites a current source, and contains no medicine doses.
- [ ] The emergency number is correct for each deployment country.
- [ ] Translations (when added) reviewed by a native speaker with health background.
- [ ] A new, independently written set of fictional test scenarios is added to `eval/` and passes with **zero emergency cases classified as routine**.
- [ ] `version` bumped; reviewer name and date recorded below.

## Sign-off log

| Version | File | Reviewer | Date | Notes |
|---|---|---|---|---|
| 0.1.1 | danger_signs.json | [pending] | | |
| 0.1.0 | knowledge_base.json | [pending] | | |
