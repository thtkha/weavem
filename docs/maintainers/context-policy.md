# Context and handoff policy

**Applies to human contributors and coding agents on every branch carrying this policy.**

## Repository context is part of completion

Important context must never live only in a conversation. Before handing off or
calling work complete, update tracked Markdown so another contributor can proceed
without the original chat, agent session, or machine-local state. This includes:

- The goal, scope, invariants, and approved decisions that constrain the work.
- Material alternatives and why they were rejected or deferred.
- Implemented interfaces and changes to existing behavior or compatibility.
- Current status, remaining work, blockers, and the next safe action.
- Verification actually performed, including revision/environment, results,
  evidence paths, and limitations. Separate plans from implementation and tests.

Keep the account concise and actionable; do not dump transcripts or speculate
about motives. Code/configuration defines actual behavior. Correct current
instructions when they drift; keep dated evidence as history rather than quietly
rewriting it to claim a later success.

## Put information where its audience can find it

- [Released user manual](../users/index.md): supported shipped behavior only.
- [Maintainer documentation](index.md): setup, contracts, conventions, procedures,
  and explicitly labelled source-branch references.
- [Project records](../project/index.md): decisions, evaluations, branch status,
  rejected alternatives, and historical evidence.
- Each active implementation branch needs a tracked handoff identifying its
  baseline, owner/scope, exact implementation commits, exported interfaces,
  integration dependencies, verification, limitations, and continuation branch.
  A branch's tests do not prove that its later integrated application works.

Use one canonical explanation and links rather than competing copies. Keep
human-first Markdown usable by agents too. Link it from the audience index.
A feature branch must not claim code or integration found only on another branch.

## Evidence and privacy

Summaries and reproducible check commands belong in Git. Disposable logs, browser
images, test projects, and generated binaries belong in the agreed ignored artifact
location (currently `.artifacts/node-editor/` for editor work). Record paths and
important outcomes in tracked records because ignored artifacts may not be shared.
Never put tokens, credentials, private keys, customer data, or complete sensitive
execution payloads into documentation. Preserve failures as well as successes.

## Branch lifecycle

Record which branch is authoritative for continuation and whether each lane is
active, integrated by cherry-pick/merge, historical, or an unselected alternative.
Record the audited code commit, not an invented live status. Inspect Git before
updating this information. Do not delete branches, rewrite history, merge to main,
or publish merely to simplify documentation.

A handoff is incomplete if its only explanation is “see the chat,” “ask the
previous agent,” or an inaccessible local artifact. If verification cannot run,
record the gap explicitly rather than claiming completion of that check.
