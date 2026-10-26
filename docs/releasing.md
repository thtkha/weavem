# Release a private Weavem alpha

| Field | Value |
| --- | --- |
| Status | Source-verified |
| Owner | Repository maintainer with write access to `thtkha/weavem` |
| Escalation | Private GitHub issue in `thtkha/weavem`, with the release tag and workflow URL |
| Last verified | 2026-10-26 — workflow and package metadata inspected; new cross-runner gate awaits remote execution |
| Last executed | 2026-10-26 — `v0.1.0a1` published; subsequent workflow changes have not published another release |
| Applies to | Private GitHub releases for `weavem` alpha versions |
| Risk | Medium — pushing a tag creates an immutable release record visible to repository readers |

> **Verification claim:** This procedure is traced to `pyproject.toml` and
> `.github/workflows/verify.yml`. The first alpha was published successfully after
> retrying publication; the newly added cross-runner gate has not yet run remotely.

## Purpose and successful outcome

Release a Weavem alpha to private repository readers, without PyPI. The automation
builds one wheel, tests that same wheel on Python 3.12–3.15 and latest stable
Python, verifies prebuilt native task/flow handoff to separate matching-minor
runners, then publishes a GitHub prerelease with the wheel and `SHA256SUMS`.

Success means the alpha tag points to the tested `main` commit, every required
workflow job passes, and the downloaded wheel passes `sha256sum -c SHA256SUMS`.

## Scope

Use this only for an unused version already set in `pyproject.toml`.
`0.1.0a1` is already published and must not be reused. Select and commit a new
alpha version before starting this procedure; do not overwrite the first release.
Do not use it for stable releases, PyPI publication, repository-visibility changes,
or replacing existing assets. Stable release automation does not exist yet.

## Safety and stop conditions

The blast radius is private repository readers: they can download the release
assets. The point of no return is the tag push. Stop if the checkout is dirty,
`main` is not current, the tag already exists, package metadata disagrees with the
tag, or any verification job fails. Do not move tags, force-push, rebuild an asset
for publication, delete assets, or manually publish a draft.

## Ownership and escalation

The repository maintainer executes and approves this change. For a workflow or
asset failure, open a private repository issue containing the tag, commit SHA,
workflow URL, asset names, and output with secrets removed.

## Prerequisites and inputs

Run Bash on Linux from the repository root, with Git, Python 3.12–3.15, and an
authenticated GitHub CLI. `gh auth status` must show an account with write access;
`git remote get-url origin` must report `https://github.com/thtkha/weavem.git`.

| Variable | Required | Description | Safe example |
| --- | --- | --- | --- |
| `TAG` | Yes | Unused alpha Git tag matching package version | `v0.1.0a2` |
| `VERSION` | Yes | Version read from package metadata | `0.1.0a2` |

The candidate must already be merged into `main`, and the latest `Verify Weavem`
**push** run for that exact `main` commit must have concluded successfully.

## System and repository orientation

`pyproject.toml` is the version source of truth. `.github/workflows/verify.yml`
builds a named wheel artifact once, shares it with the supported Python and
latest-stable lanes, and permits only an alpha tag from `main` to publish. The
supported lanes transfer their published native stores to separate consumer
jobs; publication also requires all four consumer jobs to pass. The
publish job attaches the tested wheel and `SHA256SUMS`; retry logic reuses matching
assets and stops on conflicts. The workflow has no stable-release automation.

## Preflight checks

### Step 1 — verify the candidate

**Goal:** Confirm the private repository, clean `main`, version, and unused tag.

**Run from:** Repository root in Bash, targeting `origin/main`.

**Action:**

```bash
set -euo pipefail
gh auth status
test "$(gh repo view thtkha/weavem --json isPrivate --jq .isPrivate)" = true
git fetch origin main --tags
git switch main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
VERSION="$(python3 -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')"
TAG="v${VERSION}"
MAIN_SHA="$(git rev-parse HEAD)"
test "${MAIN_SHA}" = "$(git rev-parse origin/main)"
test "$(python3 -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')" = "${VERSION}"
python3 -c 'import re, sys; sys.exit(0 if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+a[0-9]+", sys.argv[1]) else 1)' "${TAG}"
test -z "$(git tag -l "${TAG}")"
REMOTE_TAG="$(git ls-remote --tags origin "refs/tags/${TAG}")"
test -z "${REMOTE_TAG}"
MAIN_RUN_ID="$(gh run list --repo thtkha/weavem --workflow "Verify Weavem" --branch main --event push --commit "${MAIN_SHA}" --limit 1 --json databaseId,status,conclusion --jq '.[0] | select(.status == "completed" and .conclusion == "success") | .databaseId')"
test -n "${MAIN_RUN_ID}"
```

**Expected result:** All checks exit zero. No local or remote tag exists, and
`MAIN_RUN_ID` identifies a successful `push` workflow run for `MAIN_SHA`.

**If this fails:** Stop. Resolve the stated mismatch before release; use a new
alpha version when a tag already exists. If the run lookup is empty, the exact
commit is untested or not green; do not substitute a run from another commit.
Never reuse an existing tag.

**Evidence to retain:** Candidate commit SHA, package version, `MAIN_RUN_ID`, and
`gh` account.

**Repeatability:** Safe to repeat; it does not change the remote repository.

## Procedure

### Step 2 — push the immutable alpha tag

**Goal:** Start verification and private prerelease publication for the checked
`main` commit.

**Run from:** Repository root in Bash, targeting `origin`.

**Action:**

```bash
set -euo pipefail
git tag -a "${TAG}" -m "Weavem ${VERSION} alpha release"
git push origin "${TAG}"
```

