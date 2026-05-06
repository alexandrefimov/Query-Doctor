# Legacy prototypes

This directory contains historical Query Doctor prototypes that are not part of
the current trusted product workflow.

Use current entry points from the repository root instead:

- `query_doctor_web_server.py`
- `query_doctor_batch_recent.py`
- `query_doctor_collect_cm_profiles.py`
- `query_doctor_pipeline.py`
- `query_doctor_report.py`

These archived scripts may write raw or semi-raw local artifacts and may bypass
current deterministic validation, browser-safety, and trusted-report contracts.
Keep them as historical reference only unless they are explicitly maintained.
