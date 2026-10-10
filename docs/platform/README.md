# Platform: shared infrastructure for the five projects

**Scope: shared by all five projects (Projects 1, 2, 3, 4 and 5).** This is not Project 4's own documentation. Each project's own documents are in its folder (`Will I have signal out there/` to `Mission Control/`) and link here.

Documentation set for the platform. The platform is the shared infrastructure that all five projects run on: repository and CI, cloud base, the nightly session box, the serving template, status and incidents, and the operating rules (cost, storage, privacy, security). It is written first. Each project's documents link here instead of repeating it.

Status: draft, awaiting John's review and approval. Owner: John (GitHub: jwasikye). Last updated Oct 9, 2026.

## Documents

| Document | What it covers |
|---|---|
| [requirements.md](requirements.md) | Platform skeleton steps 0.1 to 0.5, operations hardening (1B.9), engineering standards, quality requirements and acceptance checks |
| [design-doc.md](design-doc.md) | The 17-section design doc: architecture, components, runtime, deployment, cross-cutting concerns, risks, open questions, glossary |
| [adrs/](adrs/) | Platform decision records (23 significant ones; the 9 minor ones are in [decisions.md](decisions.md)). The 17 superseded drafts were removed as duplicate old versions on Oct 9, 2026 |
| [contracts/](contracts/) | Data contracts for the shared tables and the published status file |
| [openapi-serving-template.yaml](openapi-serving-template.yaml) | The API spec for the serving template that each project's API copies |
| [operations.md](operations.md) | Platform schedule, monitoring, cost limits, runbooks for platform failures, backups and retention |
| [security-and-privacy.md](security-and-privacy.md) | Keys, roles, environment separation, Terraform state, platform threats |
| [platform-requirements.md](platform-requirements.md) | Working draft of the same platform parts, written during the Project 1 review. Where it differs from the documents above, the documents above win |
| [changelog.md](changelog.md) | Record of each revision |

## Not yet written

The Documentation Plan lists these as written while building, so they are not in this set yet:

- Reference generated from code (docstrings, dbt docs, API docs, Terraform docs). Generated once the code exists.
- Blameless postmortems for real incidents. Each one is written after the incident (step 0.5).
- Platform licence register: the project-level registers are in each project's security document.
- Model card: the platform's on-call agent is in the second round and gets a model card then.

## Open questions

Section 16 of the [design doc](design-doc.md) lists the open questions. Answered questions stay in the table with the answer and the ADR number, so references still resolve.
