# Test and Coverage Evidence

Verified on 2026-09-17 with Python 3.14 in the local virtual environment.

```text
14 tests passed
612 statements, 98 missed
TOTAL COVERAGE: 84%
Ruff: All checks passed
Database smoke test: passed
```

The checklist's claim-processing examples were translated to this project's defect domain:

- approved/happy path: defect creation, triage, status progression, and closure;
- duplicate: known-error and historical similarity classification;
- eligibility/validation failure: missing input, invalid status transition, missing API key;
- edge cases: missing defect, unknown model keys, reopening, reminder cancellation.

Reproduce the measurement with:

```powershell
python -m coverage run -m unittest discover -s tests
python -m coverage report --include="src/defect_triage/*"
```
