# Using Stometa Skills with Multica

Multica is a distribution and orchestration layer around agent runtimes. It can move a shared Skill into the provider-native location used for a task, while repository-scoped skills remain part of the checked-out codebase.

This repository does not require Multica. It produces portable Agent Skills; Multica is one adapter.

## Three sources, three behaviors

| Source | Where it lives | How Multica treats it | Best fit |
|---|---|---|---|
| Repository-scoped | committed under a tool-supported directory in the target repository | leaves it in the checkout; the underlying coding tool discovers it through native rules | codebase-specific workflows and profiles |
| Local | a provider-specific local root or `~/.agents/skills/` | the daemon scans supported roots and lets you choose what to import | private testing and sensitive local material |
| Workspace | stored in the Multica workspace and attached to an agent | syncs it into the task runtime when a new task starts | stable skills shared across agents or teammates |

A repository-scoped skill is not automatically copied into the Workspace registry. This is useful: local business rules can remain next to the code that owns them.

## Recommended pattern

1. Keep repository-specific behavior in the target repository's supported skill directory.
2. Import a released public skill from the GitHub tree URL for that skill, not from an unreviewed private working copy.
3. Attach the imported Workspace Skill only to agents whose job matches its trigger.
4. Start a new task after changing an attached Skill; already running tasks keep the previous version.
5. If a Workspace Skill and repository skill share a directory name, inspect both. Multica preserves the repository files and writes the Workspace copy under an adjusted sibling name.

Once this repository publishes a skill named `<skill-name>`, its import URL will follow this form:

```text
https://github.com/stone16/stometa-skills/tree/main/skills/<skill-name>
```

No URL is listed as install-ready until the catalog marks the adapter `verified`.

## Safety boundary

Multica passes imported Skill files to the selected coding tool. It does not make third-party scripts trustworthy. Before importing:

- inspect `SKILL.md` and every bundled file;
- verify the repository, pinned revision, and license;
- review scripts for filesystem, shell, network, credential, and external-service access;
- prefer local or repository-scoped skills for sensitive material;
- keep credentials in the runtime's secret mechanism, never in a Skill pack.

## Collision and ownership rule

Name collision handling prevents overwrite at task setup, but it does not resolve semantic overlap. If a repository profile and public skill both appear, make the relationship explicit with `profile_of` or `extends`. If they are independent implementations, rename one or complete an ownership transfer.

## Verification checklist

Before this repository marks Multica support `verified` for a skill:

- import succeeds from the exact public GitHub tree URL;
- all bundled files arrive and remain within documented size limits;
- the Skill attaches to a test agent;
- a new task exposes the expected trigger and files;
- a repository-scoped skill with the same name is not overwritten;
- uninstall or detach behavior is documented;
- no private evidence or credentials enter the Workspace copy.

## Source

Behavior in this document follows the [Multica Skills documentation](https://multica.ai/docs/skills). Re-check the upstream documentation before changing compatibility from `expected` to `verified`.
