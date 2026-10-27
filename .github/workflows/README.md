# Workflows

| Workflow | When | What it does |
|---|---|---|
| `ci.yml` | Every push and pull request | Lint, tests, the image build and scan, Terraform tests, secret and vulnerability scans, workflow lint. Never touches AWS. |
| `terraform.yml` | Pull requests to `main`, and merges to `main`, that change Terraform or the API | On a pull request: a plan for dev and live, in the job summary. On a merge: apply dev, then live. |
| `terraform-apply.yml` | Called by `terraform.yml` | Plans and applies one environment, inside its GitHub environment. |
| `deploy.yml` | Merges to `main` that change the site, the pipelines or the box, or when I start it from the Actions tab | Builds the Airflow image on an arm64 runner, smoke tests and scans it, then deploys to dev, then live. |
| `deploy-environment.yml` | Called by `deploy.yml` | Builds the site with that environment's API address, uploads it, clears the CloudFront cache, and pushes the image tagged with the commit. |

The rules these follow are tested in `.github/tests/test_workflows.py`, and actionlint checks the files in CI.

## How access works

GitHub signs in to AWS through OIDC, so GitHub holds no AWS key. The roles come from the `github_roles` Terraform module (see its README):

- A pull request can use only the read-only plan role. It cannot read data and writes nothing.
- The apply and deploy roles trust only jobs that name the `dev` or `live` GitHub environment. GitHub starts such a job only after that environment's rules allow it, so those rules are the approval step.

## Setting it up

`terraform.yml` and `deploy.yml` skip every job until the repository variable `AWS_SET_UP` is `true`, so CI stays green before AWS is set up. In order:

1. Apply the bootstrap, then `envs/live`, then `envs/dev`, by hand from my machine. The roles the workflows use are created by these applies.
2. Make `main` the default branch on GitHub.
3. In GitHub, Settings, Environments, create two environments:
   - `live`: required reviewer is me, and deployment branches are limited to `main`.
   - `dev`: deployment branches limited to `main`. A required reviewer is optional; without one, dev applies and deploys as soon as a change is merged.
4. Add the secrets and variables below.
5. Create every parameter listed under `parameters` in `checks/parameter_paths.yaml`, in dev and live, as SecureString in Parameter Store. The pull request plan fails until each one exists.
6. Set `AWS_SET_UP` to `true` last.

### Why most settings are secrets

The repository is public, so anyone can read the workflow logs and job summaries. AWS does not treat the account number as secret, but I keep it out of public view anyway. GitHub hides a secret's value wherever it appears in a log and prints a variable as it is, so every value that holds the account number is a secret, and so is the account number itself (`AWS_ACCOUNT_ID`), which hides it inside longer text such as the ARNs in a Terraform plan. Each AWS sign-in also sets `mask-aws-account-id`. Hiding secrets is a log feature, and I do not rely on it for the job summary, so the plan masks the account number itself before it writes the plan there.

### Repository secrets (Settings, Secrets and variables, Actions, Secrets)

| Secret | Value |
|---|---|
| `AWS_ACCOUNT_ID` | The AWS account number |
| `TF_STATE_BUCKET` | Bootstrap output `state_bucket_name` |
| `TF_STATE_KMS_KEY_ARN` | Bootstrap output `state_kms_key_arn` |
| `TF_PLAN_ROLE_ARN_DEV`, `TF_PLAN_ROLE_ARN_LIVE` | Output `terraform_plan_role_arn` of each environment |
| `ALERT_EMAILS_DEV`, `ALERT_EMAILS_LIVE` | The alert addresses as a JSON list, for example `["me@example.com"]`. Optional: without them, nothing is emailed. Terraform also marks them sensitive, so plans show only how many there are. |

### Repository variables (Settings, Secrets and variables, Actions, Variables)

| Variable | Value |
|---|---|
| `AWS_SET_UP` | `true` once everything else here exists |
| `AWS_REGION` | `us-east-1` |
| `BOX_AMI_ID_DEV`, `BOX_AMI_ID_LIVE` | The arm64 image for the session box |
| `BOX_SUBNET_ID_DEV`, `BOX_SUBNET_ID_LIVE` | The public subnet for the session box |

The plan runs outside any GitHub environment, so the box settings are repository variables with the environment in their name.

### Environment secrets and variables (on each of `dev` and `live`)

| Name | Kind | Value, from that environment's Terraform outputs |
|---|---|---|
| `TF_APPLY_ROLE_ARN` | secret | `terraform_apply_role_arn` |
| `DEPLOY_ROLE_ARN` | secret | `deploy_role_arn` |
| `SITE_BUCKET` | secret | `site_bucket_name` |
| `AIRFLOW_REPOSITORY` | secret | `airflow_image_repository` |
| `SITE_DISTRIBUTION_ID` | variable | `site_distribution_id` |
| `API_BASE_URL` | variable | `api_url` |

## Things to know

- A change to the GitHub roles in dev fails in the workflow, because the dev apply role is refused changes to itself. I apply those changes by hand.
- `terraform.yml` and `deploy.yml` run side by side after a merge. When a change needs new infrastructure before the new site or image, I let the Terraform apply finish first, then rerun the deploy.
- The image is pushed with the commit as its tag. The box install script takes that tag as `IMAGE_TAG`.
