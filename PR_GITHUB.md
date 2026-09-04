# PR → GitHub Action → Admin Dashboard

How a pull request's LeakGuard result ends up on the admin dashboard, and how
issues are told apart as **new to this PR** vs **pre-existing in the repo**.

## What this covers

Any repo that runs the LeakGuard GitHub Action on its pull requests can report
each run's pass/fail result and findings to this project's backend, and see
them on `/admin`. This is **not specific to this repo** — it works for any
repo that wires up the Action the same way (see [Wiring up a
repo](#wiring-up-a-repo) below). Right now, this repo (`VH-BitwinInit`
itself) is wired up as the first example.

## End-to-end flow

```
PR opened/updated on a repo
        |
        v
GitHub Actions runs the LeakGuard Action (same `leakguard` CLI, in Docker)
        |
        v
CLI scans the code, decides pass/fail against --fail-on
        |
        v
CLI POSTs a summary to <report-url>/api/reports/action-run
   { repo, pr_number, sha, user_id, conclusion, summary, findings }
        |
        v
Backend saves it in MongoDB (`action_runs` collection)
   + fingerprints each finding (rule_id + file + line) and records who
     first introduced it, in `repo_issues`
        |
        v
Admin dashboard reads it back via /api/admin/* endpoints
```

Reporting is **best-effort**: if the backend is down or `report-url` is
unset, the CLI just skips this step and CI still passes/fails normally on
the leak check itself.

## Wiring up a repo

Add `report-url` to the LeakGuard Action step in the repo's workflow:

```yaml
- name: Run LeakGuard
  uses: leakguard-org/leakguard@v1   # however the Action is published
  env:
    LEAKGUARD_USER_ID: ${{ github.actor }}   # attributes the run to the PR author
  with:
    path: "."
    fail-on: "error"
    report-url: "https://vh-bitwininit.onrender.com"
```

For this repo specifically, `report-url` is read from a GitHub Actions
**repository variable** instead of being hardcoded — see
`.github/workflows/leakguard-selftest.yml`:

```yaml
report-url: ${{ vars.LEAKGUARD_REPORT_URL }}
```

Set it once under **Settings → Secrets and variables → Actions → Variables**
→ `LEAKGUARD_REPORT_URL` = the backend's base URL. Unset, it's just a no-op.

## What shows up where

| Page | Route | Shows |
|---|---|---|
| Admin dashboard | `/admin` | Totals across all repos, per-repo table (last result, run/PR counts), recent activity feed |
| Repo detail | `/admin/repos/:repo` | Every PR reported for that repo, full run log (PR + push runs mixed), "current issues" from whichever run happened most recently |
| **PR detail** | `/admin/repos/:repo/prs/:prNumber` | Every run reported **for that one PR**, and the issue breakdown from its latest run |

The PR detail page is the one that answers "what's wrong with *this* PR
specifically" — the repo detail page's "current issues" section is
whichever run reported last, which could be a push or a different PR.

## New vs. pre-existing issues

Every finding is fingerprinted by `(rule_id, file, line)`, **scoped to the
repo** — not to a PR or a run. The first run anywhere in the repo's history
to report a given fingerprint "owns" it.

On any PR's page, each issue is tagged:

- 🆕 **new, this PR** — this exact fingerprint has never been reported
  anywhere in the repo before. This PR is the first place it showed up.
- 🕰️ **pre-existing** — this fingerprint was already recorded by an earlier
  run (a different PR, or a push). This PR's branch just still contains it —
  the PR author didn't introduce it. The card shows who *did*, and when.

This is why a PR opened today can show a leak from three weeks ago tagged
"pre-existing, first reported by `alice`" instead of blaming whoever
happened to touch that file next.

## API reference

All under `/api/admin`:

| Endpoint | Returns |
|---|---|
| `GET /overview` | Global totals: repos, runs, PR runs, findings |
| `GET /repos` | One row per repo: run/PR counts, last result |
| `GET /recent?limit=` | Most recent runs across all repos |
| `GET /repos/{repo}/logs` | Every run for a repo (PR + push) |
| `GET /repos/{repo}/issues` | Issue breakdown from the repo's most recent run |
| `GET /repos/{repo}/prs` | One row per PR number reported for a repo |
| `GET /repos/{repo}/prs/{pr_number}/logs` | Every run reported for that one PR |
| `GET /repos/{repo}/prs/{pr_number}/issues` | Issue breakdown from that PR's most recent run |

`{repo}` is the full `owner/name` string, URL-encoded (e.g.
`test%2Fdashboard-check`).

Reports come in via a separate endpoint, called by the CLI, not the
frontend:

| Endpoint | Purpose |
|---|---|
| `POST /api/reports/action-run` | Called by `leakguard scan --report-url`. Body: `{repo, pr_number, sha, user_id, conclusion, summary, findings}` |

## Known limitations

- **No auth.** Both the admin dashboard and `/api/reports/action-run` are
  open — anyone who knows the backend URL can read every repo's data or post
  fake runs. Fine for a demo, not for anything real without adding auth.
- **`user_id` is just a free-text string** (`github.actor` by default) —
  there's no verification that whoever reports a run actually is that
  GitHub user.
