<p align="center"><a href="README.zh-CN.md">简体中文</a></p>

# Stometa Skills

Many repositories, three scopes, one ownership rule.

`stometa-skills` is the public home for agent skills that have survived real use, portability review, privacy review, and behavioral evaluation. It is deliberately curated: a skill enters this repository after promotion, not when somebody first writes a useful prompt.

> **Status: active incubation baseline v0.** There are `0` promoted skills today. The repository rules are active; the first completed promotion will trigger a policy review before the baseline becomes v1.

## The model

```text
Repository skill
  -> repeated use across distinct repositories
  -> private incubation and evaluation
  -> public promotion review
  -> ownership transfers to stometa-skills
```

The system separates three independent questions:

| Axis | Values | What it decides |
|---|---|---|
| Scope | repository / shared / public | Where the skill is useful |
| Visibility | private / public | Who may inspect the source and evidence |
| Lifecycle | incubating / validated / stable / deprecated | How much trust the skill has earned |

These axes do not imply one another. Reuse does not prove publishability. Public-safe content does not prove usefulness.

## Repository contract

- `skills/` is flat and contains promoted public skills. Deprecated skills remain as migration sources but are excluded from default collections and installs.
- Every published skill has one canonical source in this repository.
- Repository-specific paths, commands, credentials, and business facts stay in local profiles.
- A promotion PR includes provenance, real-use evidence, trigger tests, safety review, and installation checks.
- Claude, Codex, Multica, and installer metadata are adapters. They never become a second copy of the skill body.

See [Architecture](docs/architecture.md) and [Promotion policy](docs/promotion-policy.md) for the complete contract.

## Choose the smallest useful scope

| If the method is... | Keep it in... | Why |
|---|---|---|
| coupled to one codebase, customer, or operating environment | that repository | the skill can use local paths and conventions without pretending to be portable |
| reused across your own repositories but still personal or sensitive | a private control plane | one owner can consolidate and evaluate it without publishing runtime evidence |
| portable, safe to inspect, independently reviewed, and worth maintaining for others | `stometa-skills` | the public repository becomes the canonical source |

The architecture is reusable; the private control plane is an implementation choice. You can adopt the public rules with one repository, several repositories, or a team workspace. See [Operating model](docs/operating-model.md) for the minimum viable setup and copyable review prompts.

## Collections

Collections are catalog views, not directories. A skill may belong to more than one collection without moving or duplicating its source.

- Skill engineering
- Repository and harness engineering
- Research and knowledge work
- Content and growth

The machine-readable definitions live in [`catalog/collections.yaml`](catalog/collections.yaml).

## Installation

No install command is advertised before the first skill passes promotion. Planned distribution adapters are tracked in [Compatibility](docs/compatibility.md):

- `skills.sh` for editable copies
- Claude Code and Codex plugins for managed installs
- GitHub import and repository-scoped discovery for Multica workflows

Multica treats those two paths differently. A repository-scoped skill stays inside the checked-out repository and is discovered by the underlying coding tool. A Workspace Skill is imported, attached to an agent, and synced for new tasks. See [Using the repository with Multica](docs/multica.md).

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). New skills require a promotion case; documentation fixes, evaluation improvements, and portability fixes can be proposed directly.

## Documentation

- [Operating model](docs/operating-model.md) — adopt the three-layer system and use the review prompts.
- [Architecture](docs/architecture.md) — source-of-truth, scopes, and ownership transfer.
- [Promotion policy](docs/promotion-policy.md) — nomination signals, gates, and decisions.
- [Skill standard](docs/skill-standard.md) — required files, evaluations, and safety boundaries.
- [Multica](docs/multica.md) — repository-scoped, local, and Workspace Skill behavior.
- [Compatibility](docs/compatibility.md) — verified, expected, and unsupported adapters.

## License

Apache-2.0. Third-party adaptations retain their original notices and provenance.
