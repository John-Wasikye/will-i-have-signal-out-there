# github_roles module

I use this module to give the GitHub workflows their AWS access, one set per environment. GitHub signs in through OIDC, so no AWS key is stored in GitHub (ADR-0007). An account has one OIDC provider; in my account the NFL project's Terraform owns it, and these roles trust it by its ARN.

GitHub writes the kind of job into the token it sends to AWS. A pull request job says `pull_request`. A job that names a GitHub environment says `environment:<name>`, and it only starts after that environment's rules let it, for example a required reviewer or a branch rule. Each role below trusts exactly one of those.

| Role | Used by | Can do |
|---|---|---|
| `portfolio-<env>-terraform-plan` | Pull requests in this repository | Read the settings of everything (AWS's `ReadOnlyAccess`) and its own state file. It is refused data files, Parameter Store values, Secrets Manager, DynamoDB records and logs, because a pull request can come from any branch. It writes nothing, so plans run with `-lock=false`. |
| `portfolio-<env>-terraform-apply` | Jobs in the `<env>` GitHub environment | Everything (`AdministratorAccess`), because Terraform creates roles, functions and buckets. The GitHub environment's rules are the guard. |
| `portfolio-<env>-deploy` | Jobs in the `<env>` GitHub environment | Upload the site to the site bucket, clear the CloudFront cache, and push to its own image repository. It is refused `published/` and `status.json`, which the box writes. |

Dev and live share one AWS account, so the dev apply role is also refused:

- anything named `portfolio-live-*` or `portfolio_live*`, and the live state file
- the budget, which `envs/live` owns
- any change to itself, so it cannot remove these refusals. It may still read itself (`iam:Get*`, `iam:List*`), because Terraform reads every resource before it plans. A change to this role in dev is applied by hand, from my own machine.

The account also runs other projects, such as the NFL site. Both apply roles, dev and live, are refused every resource whose name contains one of `protected_names` (each environment passes `nfl-` for the NFL site), the exact resources in `protected_arns` (its two GitHub roles and its CloudFront distribution), and any change to the OIDC provider, which another project owns. A new project in the account must be added to those lists.

IAM refuses an ARN whose service is a wildcard (`arn:aws:*:...`), so "refuse anything named X" is written once per service the projects use; the list is `regional_services` in `main.tf`. A resource in a service missing from that list is not refused, so a project that starts using a new service must add it there. The first live apply failed on a wildcard service, so a test and a variable check now refuse one.

Otherwise the live apply role has no refusals. Its GitHub environment allows only the main branch and waits for my approval.

The roles are created by the same Terraform they run, so the first apply of each environment is done by hand.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `github_repo` | string | `John-Wasikye/will-i-have-signal-out-there` | Repository whose workflows may use the roles. |
| `site_bucket_arn` | string | none | This environment's site bucket. |
| `distribution_arn` | string | none | This environment's CloudFront distribution. |
| `registry_arn` | string | none | This environment's image repository. |
| `protected_names` | list(string) | `[]` | Name fragments of other projects in the account, for example `nfl-`. |
| `protected_arns` | list(string) | `[]` | Exact ARNs of other projects' resources whose names carry no protected name. Each must name its service. |

## Outputs

| Name | Description |
|---|---|
| `plan_role_arn` | GitHub repository variable `TF_PLAN_ROLE_ARN_<ENV>`. |
| `apply_role_arn` | GitHub environment variable `TF_APPLY_ROLE_ARN`. |
| `deploy_role_arn` | GitHub environment variable `DEPLOY_ROLE_ARN`. |
