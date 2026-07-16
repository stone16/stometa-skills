# Security policy

Agent skills may instruct a model to run commands, access repositories, call external tools, or change remote state. Treat changes to executable scripts and mutation workflows as security-sensitive.

## Report a vulnerability

Use GitHub private vulnerability reporting for vulnerabilities, leaked credentials, unsafe default permissions, or prompt-driven paths that can cause unintended external mutations. Do not open a public issue containing a secret or private customer detail.

## Public repository boundary

This repository must not contain:

- credentials, cookies, tokens, or secret-bearing URLs;
- absolute personal paths or private repository identifiers;
- raw task prompts, private task output, or usage receipts;
- customer names, internal domains, workspace IDs, or private Multica configuration;
- executable scripts without explicit inputs, side effects, and verification behavior.

The repository validator is a guardrail, not proof that a change is safe. Promotion PRs still require human review.

