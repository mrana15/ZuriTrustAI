# Contributing

1. Fork the repository and create a feature branch.
2. Install development dependencies with `pip install -r requirements-dev.txt`.
3. Run `python -m pytest -q` and the evaluation commands documented in `README.md`. Record the actual output; do not claim a test passed unless it ran successfully.
4. **Clinical content changes** (`app/data/danger_signs.json`, `app/data/knowledge_base.json`) must: bump the content version, cite authoritative sources, and receive approval from the clinical lead as described in `docs/clinical_review.md`.
5. Never add real patient data, personal identifiers, access tokens, or production secrets to tests, evaluation sets, issues, or pull requests. Use fictional scenarios only.
6. Keep dependencies lightweight. Discuss material increases in page weight, server requirements, or data collection before adding them.
7. Do not describe software test performance as clinical validation. Any clinical or pilot claims require appropriate independent review and approvals.
