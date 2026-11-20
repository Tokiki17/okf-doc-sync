---
type: Compatibility Policy
title: Host compatibility
description: Defines the host-neutral skill contract, per-host installation, and agent instruction file policy.
tags: [portability, agent-skills, installation]
generated:
  by: process:doc-sync
  at: 2026-11-20T13:00:43+09:00
sources:
  - id: policy
    resource: ../../../docs/host-compatibility.md
  - id: installer
    resource: ../../../scripts/install.py
  - id: agent-skills-spec
    resource: https://agentskills.io/specification
  - id: claude-code-skills
    resource: https://code.claude.com/docs/en/skills
  - id: codex-skills
    resource: https://learn.chatgpt.com/docs/build-skills
  - id: delegation
    resource: ../../../skills/doc-sync/references/delegation.md
---

# Current policy

The [host compatibility policy](../../../docs/host-compatibility.md) keeps one Agent Skills tree with only `name` and `description` frontmatter, the key set accepted by the specification, Codex's skill-creator validator, and the claude.ai/API upload validator. The body names no host tools, models, or fixed paths. `agents/openai.yaml` remains optional Codex metadata.

The [delegation reference](../../../skills/doc-sync/references/delegation.md) uses existing host authorization or a saved preference, including any chosen reconfirmation policy. With no applicable preference or route, the main session completes the sync. Persistent setup is available on request.

`scripts/install.py` installs the same tree with `--host codex`, `agents`, or `claude`, or any `--target`, and checks parity per target. Shared project rules stay in `AGENTS.md`; host files such as `CLAUDE.md` import it and add only host-specific rules.

# Verification boundary

Repository validation enforces format, size limits, links, and parity. It does not measure triggering quality or behavior across models and hosts.

# Related knowledge

- [Skill contract](skill-contract.md)
- [Installation and validation](install-and-validation.md)
