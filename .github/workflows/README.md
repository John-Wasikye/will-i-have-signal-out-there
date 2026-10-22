# Workflows

| Workflow | When | What it does |
|---|---|---|
| `ci.yml` | Every push and pull request | Lint, tests, the image build and scan, Terraform tests, secret and vulnerability scans, workflow lint. Never touches AWS. |
| `terraform.yml` | Pull requests to `main`, and merges to `main`, that change Terraform or the API | On a pull request: a plan for dev and live, in the job summary. On a merge: apply dev, then live. |
| `terraform-apply.yml` | Called by `terraform.yml` | Plans and applies one environment, inside its GitHub environment. |
| `deploy.yml` | Merges to `main` that change the site, the pipelines or the box | Builds the Airflow image on an arm64 runner, smoke tests and scans it, then deploys to dev, then live. |
| `deploy-environment.yml` | Called by `deploy.yml` | Builds the site with that environment's API address, uploads it, clears the CloudFront cache, and pushes the image tagged with the commit. |

The rules these follow are tested in `.github/tests/test_workflows.py`, and actionlint checks the files in CI.

## How access works

GitHub signs in to AWS through OIDC, so GitHub holds no AWS key. The roles come from the `github_roles` Terraform module (see its README):

- A pull request can use only the read-only plan role. It cannot read data and writes nothing.
- The apply and deploy roles trust only jobs that name the `dev` or `live` GitHub environment. GitHub starts such a job only after that environment's rules allow it, so those rules are the approval step.

## Setting it up

`terraform.yml` and `deploy.yml` skip every job until the repository variable `TF_STATE_BUCKET` exists, so CI stays green before AWS is set up. In order:

1. Apply the bootstrap, then `envs/live`, then `envs/dev`, by hand from my machine. The roles the workflows use are created by these applies.
2. Create the default branch `main` on GitHub.
3. In GitHub, Settings, Environments, create two environments:
   - `live`: required reviewer is me, and deployment branches are limited to `main`.
   - `dev`: deployment branches limited to `main`. A required reviewer is optional; without one, dev applies and deploys as soon as a change is merged.
4. Add the variables and the secrets below. None of the variables is secret: they are names, IDs and addresses, and the ARNs include the account number, which AWS does not treat as secret.

### Repository variables (Settings, Secrets and variables, Actions, Variables)

| Variable | Value |
|---|---|
| `AWS_REGION` | `us-east-1` |
| `TF_STATE_BUCKET` | Bootstrap output `state_bucket_name` |
| `TF_STATE_KMS_KEY_ARN` | Bootstrap output `state_kms_key_arn` |
| `TF_PLAN_ROLE_ARN_DEV`, `TF_PLAN_ROLE_ARN_LIVE` | Output `terraform_plan_role_arn` of each environment |
| `BOX_AMI_ID_DEV`, `BOX_AMI_ID_LIVE` | The arm64 image for the session box |
| `BOX_SUBNET_ID_DEV`, `BOX_SUBNET_ID_LIVE` | The public subnet for the session box |

The plan runs outside any GitHub environment, so the box settings are repository variables with the environment in their name.

### Repository secrets

| Secret | Value |
|---|---|
| `ALERT_EMAILS_DEV`, `ALERT_EMAILS_LIVE` | The alert addresses as a JSON list, for example `["me@example.com"]`. Optional: without them, nothing is emailed. |

They are secrets because the repository is public. Terraform also marks them sensitive, so plans in the public logs show only how many there are.

### Environment variables (on each of `dev` and `live`)

| Variable | Value, from that environment's Terraform outputs |
|---|---|
| `TF_APPLY_ROLE_ARN` | `terraform_apply_role_arn` |
| `DEPLOY_ROLE_ARN` | `deploy_role_arn` |
| `SITE_BUCKET` | `site_bucket_name` |
| `SITE_DISTRIBUTION_ID` | `site_distribution_id` |
| `AIRFLOW_REPOSITORY` | `airflow_image_repository` |
| `API_BASE_URL` | `api_url` |

## Things to know

- A change to the GitHub roles in dev fails in the workflow, because the dev apply role is refused changes to itself. I apply those changes by hand.
- `terraform.yml` and `deploy.yml` run side by side after a merge. When a change needs new infrastructure before the new site or image, I let the Terraform apply finish first, then rerun the deploy.
- The image is pushed with the commit as its tag. The box install script takes that tag as `IMAGE_TAG`.