**Expected result:** Git reports the new remote tag and GitHub starts `Verify
Weavem` for it.

**If this fails:** If the tag is only local, repair the safe local error or run
`git tag -d "${TAG}"`. If it was pushed, stop and escalate; do not delete or move it.

**Evidence to retain:** `git rev-parse "${TAG}^{commit}"` and the workflow URL.

**Repeatability:** Not repeatable after a successful push.

### Step 3 — inspect automated publication

**Goal:** Confirm all lanes passed and GitHub published the tested wheel.

**Run from:** Repository root in Bash, targeting `thtkha/weavem`.

**Action:**

```bash
set -euo pipefail
TAG_SHA="$(git rev-parse "${TAG}^{commit}")"
RUN_ID=""
for ATTEMPT in $(seq 1 12); do
  RUN_ID="$(gh run list --repo thtkha/weavem --workflow "Verify Weavem" --branch "${TAG}" --event push --commit "${TAG_SHA}" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  test -n "${RUN_ID}" && break
  sleep 10
done
test -n "${RUN_ID}"
gh run watch "${RUN_ID}" --repo thtkha/weavem --exit-status
sleep 10
gh release view "${TAG}" --repo thtkha/weavem --json isPrerelease,isDraft,body,url,assets
```

**Expected result:** Python 3.12–3.15, latest-stable, and all separate native
handoff consumer jobs are successful. The
release is not a draft, is a prerelease, identifies the tag commit in its notes, and contains one
wheel plus `SHA256SUMS`.

After successful draft creation, automation checks immediately, then retries a
missing draft after waits of 1, 2, 4, and 8 seconds. API errors and identity or
checksum conflicts still stop immediately. It never retries the create command.
If the draft remains invisible, it reports a **draft visibility timeout**; this
does not mean creation failed.

**If this fails:** Preserve the tag, logs, draft, and assets. A draft visibility
timeout can be recovered by waiting for GitHub to show the draft and rerunning
only the failed publication job below. If GitHub reports another
transient runner, network, or publication failure rather than a code, test, or
metadata failure, rerun only failed jobs and watch the same run:

```bash
gh run rerun "${RUN_ID}" --repo thtkha/weavem --failed
gh run watch "${RUN_ID}" --repo thtkha/weavem --exit-status
```

This retains the already built candidate. For code, test, tag, version, or checksum
failure, fix forward in a new commit and release a new alpha version. Do not upload
replacement assets.

**Evidence to retain:** Workflow URL, `RUN_ID`, release URL, commit SHA, and asset list.

**Repeatability:** Read-only inspection is safe to repeat. Rerun failed jobs only
for a transient failure; it does not authorize changing the candidate.

## Verification

### Step 4 — verify the downloaded bytes

**Goal:** Check the published wheel independently of the publication command.

**Run from:** Repository root in Bash, targeting the private release.

**Action:**

```bash
set -euo pipefail
mkdir -p .artifacts/release-download
DOWNLOAD_DIR="$(mktemp -d ".artifacts/release-download/${TAG}.XXXXXX")"
gh release download "${TAG}" --repo thtkha/weavem --dir "${DOWNLOAD_DIR}" --pattern "weavem-*.whl" --pattern "SHA256SUMS"
cd "${DOWNLOAD_DIR}"
sha256sum -c SHA256SUMS
```

**Expected result:** `sha256sum` prints `OK` for the wheel.

**If this fails:** Stop distribution and escalate with the checksum output and
release URL. Do not overwrite the assets.

**Evidence to retain:** `SHA256SUMS`, successful checksum output, release URL, and
commit SHA under the gitignored `.artifacts/release-download/` directory.

**Repeatability:** Safe to repeat; each invocation uses a new gitignored
`.artifacts/release-download/` directory.

## Rollback and recovery

A pushed tag and release are not retagged or overwritten. Before a push failure,
the local tag recovery is:

```bash
set -euo pipefail
git tag -d "${TAG}"
git status --short
```

Expect a deleted local tag and no unexpected working-tree change. After a remote
tag exists, forward recovery is a corrected commit with a new alpha version. Keep
the failed tag, draft, workflow logs, and assets as evidence.

## Troubleshooting

- **Tag exists:** stop; choose a new alpha version.
- **Verification job fails:** fix in a new commit and restart from Step 1.
- **Asset or checksum conflict:** stop publication; preserve the draft and report
  the asset name and checksum.
- **Release is not visible:** run `gh auth status` and confirm private-repository
  access.

## Cleanup

Keep `.artifacts/release-download/` evidence until release review completes. Do
not delete existing tags, release assets, CI artifacts, or historical evidence.

## Evidence and audit record

Record tag, commit SHA, Verify Weavem workflow URL, private release URL, wheel
filename, SHA-256, and confirmation that no PyPI publication occurred.

First release: [`v0.1.0a1`](https://github.com/thtkha/weavem/releases/tag/v0.1.0a1),
verified on 2026-10-26 in [workflow run 40312643304](https://github.com/thtkha/weavem/actions/runs/40312643304).
Publication succeeded on the second attempt, reusing the original candidate;
this run predates the separate-runner native handoff gate.

## References

- `pyproject.toml` — package version and Python support.
- `.github/workflows/verify.yml` — build, verification, and publication logic.
- [GitHub CLI release creation](https://cli.github.com/manual/gh_release_create).

## Document maintenance

Review this guide when package versioning, workflow triggers, release visibility,
asset names, or retry behavior change. Record each release's date, tag, workflow
URL, and verification result in the release evidence.
