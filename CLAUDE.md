# Incident drill repo: instructions for Claude

This repo is a sandbox for rehearsing incident response. The service, `clinic-hours`, serves
opening hours for a **fictional** county. All data is synthetic. Never add real people, patient
data or anything resembling PHI, even as examples.

## Releases and production
- Releases are git tags `vX.Y`. The `prod` tag marks what is deployed.
- The deployer follows `prod`. Rolling back = the `rollback` workflow moves `prod` to an earlier
  release. That workflow requires human approval in the `production` environment.

## When asked to diagnose an incident
1. Identify the release in production (`git tag --points-at prod`) and the previous release.
2. Read the release diff: `git diff <previous>..<current>` (full history and tags are fetched).
3. Relate the diff to the symptoms in the issue (error rate, error message, affected requests).
4. Reply with: likely cause (file and line), evidence, confidence, and a recommendation.
   If rollback is recommended, name the exact target tag. **Do not roll back yourself** and do
   not move or create tags; a human approves rollbacks.
5. Keep it short. Plain language; the readers are not all engineers.

## When asked to change code
1. Work on a new branch; never push to `main`.
2. Run `npm test` and report the result (pass/fail counts) in the PR description.
3. If the issue names the release the change is for (e.g. "v1.5"), set `version` in
   `package.json` to match (`1.5.0`) in the same PR. Do not create or move tags.
4. Open the pull request yourself with `gh pr create --base main` after pushing, and link
   it in your reply. Only if that command fails, post a "Create PR" link instead and say why.

## When asked for a postmortem
Open a pull request adding `lessons/YYYY-MM-DD-<slug>.md` with: summary, timeline, impact,
root cause, what went well, what didn't, and follow-up actions (e.g. a test that would have
caught it). Never push to `main` directly. Open the PR with `gh pr create --base main`.
