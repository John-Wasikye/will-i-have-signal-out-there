# Will I have signal out there?

A trip planner for hikers, campers and backpackers. Pick a trail and see where each carrier has coverage, where it drops out, and when a Starlink Direct-to-Cell satellite text could get through. This repository holds the shared platform and the first project's code.

The project is in its first phase. The platform skeleton is being built, and it is not yet deployed to AWS.

## What is built

| Part | Folder | Status |
|---|---|---|
| Serving API (FastAPI, DuckDB over Parquet, Lambda handler) | `platform/serving` | Built, tested |
| Publish gate, write-audit-publish, status and run metrics | `pipelines/platform/publish` | Built, tested |
| Spark job writing an Iceberg table | `pipelines/platform/spark/sample_iceberg_job.py` | Built, tested with a fake Spark session |
| Iceberg maintenance task | `pipelines/platform/spark/iceberg_maintenance.py` | Built, tested with a fake Spark session |
| Nightly Airflow DAG | `pipelines/platform/dags` | Built, not run (Airflow does not install on Windows) |
| Site template (React, TypeScript) | `app` | Built, tested |
| Terraform (storage, catalog, IAM, budget, parameters, visitor data) | `platform/terraform` | Built, validated and tested with mock plans. Nothing applied to AWS |
| Continuous integration | `.github/workflows/ci.yml` | Written. Not yet run on GitHub |
| Dev container | `.devcontainer` | Written. Not yet opened in Codespaces |

Not built yet: the session box (k3s, Airflow and Spark on spot instances), the AWS deployment, the GitHub remote, the Terraform state bucket, the status page on a live site, and the Project 1 trail data.

## Run the checks yourself

These steps assume Windows and PowerShell. Python 3.11, Node 24 and Terraform 1.16 are needed.

### 1. Python tests and lint

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
pytest
```

Expected: `ruff` reports `All checks passed!`, and `pytest` reports the tests passing, with one test skipped because Airflow is not installed on Windows.

### 2. Site

```powershell
cd app
npm ci
npm run typecheck
npm test
npm run build
npm run dev
```

`npm run dev` starts a local preview. The status page reads `app/public/status.json`.

### 3. Terraform

```powershell
cd platform\terraform\modules\storage
terraform init -backend=false
terraform test
cd ..\..\..\..
terraform fmt -check -recursive platform\terraform
```

The module tests use a mock AWS provider and make no AWS calls. The IAM module tests use the real provider with three values overridden, so they also make no AWS calls.

## Working rules

- Tests come first. For each new behavior, write a test, watch it fail, then write the code that makes it pass. See [CONTRIBUTING.md](CONTRIBUTING.md).
- Every timestamp is UTC. The page converts it to local time.
- Every key lives in AWS Parameter Store. None is stored in this repository or in GitHub.
- The platform design is in [docs/platform](docs/platform). The planning documents are in [docs](docs).

## License

The code is under the MIT license ([LICENSE](LICENSE)). The data used by each project keeps its own license, and the project notes list them.
