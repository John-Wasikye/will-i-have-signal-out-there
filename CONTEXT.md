# Context for the next session

I wrote this file so I can pick the work up again without the earlier conversation. It holds the state, the decisions I made, and what comes next. The project overview is in [README.md](README.md), and my working rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Where things are

- Repo: this folder, on my computer. The work is on the branch `feature/platform-skeleton`.
- GitHub: the repository is pushed to GitHub as a public repository. I push only the feature branch. I never push to `master` without asking.
- Planning documents: I keep the original build plan and design documents outside the repo. Copies of the approved platform documents are in `docs/`.
- The requirements, decision records and data contracts for the trip planner are not copied into this repo yet.

## Where the build is

The trip planner, Will I have signal out there?, platform skeleton steps 0.1 to 0.5 of my build plan.

Done and verified:
- Python: 128 tests pass on my machine, and 2 are skipped there. The skipped tests run and pass in CI on Linux: 5 on real Spark and Iceberg, and 6 Airflow DAG tests on Airflow 3.3.2. `ruff check .` passes.
- Site (`app/`): typecheck passes, 4 tests pass and the build passes.
- Terraform: `terraform fmt -check` is clean, and `terraform validate` passes for `envs/dev` and `envs/live`. Every module has Terraform tests that pass: storage (11), iam (7), catalog (3), visitor_data (5), budget (3), parameters (3), session_box (10), box_iam (7), serving (8) and site (7). Nothing is applied to AWS.
- The session box creates a persistent spot instance, starts it at 10:00 UTC (off in dev), hard-stops it at 14:00 UTC, and stops it when idle. `box_iam` gives it and the scheduler their roles.
- The API package builds for real: `python platform/serving/build_package.py` makes an arm64 zip that is 22.6 MB zipped and 64.7 MB unzipped. The Lambda copies published files from S3 before it answers.
- The site and the API are connected to dev and live. Only the site's CloudFront distribution can read the site bucket, and CloudFront blocks the `published/` folder.
- The box install files are in `platform/box` and have tests that I wrote first: the Airflow chart settings are tested on the real rendered chart (10 tests), the install script in dry-run mode (13 tests), and the database backup tool (22 tests). The Airflow image builds and passes its smoke test on my machine. Shellcheck passes on both scripts.
- GitHub CI runs six jobs on every push, and all pass on the latest commit: Python, Spark, Airflow, site, Terraform, and security scans.

Not done, in order:
1. The Terraform state bootstrap (`platform/terraform/bootstrap`) is written but not applied. Applying it creates AWS resources, so I will ask first.
2. The box files exist but have never run on a real box. I still need to run `install.sh` on a real spot instance, push the image to a registry (ECR), and measure memory and the idle threshold. Spark runs inside the scheduler in local mode; the Spark operator is the next step. Nothing creates an Airflow login yet. The two-hour nightly maximum check (`nightly_limit.py`) and the spot warning handler (`spot_interruption.py`) are written and tested, but nothing calls them yet.
3. The nightly DAG does not yet call the incident record or the run metrics for failures beyond the publish step.
4. First-run checks on AWS: the Lambda concurrency cap of 10 may be refused on a new account, and the arm64 image manifest must be checked before the box uses it.
5. A review pass over every file, looking for dead code and unclear names.
6. Site lint in CI. Typecheck is already in CI.

## Decisions I made (with the default I used)

- Repo name: `will-i-have-signal-out-there`, because the repository holds this one project and its platform.
- Licence: MIT for the code. Data keeps its own licence. I added this when I asked for a licence to be included.
- Test-driven development is required for all code. Code must be reviewable and replicable by a person.
- The platform design document is still marked Draft. I treated my go-ahead to start coding as approval to build to it.
- Open questions from the platform design document, with the defaults I used:
  - OQ-P05, preview deploys: not decided. Preview links are not built.
  - OQ-P06, Airflow database backups: not built yet.
  - OQ-P07, Iceberg retention: 7 days for snapshots and 3 days for orphan files, in `iceberg_maintenance.py`. I will replace these after measuring real table sizes.
  - OQ-P08, freshness: the sample pipeline uses 26 hours.
  - OQ-P10, Parameter Store path check: not built.
- Terraform minimum version is `>= 1.6`, as the spec says. The `use_lockfile` setting needs 1.10, so I should raise the minimum to 1.10.
- The GitHub OIDC provider is created only by `envs/live`. I apply live before dev the first time.
- Budget notifications are created only when `alert_emails` is set.
- Dev roles trust any ref in the repo, as the spec says. This is a known gap: any branch can get a dev role token, but dev roles cannot reach live data.
- The IAM module exposes `github_subject` as an output, so the tests can check the trust rule at plan time.
- A third-party warning from Starlette's test client is filtered in `pyproject.toml`, with a comment. I will remove the filter when the test client changes.
- I removed as dead code: the gate's freshness and value-range checks, and the site's `needsLateNotice`. Nothing used them. I will add each back test-first when a pipeline needs it.

## Rules I set for this work

- Write tests first. Never weaken a test to make it pass.
- Code must be reviewable and replicable by a person. No slop.
- Ask before committing to `master`, before any push to a new place, and before merging a pull request.
- No `Co-Authored-By` lines and no "Generated with Claude" footers in commits or pull requests.
- Consult only on major decisions. For everything else, pick the default and list it in the final message.
- Use at most two Haiku subagents at a time.
- Resolve every warning before moving on.
- Public text uses no em dashes and no spaced hyphens used as dashes, and it is written in first person.
- Keep personal details and local file paths out of the public repo.

## Known problems and gaps

- The serving, publish, status and metrics code was written before its tests. The tests were not written first, so I treat them as checks on the existing behavior.
- The site's tests were also written after the code.
- The CI actions are pinned to major versions, not commit SHAs. I will pin them to SHAs before going live.
- Terraform writes `.terraform.lock.hcl` files. I keep them in git, because they hold provider versions and no secrets.
- The `aws-mcp` tool server failed to connect in my session, with a timeout. I do not need it for this work so far.

## How to run the checks

See the README, section "Run the checks yourself". The short version:

```powershell
.\.venv\Scripts\Activate.ps1
ruff check .
pytest
cd app; npm test; npm run build
```
