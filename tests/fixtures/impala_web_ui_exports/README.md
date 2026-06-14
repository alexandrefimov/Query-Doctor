# Sanitized Impala Web UI Export Fixtures

This directory contains synthetic, sanitized text profiles shaped like Impala
Web UI profile downloads. They are committed to exercise installed-package user
paths without real SQL, users, hosts, local paths, credentials, or production
payloads.

The fixture set covers:

- embedded `Query ID` intake;
- strict `profile_<query-id-high>_<query-id-low>` filename fallback when the
  profile body has no readable Query ID header;
- accepted local analysis for a profile that yields zero parsed operators.

Keep these fixtures small and public-safe. Do not replace them with raw exported
profiles.
