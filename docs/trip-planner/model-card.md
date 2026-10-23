# Project 1 model card

| Field | Value |
|---|---|
| Status | Draft for review. **No model has been trained and no evaluation has been run.** Every result field is empty on purpose until the first run |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Phase | B (both components). Phase A has no AI |
| Related | [design-doc.md](design-doc.md) (components C17 to C20), [requirements.md](requirements.md) (FR-34 to FR-48), [security-and-privacy.md](security-and-privacy.md) |

This card describes the two AI components of Project 1 and what is known about each. It states what the components are for, what they must not be used for, how they are tested, and where they fail. It is updated after every training run and every evaluation.

---

## 1. Components

| | Coverage confidence model | Trip-planning assistant |
|---|---|---|
| What it does | Predicts how likely the FCC coverage claim is to be right at a trail point and carrier. It gives a confidence level only where enough speed tests exist nearby. Elsewhere it gives "not enough measurements" (ADR 0008) | Answers a plain-language trip question with a check-in plan: where each carrier works, when satellite windows open, and how confident the map is. It cites the trail points and times it used. It says so when the data cannot answer (ADR 0017) |
| Kind | Supervised classifier. Scikit-learn is the planned library. The model family is logistic regression (ADR 0031) | Large language model: the cheapest Claude model from Anthropic (ADR 0034), calling a fixed set of metric tools through an MCP server |
| Where it is trained | Databricks Free Edition, tracked in MLflow (ADR 0014) | Not trained. Prompts are versioned in git |
| Where it runs | Nightly run scores each point with the copy of the chosen model in the repository. The site never depends on Databricks | Lambda behind API Gateway, from Phase B |
| Version | Recorded in each row of `fct_coverage_confidence` as `model_version` | Recorded in each answer as `prompt_version` |

## 2. Intended use

- Helping a hiker judge how far to trust the FCC coverage map at a trail point.
- Helping a hiker see when a Direct-to-Cell satellite could pass, and plan where to check in.
- Showing the confidence of each claim, and saying plainly when there are not enough measurements to judge.

## 3. Out of scope

- **Emergency communication.** Nothing here may be used to decide whether a call or text will get through in an emergency, or any decision where a missed message is a safety risk. The page wording that says so is open (OQ-22).
- **Any area outside the scope of the phase in use.** Phase A covers three Grand Canyon trails with one carrier. Its results do not describe other areas or carriers.
- **Later days than the prediction span.** The assistant answers only within the prediction span and says so (ADR 0021).
- **Commercial use.** The project is non-commercial (ADR 0013; Databricks Free Edition terms).

## 4. Data

### 4.1 Confidence model

| Input | Source | Notes |
|---|---|---|
| FCC coverage claim per cell and carrier | FCC mobile coverage files, H3 resolution 9 | The claim is a model's output, not a measurement |
| Ookla speed-test tiles | Ookla open data, quarterly, about 600 m tiles, GPS-accurate tests only | Speed tests exist only where phones already had signal. Dead zones are missing from the data |
| Terrain features | Copernicus GLO-30 | A surface model, so trees and buildings count as terrain (ADR 0004) |
| Distance to the nearest tower | OpenCelliD tower locations (ADR 0024) | Share-alike licence |
| Remoteness | Distance to the nearest road or trailhead, from published data. Source: TIGER/Line roads and NPS trail lines (ADR 0035) | Definition recorded in ADR 0024 |
| Labels | Hiker signal reports (Phase B), where at least N reports in one cell on one day agree (ADR 0008; N open, OQ-12) | Each report is from a different visitor, because of the one-per-cell rule. Reports arrive only from hikers who choose to tap |

Label volume is limited by the report caps: 10 reports a day per visitor and 50 a day for the whole system (ADR 0011). Labels accrue slowly.

### 4.2 Assistant

The assistant reads only through the metric tools, and the metric tools read the published tables. It never reads raw source files or the DynamoDB reports table. Raw SQL is a read-only, allowlisted fallback, and each use is logged separately (ADR 0017).

## 5. Evaluation

### 5.1 Confidence model

| Measure | Plan | Threshold |
|---|---|---|
| Agreement with held-out Ookla measurements, where enough tests exist | Compare each model version in MLflow on the same held-out split (method proposed; OQ-16) | Not set (OQ-16) |
| Coverage of the "not enough measurements" rule | Test on a sparse-area fixture (AC-1B.4, QR-17) | The page must show the notice and no confidence level there |
| Baseline | The FCC claim alone, with no confidence model. This is the version without AI, against which the model must show a gain (proposal, OQ-21) | Not set |

The exact split, the metric, and the accuracy threshold are set by John after the first scoring run (OQ-14, OQ-16). Until then, no accuracy figure is claimed.

### 5.2 Assistant

