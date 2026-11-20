# Delegated execution

Read this when installing doc-sync, when no choice record exists for the current host, or before running doc-sync in a delegated agent (a subagent or child agent). Delegation keeps the main context small and can use a less expensive model. It is optional: without a verified delegation mechanism, or when the user declines, run doc-sync in the main session.

This file states what doc-sync needs. It names no models, hosts, or tools on purpose: which options exist, and how to select them, is decided at run time from the current host's own evidence.

## Contents

- Requirement profile
- Host evidence
- Setup
- Each run
- Choice record
- Boundaries
- Sources

## Requirement profile

Use this profile to rank the options the host actually offers.

- **Recommended:** a mid-capability model at the host's default or medium reasoning setting. Most steps are mechanical (focused search, link and index repair, the update log, the validator), but mapping the affected surface and separating current, pending, historical, and retired claims need judgment. Errors in those two steps pass structural validation.
- **Lowest tier:** acceptable only for a narrow mechanical update whose surfaces the brief already lists, such as a renamed command or path. Do not recommend it as the default.
- **Highest tier:** not needed for routine synchronization. Offer it when the user values thoroughness over cost.
- **Keep in the main session:** durable initialization, OKF version migration, governance repair, restricted-data handling, unresolved source conflicts, and any change small enough that writing the brief and reviewing the result costs more than doing it, such as a wording-only edit.

Prefer options that follow the vendor's updates, such as a tier name or alias, over a pinned version when the host offers both and they map to the same tier.

## Host evidence

Decide each host-specific fact from evidence, in this order, and note which source settled it:

1. what the current session exposes: the delegation interface, its parameters, and their allowed values, plus existing agent definition files and local configuration;
2. the host's official documentation and best practices;
3. the host's source repository at the installed version, when it is open source.

If none settles a fact, it is unknown. Do not rely on memory, third-party articles, or a model name seen elsewhere. A model the vendor has released is not an option until the host offers it.

Sources 2 and 3 cost far more than source 1. Consult them during setup, or when source 1 shows a change it cannot explain; do not repeat them on every run.

Choose the delegation mechanism in this order:

1. **Per-dispatch selection:** the delegation interface accepts a model or tier, and optionally a reasoning setting, for each call. Nothing persistent changes.
2. **Persistent agent definition:** a file or setting that fixes the delegated agent's model. Confirm its location, format, and field values from the evidence above; a misspelled field can break the agent. Writing it changes persistent configuration and needs the user's approval.
3. **No delegation:** if neither can be verified, say why and run doc-sync in the main session.

## Setup

Run setup when the skill is installed by an agent, or at the first doc-sync run on a host without a choice record. The main session runs it. Ask each question separately and wait for an explicit answer; never apply a recommendation by default.

1. **Model choice.** List the options the host offers, rank them with the requirement profile, and ask the user to choose. Put the recommendation first with a one-line reason, and include running in the main session. If the chosen mechanism is a persistent agent definition, show the file and its content and ask before writing it.
2. **Global instruction.** Skip this step if the user chose the main session. Otherwise, find the user-level instruction file the host loads in every session, from host evidence. If that file is installed from another source, such as a configuration repository, propose the change to the source and follow that source's own install and commit rules. Read the file and propose:
   - one rule that runs doc-sync through a delegated agent according to this reference and the choice record;
   - for each existing rule that would block this flow, such as one that forbids asking about model or agent choices or one that keeps all work in the main session, a narrow exception for skills that define their own model confirmation. Quote the rule and leave its other effects unchanged.

   Show the proposed edits as a diff and ask, with applying them as the recommendation. Apply only after a yes. Without the rule, the host's agents are unlikely to delegate on their own; say so if the user declines.
3. **Record.** Save both answers in the choice record. Do not propose the global instruction again unless the user asks or the instruction file no longer contains an applied rule.

## Each run

1. **Decide whether to delegate.** Use the requirement profile. Work that belongs in the main session stays there.
2. **Check the options.** Read the offered options from source 1 only and compare them with the record:
   - the chosen option is still offered and no new option ranks above it: dispatch without asking; if the list changed, update `offered` silently;
   - the chosen option is gone, or a new option ranks above it: ask once, recommending the best current option, offering to keep the current choice when it is still offered, and offering the main session. Save the answer either way.
3. **Dispatch.** Give the delegated agent a brief, because it does not see the conversation: the confirmed facts that changed, the affected files or diff, what is verified and what is pending, the write scope, and a stop condition. It edits only documentation and OKF files in scope; it does not commit, push, act on external systems, or delegate further. It returns the changed files, the checks it ran with their results, and remaining gaps.
4. **Review.** The main session reviews the diff and the validator result before it reports completion. A delegated report is evidence, not proof.

## Choice record

Store the record outside every project repository and outside the skills root, which hosts scan for skills. For a user-level installation, use `.doc-sync-install/delegation.json` beside the skills root that holds this skill; the installer keeps its rollback backup in the same directory and does not remove other files there. If that location is inside a project or not writable, keep the choice for the current session only and tell the user.

Keep one entry per host:

```json
{
  "<host>": {
    "mechanism": "per-dispatch",
    "choice": {"model": "<as the host names it>", "reasoning": "<setting or null>"},
    "offered": ["<every option the host offered, sorted>"],
    "instruction": {"status": "applied", "file": "<edited source file>"},
    "evidence": ["<source that settled the mechanism and the options>"],
    "decided_at": "<ISO 8601 timestamp with time zone>"
  }
}
```

`choice.model` is `null` when the user chose the main session. `instruction.status` is `applied`, `declined`, or `not-needed`. When the host cannot list its options, record `offered` as `null`, keep the current choice, and say that update detection is unavailable on this host.

## Boundaries

- The record is a preference. It does not prove that an option is available; check before every dispatch.
- A model change is not a reason to migrate an OKF version or rewrite documentation.
- Asking the user and editing global instructions or persistent host configuration follow the current authorization; a delegated agent never changes either.

## Sources

Checked 2026-11-20. Re-check a source before relying on a field or value that may have changed. They show that hosts differ in where delegated agents are defined, which model values they accept (aliases, exact identifiers, or tiers), whether a reasoning setting exists, and whether model choice is available per dispatch.

- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents), Claude Code docs.
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), OpenAI Codex docs.
- [Antigravity custom subagents](https://antigravity.google/docs/subagents/), Google Antigravity docs.
