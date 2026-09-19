# Safety-gated pull-request review agent

The review agent collects automated review results without silently changing source code. Its primary invariant is:

> A bot suggestion must be fetched, shown in the report and explicitly approved by a human before an apply operation can be authorized.

The service supports GitHub.com and GitHub Enterprise Server by configuring `GITHUB_API_URL`. For GHES, use the `/api/v3` base URL. It retrieves both:

- `GET /repos/{owner}/{repo}/pulls/{number}/reviews`
- `GET /repos/{owner}/{repo}/pulls/{number}/comments`

Every readiness response contains the review summaries and inline comments used to reach its decision. A report that has not been fetched remains `pending`.

## Configuration

Configuration is read from the default branch and must be nested below `beacode`:

```yaml
beacode:
  target_branch: main
  fork_support: false
  review_request_changes: true
  reviewer_login: beacode[bot]
  pr_checks:
    - name: security-scanner-alerts
      scope: diff
```

Security alerts are opt-in. At least one check name must contain `security-scanner`; otherwise Dependabot and code-scanning APIs are not called. `diff` keeps only alerts whose paths changed in the pull request. `repo` returns all open repository alerts and is intentionally noisier.

## Fork latch

Eligibility is stored when the `opened` event is processed. Changing `fork_support` later does not reactivate that stored pull request. The safe sequence is:

1. Merge configuration to the target branch.
2. Close the skipped pull request.
3. Open a fresh pull request so the new policy is latched.

Independent security workflows are outside this latch and continue according to their own GitHub Actions configuration.

## Approval flow

1. A review operator records the PR-open event.
2. The service fetches review summaries, inline comments and configured security alerts.
3. The complete report is presented to the user.
4. A principal with `review-approver` records approval for one fetched comment ID.
5. Only then can a `review-operator` request an apply authorization.

The current service deliberately returns an authorization record; it does not edit a branch. A future patch executor must consume that authorization, bind it to the exact head SHA and remain a separately permissioned component.

## Authentication

Use OIDC in shared environments. The development identity mode is only for a local lab. Required roles are:

- `review-operator`: ingest, refresh and request apply authorization;
- `review-approver`: approve a previously displayed suggestion.

The GitHub token requires pull-request read permission. Security alert collection additionally requires the corresponding security-events access. Store tokens in a secret manager and never commit them.