| Measure | Plan | Threshold |
|---|---|---|
| Correct, cited plans on sample questions | Ten sample trip questions, checked by hand (AC-1B.6) | Not set |
| Graded eval suite | 30 or more questions with known answers, including ones the data cannot answer. Graded exactly on tool choice, numbers and refusal (FR-45) | CI fails below the threshold (OQ-16) |
| Clarity | An LLM judge, a second model, scores clarity. It is calibrated on 50 answers John grades by hand (FR-46) | Agreement with John's grades is reported; threshold not set |
| Red team | 20 or more prompts: instructions hidden in source text, write requests, off-topic requests, cost abuse (FR-47) | CI fails below the threshold (OQ-16) |
| Numbers | The harness fails when an answer states a number that is not in the query result (AC-1B.5, QR-18) | Zero unsupported numbers |
| Later days | Questions about days beyond the span, where the correct answer is the statement of the limit (ADR 0021) | Must refuse the later day and say so |
| A/B | Two prompt versions compared through votes in DynamoDB (FR-48) | Result reported; no winner is assumed |

### 5.3 Results

No results exist yet. The results section is filled in when the first run happens. It records the date, the model version or prompt version, the eval scores, the agreement with John's grades, and the A/B result. Nothing is copied from another project.

## 6. Known failure cases

These are known in advance from the design. Each one is tested or shown on the page where possible.

| Failure | Why it happens | What the system does |
|---|---|---|
| Overconfident in dead zones | Speed tests are missing where phones had no signal | No confidence level where tests are too few. The page shows the "not enough measurements" notice (ADR 0008) |
| Claims the FCC map is right when it is not | The FCC coverage is a modeled claim | The page says the coverage is a map claim. The wording is set in ADR 0037 |
| Trees and buildings counted as terrain | The elevation model is a surface model (ADR 0004) | Stated as a limitation. The effect on horizons is measured later (OQ-24) |
| Biased labels | Only hikers who choose to report, and only where they have a signal to report | Labels only where N reports agree. Reports that contradict nearby reports are set aside (ADR 0012) |
| Few labels, slow learning | Report caps (10 a day per visitor, 50 a day for the system) | Retraining waits until there are enough labels (OQ-13) |
| Remoteness is a rough proxy | Distance to a road or trail line is not a measure of signal. The trail network stands in for trailheads | Listed as an input. Its value is checked in evaluation (ADR 0035) |
| Wrong numbers in an answer | A model can state a figure it did not read | The harness fails an answer with a number that is not in the query result (AC-1B.5) |
| Answers about a later day | Windows exist only for the span | Refused, with a statement of the limit (ADR 0021) |
| Instructions hidden in text change the answer | Source text and user questions are untrusted | Source text is data. Tools are read-only and allowlisted. Red team tests this (FR-47) |
| Answer when the data cannot answer | The model may try to be helpful | The answer says so. The eval suite tests refusal (FR-44) |

## 7. Safety and privacy

- The confidence model sees only cells and aggregated speed tests. It never sees a visitor ID or exact coordinates.
- Reports carry no visitor ID, so a label cannot be linked to a visitor (ADR 0009, ADR 0011).
- The assistant is given no write tool (ADR 0017).
- Each model call is logged with its model, prompt version, tokens, latency and cost. The question text is not stored in the log (platform contract `llm_calls`). It is not stored (ADR 0033).
- The question text goes to the model provider. The provider's terms are recorded before the first call (OQ-39, ADR 0034).
- Spending is capped: $10 a month, a daily question cap and a token limit per answer (FR-42).

## 8. Updates and monitoring

- **Confidence model:** retrained only after the labels reach the level set in OQ-13. Each training run is tracked in MLflow. The chosen model and its results are copied to the repository by hand (ADR 0014). The nightly run uses the copy in the repository. A results file that carries the run ID must be in the repository after each run (FR-37).
- **Assistant:** the prompt version is recorded in every answer. Changes to prompts are made in git and evaluated in CI before they reach the site. The model is changed only when the evals justify the cost (FR-65, Phase C).
- **Monitoring:** calls and costs are in the nightly `llm_calls` table. Traces are in AWS X-Ray. Grafana reads X-Ray during work sessions (design doc, section 12.3).

## 9. Licences

- Ookla open data: CC BY-NC-SA 4.0. Confidence values derived from it are shared under the same licence, and the exact notice is shown (ADR 0013).
- OpenCelliD: share-alike. Confidence values that use tower distance carry the same licence (ADR 0024).
- Databricks Free Edition: non-commercial.
- Model provider: Anthropic. Terms to be recorded before the first call (OQ-39).

## 10. Open items

| Item | Tracked in |
|---|---|
| Remoteness source | OQ-18 |
| Enough nearby tests for a confidence level | OQ-14 |
| Labels needed to retrain; the N that makes a label | OQ-13, OQ-12 |
| Eval, judge and red-team thresholds | OQ-16 |
| Assistant daily cap and token limit | OQ-17 |
| Baseline for the assistant (the version without the model) | Proposed here; approve with the design doc (OQ-21) |
