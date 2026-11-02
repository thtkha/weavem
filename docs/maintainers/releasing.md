# Promote the original Weavem 0.1.0a2 wheel to public PyPI

| Field | Value |
| --- | --- |
| Status | Draft |
| Owner | Kha Trịnh, repository owner `thtkha`; contact in [SECURITY.md](../../SECURITY.md) |
| Escalation | Email `khaa.dev@gmail.com` with the workflow URL, version and redacted failure |
| Last verified | 2026-11-02 — original release identity and CLI flags inspected; publication is pending |
| Last executed | Never — this public promotion has not completed |
| Applies to | `thtkha/weavem`, `main`, original `v0.1.0a2`, production PyPI project `weavem` |
| Risk | High — public source can be copied, and an uploaded distribution cannot be replaced |
| Expected duration | 20–60 minutes after account setup; verification and owner approval determine timing |
| Change record | Owner-approved public promotion of the existing alpha; no new version or feature merge |

> **Verification claim:** This is a prepared public-promotion procedure, not proof
> of a completed upload. Account configuration, public visibility, workflow
> execution and anonymous PyPI installation remain acceptance gates until the
> operator records their actual results below. The historical private-release
> procedure is [preserved separately](releasing-private-legacy.md).

## Contents

- [Purpose and successful outcome](#purpose-and-successful-outcome)
- [Scope](#scope)
- [Safety, impact, and stop conditions](#safety-impact-and-stop-conditions)
- [Ownership and escalation](#ownership-and-escalation)
- [Prerequisites](#prerequisites)
- [System and repository orientation](#system-and-repository-orientation)
- [Preflight checks](#preflight-checks)
- [Procedure](#procedure)
- [Verification](#verification)
- [Rollback and recovery](#rollback-and-recovery)
- [Troubleshooting](#troubleshooting)
- [Cleanup](#cleanup)
- [Evidence and audit record](#evidence-and-audit-record)
- [References](#references)
- [Document maintenance](#document-maintenance)

## Purpose and successful outcome

Make the existing GitHub repository public and promote the **original**
`weavem-0.1.0a2-py3-none-any.whl` from GitHub to PyPI. The promotion succeeds only
when the public PyPI wheel has the original SHA-256 and a clean anonymous install
passes the supported-platform task/flow/native/reuse checks.

## Scope

Both remote branches, `main` and `prototype/node-editor`, and their reachable
history become public after audit. The editor remains experimental and absent
from `0.1.0a2`. Do not merge newer core/editor work, build a replacement artifact,
move the tag, create `a3`, upload a new source distribution, or overwrite GitHub
assets. The original wheel's embedded README retains private-release wording;
current repository documentation explains public distribution.

## Safety, impact, and stop conditions

- Require the repository owner's approved public-exposure audit before changing
  visibility. Audit history, both remote branches, release assets, and package
  contents; a clean working tree alone does not prove that history is safe.
- Public exposure cannot be undone by making the repository private again.
  The PyPI upload is a second point of no return: distribution filenames cannot
  be reused after deletion. Preserve the original wheel, manifest and tag.
- Stop on a secret/confidential-data finding, unresolved license/notice issue,
  wrong source/tag/digest, failed verification lane, unavailable package name,
  publisher-identity mismatch, or existing conflicting PyPI distribution.
- Do not bypass the protected `pypi` environment, use credentials in chat or
  workflow inputs, retry a conflicting upload, or substitute another package name.
- Before exposure, preserve all audit and verification evidence in the approved,
  gitignored `.artifacts/public-release/` directory. Do not commit it wholesale.

## Ownership and escalation

Kha Trịnh approves public exposure, configures the existing PyPI account, and
reviews the protected environment. Implementation agents may prepare and verify
files; an agent report is not evidence that publication finished. For a blocker,
stop the workflow and email `khaa.dev@gmail.com` with the repository commit,
workflow/run URL, failed step, expected/actual digest, and redacted diagnostics.
Do not send passwords, two-factor codes, recovery codes or API tokens.

## Prerequisites

Run Bash on Linux from the repository root with Git, Python 3.12–3.15 and a
GitHub CLI login authorized to administer `thtkha/weavem`. Verify tools with
`git --version`, `python3 --version`, `gh --version` and `gh auth status`.
The original artifact supports standard GIL-enabled, non-debug CPython on Linux
x86_64/glibc 2.28+, not every platform accepted by its portable wheel filename.

The reviewed promotion workflow and documentation must already be committed and
pushed to `main`, with a successful `Verify Weavem` push run for that exact commit.
Start from a clean `main` checkout. This runbook does not merge feature branches.

Use the existing PyPI account with verified email and two-factor authentication.
It must be authorized to create project `weavem`, or own that project if it already
exists. A pending publisher does not reserve a name. Do not create a password or
API token for GitHub Actions: this workflow uses OpenID Connect (OIDC).

| Input | Fixed value or source |
| --- | --- |
| Repository | `https://github.com/thtkha/weavem` |
| Source tag | `v0.1.0a2` |
| Tag commit | `13c2b3876e55690be06da1deb5db8ab2df516f65` |
| Wheel | `weavem-0.1.0a2-py3-none-any.whl` |
| Wheel SHA-256 | `518877f1dc2c20c34ed3c0aeb9144a4e99d8a6ab4547db103130c475b9aa2f95` |
| Workflow file | `.github/workflows/publish-pypi.yml` |
| GitHub environment | `pypi`, restricted to `main` and owner review |
| `RUN_ID` | Numeric ID of the exact manually dispatched publishing run, obtained in Step 3 |

## System and repository orientation

The dedicated `publish-pypi.yml` workflow promotes an existing artifact; it does
not build the release. Its fixed-version helper verifies the release identity,
checksums and wheel contents, then supported-Python jobs test that candidate.
Only the protected publishing job receives OIDC permission. No pull request,
experimental branch or tag push may publish. The old private-GitHub helper in
`scripts/release-alpha.py` remains historical and refuses a public repository.

## Preflight checks

**Goal:** Confirm repository and immutable release identity before mutation.

**Run from:** Repository root in Bash, as the authenticated repository maintainer.

**Action:**

```bash
set -euo pipefail
test "$(git remote get-url origin)" = 'https://github.com/thtkha/weavem.git'
test -z "$(git status --porcelain)"
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$(gh api repos/thtkha/weavem/git/ref/heads/main --jq .object.sha)"
gh run list --repo thtkha/weavem --workflow verify.yml --branch main --event push \
  --commit "$(git rev-parse HEAD)" --limit 1 --json status,conclusion,url
test "$(git rev-parse v0.1.0a2^{commit})" = '13c2b3876e55690be06da1deb5db8ab2df516f65'
gh repo view thtkha/weavem --json nameWithOwner,visibility,defaultBranchRef
gh release view v0.1.0a2 --repo thtkha/weavem --json tagName,isDraft,isPrerelease,assets
```

**Expected result:** The correct repository, original tag commit and non-draft
GitHub alpha with its wheel and `SHA256SUMS`; a clean `main` matching the remote,
and a completed successful verification run for the exact commit. Require completed audit and supported-Python evidence before
Step 2. Current private visibility is expected before initial public exposure.

**If this fails:** Stop. Do not repair by retagging, rewriting assets or skipping
an audit/test. **Evidence to retain:** commit, release metadata, audit result and
verification job URLs. **Repeatability:** read-only and safe to repeat.

## Procedure

### Step 1 — configure the publisher and approval gate

**Goal:** Authorize only the intended GitHub workflow, without a long-lived token.

**Run from:** The owner's browser, signed into the existing PyPI and GitHub accounts.

**Action:** On PyPI, open **Account settings → Publishing** at
[the account publishing page](https://pypi.org/manage/account/publishing/).
Add a pending **GitHub** publisher with project `weavem`, owner `thtkha`, repository
`weavem`, workflow `publish-pypi.yml` (filename only), and environment `pypi`.
If the project already exists under the owner's account, use its **Manage →
Publishing** page instead. An unrelated owner is a blocker, not permission to rename.

On GitHub, open **thtkha/weavem → Settings → Environments → pypi**. Restrict the
environment to `main` and require repository-owner review. Ensure the owner can
approve the intended manual run; do not weaken the protection to resolve a failure.

**Expected result:** Matching publisher fields and protected environment.
**If this fails:** Stop before visibility/upload changes and escalate to Kha.
**Evidence to retain:** non-secret field values and approval configuration.
**Repeatability:** inspect existing entries before adding; do not create duplicates.

### Step 2 — expose only the audited repository

**Goal:** Make the approved repository and both audited remote branches public.

**Run from:** Repository root in Bash, as the owner, after Step 1 and all audits/tests.

**Action:** Immediately before this irreversible exposure, confirm the target:

```bash
gh repo view thtkha/weavem --json nameWithOwner,visibility
```

If already public, do not repeat the change. If private and the audit is approved,
use the owner's **Settings → General → Danger Zone → Change repository visibility**
control for **thtkha/weavem**, select **Public**, and complete GitHub's confirmation.

**Expected result:** `gh repo view thtkha/weavem --json visibility` reports
`PUBLIC`; anonymous visitors can read the repository and original release assets.
**If this fails:** Stop before publishing. Do not treat private/public toggling as
removal of leaked content. **Evidence to retain:** audit revision and visibility
check. **Repeatability:** visibility inspection is safe; exposure is not reversible.

### Step 3 — dispatch the exact-a2 promotion

**Goal:** Run verification, owner approval and publication for the original wheel.

**Run from:** Repository root in Bash, targeting the committed workflow on `main`.

**Action:**

```bash
gh repo view thtkha/weavem --json nameWithOwner,visibility
gh workflow run publish-pypi.yml --repo thtkha/weavem --ref main
gh run list --repo thtkha/weavem --workflow publish-pypi.yml --branch main \
  --event workflow_dispatch --limit 5 --json databaseId,headSha,status,conclusion,url
```

Select the run matching this dispatch and approved `main` commit. Set `RUN_ID`
to its displayed numeric `databaseId`, then run:

```bash
read -r -p "Exact publishing run databaseId: " RUN_ID
[[ "${RUN_ID}" =~ ^[0-9]+$ ]]
gh run view "${RUN_ID}" --repo thtkha/weavem --json headSha,event,url
gh run watch "${RUN_ID}" --repo thtkha/weavem --exit-status
```

When GitHub shows a pending deployment, the owner reviews the exact run and
approves its **pypi** environment through the run page. No credentials are entered
in Actions logs. **Expected result:** all verification jobs pass and the protected
publication/confirmation jobs succeed. **If this fails:** preserve the run; stop
on a digest/name/identity conflict. A retry may reuse only matching immutable
bytes; an already published identical wheel must be confirmed, not replaced.
**Evidence to retain:** run ID/URL, source commit, hashes and approval record.
**Repeatability:** do not dispatch simultaneous runs; inspect the prior run first.

## Verification

**Goal:** Prove checksum-matched public distribution and anonymous installation.

**Run from:** A clean supported Linux environment, without GitHub/PyPI credentials.

**Action:** Open the public repository, GitHub release and
[PyPI version page](https://pypi.org/project/weavem/0.1.0a2/). Confirm that PyPI's
wheel digest equals the fixed SHA-256 above. In a new virtual environment run:

```bash
python3 -m venv .venv-public-check
source .venv-public-check/bin/activate
python -m pip install --no-cache-dir --pre 'weavem==0.1.0a2'
python -m pip check
python -c 'from importlib.metadata import version; print(version("weavem"))'
weavem doctor
```

Then execute the current [user tutorial](../users/authoring-guide.md) and
[native tutorial](../users/native-authoring.md), using the same published wheel.
**Expected result:** version `0.1.0a2`, no broken requirements, passing doctor,
and the documented task/flow/native/cross-project results. **If this fails:** stop
announcement and escalate; do not rebuild `a2`. **Evidence to retain:** public
URLs, PyPI digest, interpreter/platform and sanitized test outputs.
**Repeatability:** use a new empty directory/environment for each acceptance run.
No sustained service observation window applies: this is package distribution,
not a running production service deployment.

## Rollback and recovery

Before public exposure or upload, cancel a running workflow using
`gh run cancel "${RUN_ID}" --repo thtkha/weavem` and verify cancellation with
`gh run view "${RUN_ID}" --repo thtkha/weavem --json status,conclusion`.
The safe terminal state is preserved original assets and no public upload.

After exposure, making the repository private cannot retract copies. After upload,
never delete/reuse a distribution filename or overwrite the GitHub artifact.
Preserve evidence and notify Kha. If a genuine release defect requires withdrawal,
the PyPI owner may yank the affected release through **Manage project → Releases**
with an explanatory reason; that is a separate owner decision. Corrected bytes
require a new version, outside this exact-a2 promotion. Revoke the trusted publisher
through PyPI **Publishing** if authorization itself is compromised; do not put a
replacement token into the workflow as an emergency bypass.

## Troubleshooting

- **Publisher rejected:** compare owner/repository/workflow/environment spelling
  against Step 1; do not remove environment protection or supply an API token.
- **Name unavailable or different existing digest:** stop and ask the owner;
  neither an alternate name nor replacement bytes are authorized.
- **Checksum/tag/content mismatch:** retain the original files and failed output;
  do not edit the manifest, rebuild, or retag to make checks pass.
- **Pip cannot find `0.1.0a2`:** confirm the production PyPI version page, the
  supported Python and the workflow's final status. A created pending publisher
  alone is not a published project. Preserve index-propagation diagnostics.
- **Private helper refuses the public repository:** expected legacy behavior;
  use this dedicated promotion workflow, not the historical helper's publish mode.

## Cleanup

Keep original wheel/manifests and `.artifacts/public-release/` evidence. Do not
commit caches, credentials, downloaded distributions or audit raw data. No
privileged temporary access, public server or network tunnel is created here.

## Evidence and audit record

Record audit revision, public `main` commit, unchanged a2 tag commit, source/wheel
hashes, workflow URL, owner approval, PyPI digest, anonymous-install outcomes and
any remaining limitations. Update the status and actual execution date only after
all acceptance gates complete; until then this runbook remains **Draft**.

## References

- [Pending PyPI publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
- [Trusted Publishing configuration](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
- [GitHub CLI workflow dispatch](https://cli.github.com/manual/gh_workflow_run).
- `.github/workflows/publish-pypi.yml` and `scripts/promote-pypi-a2.py` — executable promotion policy.
- [Historical private release evidence](releasing-private-legacy.md#evidence-and-audit-record).

## Document maintenance

Kha reviews this procedure if publisher identity, workflow permissions, source
scope, support policy or immutable-asset rules change. Do not turn the one-time
`a2` promotion into authorization for a new feature release.
