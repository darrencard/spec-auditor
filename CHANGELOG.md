# Changelog

## 0.3.1, 2026-11-26

- README: install through the Landing Loop bundle (`/plugin marketplace add darrencard/landing-loop`, then `/plugin install spec-auditor@landing-loop`), with the paste-in prompt kept for a standalone install.
- README: the repository is public, so the private-until-review notes are gone, and the loop is counted as eleven skills plus the Product & Technology Leader Report.
- README: one trademark line for Claude and Claude Code.
- Acme fixtures name people by role (Head of Product, Quoting squad; Quoting squad tech lead), as the loop briefs do.
- No change to what the skill computes. The version in the sample record's `tool` field moves with the release.
- A hold prints in ink, not brass; brass is kept for the owner's name. Text selection and the focus ring print in ink, not the template's green.
- `spec_audit.py` checks for Python 3.11 or later first, before it reads or writes anything, and stops with a plain message on anything older.
