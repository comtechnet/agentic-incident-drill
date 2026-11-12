# Postmortem: clinic-hours server errors after v1.4 (synthetic drill)

- **Date:** 2026-11-11
- **Issue:** #2
- **Status:** Resolved by rolling back `prod` to `v1.3`
- **Note:** This was a synthetic drill. All data is fictional.

## Summary

Release `v1.4` added Saturday hours to the clinic lookup response. The new code crashed for any
clinic with no Saturday entry in `data/clinics.json`. Requests for towns that include such
clinics (Fernhill and Ashby in the probe) returned HTTP 500. The error rate reached 36% (4 of 11
requests in 30 seconds), above the 10% alert threshold. `prod` was rolled back to `v1.3` after
human approval, and the monitor confirmed recovery.

## Timeline (America/Indianapolis)

| Time | Event |
|---|---|
| 11:33:33 AM EST | Alert raised: errors at 36% on v1.4.0 |
| 11:33:43 AM EST | Diagnosis requested by pilotadmin |
| 11:34:49 AM EST | Claude posted diagnosis: likely cause `src/clinics.js:20`, recommend rollback to `v1.3` |
| 11:35:01 AM EST | Go given by pilotadmin in Mattermost |
| about 11:46:17 AM EST | Rollback approved by comtechnet in the `production` environment |
| 11:46:22 AM EST | Rollback workflow finished; `prod` moved to `v1.3` |
| 11:46:26 AM EST | Deployer switched production to `v1.3` |
| 11:46:35 AM EST | Monitor confirmed recovery |

Roughly 13 minutes passed between the alert and recovery. About 11 of those were between the
"go" and the approval of the rollback in the `production` environment. The delay was not a
slow decision: the approver was not signed in to GitHub, and the approval link posted in
Mattermost did not make clear which run to open. Once found, the approval took seconds.

## Impact

- 4 of 11 requests failed in the 30-second alert window (36%).
- The synthetic probe showed Fernhill and Ashby returning 500. Millbrook, Cedar Falls and
  Quarry Point returned 200.
- Lookups for towns with a clinic lacking Saturday hours failed. In `data/clinics.json`, 16 of
  20 clinics have a `sat` entry, so 4 do not. Which requests failed depended on which town was
  asked for.
- No data was lost or changed. The failure was in reading and formatting.

## Root cause

In `v1.4`, `toResult` in `src/clinics.js` (line 20) added `saturday: formatHours(clinic.hours.sat)`.
`formatHours` (line 9) calls `range.split('-')`. When a clinic has no `sat` entry, `range` is
`undefined` and the call throws `TypeError: Cannot read properties of undefined (reading 'split')`,
which the service returns as a 500.

The weekday fields were already safe because every clinic has weekday hours. Saturday is the
first field that is legitimately absent for some clinics, and the code assumed it was always
present.

The new test in `v1.4` only looked up Millbrook, whose clinic has Saturday hours, so it passed
and did not exercise the missing-data case.

## What went well

- The alert fired within seconds of the first errors, and the threshold was crossed clearly.
- The relay's synthetic probe by town pointed straight at the affected towns.
- The diagnosis took about a minute and named the file, line, evidence and exact rollback target.
- Nobody rolled back or moved tags without a human. The rollback needed approval in the
  `production` environment, and the approver recorded their reasoning.
- Rollback to `v1.3` restored service, and the monitor confirmed it.

## What didn't go well

- The bug shipped because the tests only covered data that had the new field.
- Nothing in the release process checks new code against all records in `data/clinics.json`.
- Most of the time to recovery was waiting for approval, not diagnosing. The approver had to
  sign in to GitHub and then work out which run the approval link referred to.
- The diagnosis only checked two towns' data (Fernhill and Ashby) by hand. That was enough for
  the decision here, but it was not a full check of every town.

## Follow-up actions

| Action | Why |
|---|---|
| Make `saturday` optional in `toResult`, e.g. `clinic.hours.sat ? formatHours(clinic.hours.sat) : null`, before re-releasing the feature | Fixes the crash |
| Add a test that looks up a clinic with no Saturday hours (e.g. Fernhill) | This test would have failed on `v1.4` and caught the bug before release |
| Add a test that runs `toResult` over every clinic in `data/clinics.json` | Catches any future field that is missing for some records |
| Run the town probe against every town in CI or a pre-prod check before `prod` moves | Would have shown the 500s before users did |
| Consider making `formatHours` fail clearly (or handle `undefined`) instead of throwing a bare `TypeError` | Easier to diagnose and less likely to turn into a 500 |
| Review whether the approval step can notify approvers more directly | Shortens the wait between "go" and approval |
