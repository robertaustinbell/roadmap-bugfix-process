# Security findings

Security findings never go into a public PR, issue, commit message, branch name, or comment.
This repo contains no security findings, only the procedure.

## Procedure

1. The Decider marks a finding `security` if it could expose user data, bypass auth, leak secrets,
   allow injection, or weaken a security control.
2. Stop the normal path. Do not write a fix branch on a public fork.
3. Report privately to Brad's agent through the private agent-to-agent channel Brad named
   for security reports, without waiting for operator approval. If no such channel is named, use
   GitHub private vulnerability reporting on
   [DrBradStanfield/roadmap](https://github.com/DrBradStanfield/roadmap/security) (enabled).
   Tell the operator in one line that a report went, with no detail.
4. Include: affected file and commit, impact, minimal reproduction, suggested fix. Use synthetic
   data only.
5. Record locally (outside any public repo) that a report was sent and when. The public ledger only
   gets a count, never details.
6. The maintainer decides whether and how it is fixed. A security-*policy* change (what the rules
   should be) always goes to the human review list, not to the Bug fixer.

## Never

- Never mention a specific security issue publicly before the maintainer has fixed it and agreed.
- Never test a security finding against the live production service.
- Never put real user, patient, or health data anywhere, including private reports.
