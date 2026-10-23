# Project 1: Will I have signal out there. Decision log

This log holds only Project 1's decisions. It was split out of the shared logs on Oct 9, 2026; the originals are in `Project_Documentation\_archive\`.

## Answered by John (Oct 9, 2026)

Answers are recorded in this project's requirements, design doc and ADRs. Where an answer covers more than one project, the "Projects" column says which.
Text in parentheses was added later, when the answer was acted on; the answer itself is unchanged.

| # | Projects | Question | Answer |
|---|---|---|---|
| 1 | 1, 2, 3, 4, 5 | What a page shows when a nightly run is late or failed | Show the old data with a visible late notice (and the time of the last good run). Do not hide it. Applies to all five projects, including Project 1 (replaces "expired windows hidden"). |
| 3 | 1, 5 | How ML results leave Databricks Free Edition | Manual export (download results and model, commit to GitHub). An open question stays to test whether automation is possible. |
| 5 | 1 | Satellite window span | Predict 26 hours (24 plus the 2-hour nightly maximum) so there is no daily gap. The page still says "the next 24 hours". |
| 6 | 1 | Offline batches vs the hourly report limit | Apply the limits by the hour the report was made on the phone, not by arrival time. |
| 7 | 1 | Trip assistant and future days | Limit the assistant to the predicted window span and say so for later days. |
| 8 | 1 | Report limits | 10 reports a day per visitor (replaces 10 an hour and 50 a day per visitor); the whole system accepts at most 50 a day; caps to be raised as traffic grows. |
| 9 | 1 | Counting "enough different visitors agree" | N reports in the same cell on the same day (one report per cell per visitor per 24 hours means each is a different visitor). N stays an open number. |
| 12 | 1 | DynamoDB recovery vs 30-day deletion | Point-in-time recovery turned OFF for the hiker reports table (deletion final at 30 days). Other tables keep it on. |
| 13 | 1 | IP addresses in CloudFront and API Gateway logs | Logs may be written, but addresses are removed before anything is stored beyond a short delete window. |
| 14 | 1 | Phase A carrier | T-Mobile (only carrier with a confirmed satellite service, T-Satellite over Starlink). Confirmed by the plan's [DTC] first-run check. |
| 15 | 1 | Phase A trails | Bright Angel, South Kaibab and North Kaibab, names checked against the NPS data in the first-run download. |
| 18 | 1 | Phase B model inputs | Add OpenCelliD tower locations for distance to nearest tower. Its share-alike license means derived data carries the same license (record in the license register and on the page). "Remoteness" still needs a definition. |
| 19 | 1 | Phase label for report location | The build plan is right: step 1B.8 (Phase B). The Build Plan Decisions label "(A)" on that row is a typo. |
| 38 | 1 | Meaning of "remoteness" | Distance to the nearest road or trailhead from published data; source chosen later. |

## Open (reviewer round 1, Oct 9, 2026)

These are as recorded on Oct 9, 2026. The current status of each is in this project's design doc, section 16 (or its open questions section).

- Satellite windows cover 24 hours from a 10:00 UTC run, so the page shows none for roughly 45 minutes to 2 hours every day (OQ-23).
- "Enough different visitors agree" cannot be counted when reports carry no linking ID (OQ-12).
- Offline report batches exceed the 10-an-hour limit (OQ-26).
- The "Saturday" assistant example asks beyond the 24-hour window (OQ-27).
- No source for tower distance or remoteness; model family unstated (OQ-18).
- Databricks Free Edition to GitHub copy needs outbound internet (OQ-19).
- "One carrier" and "main trails" are never named (OQ-11, OQ-36).
- Report location is Phase A in Build Plan Decisions but step 1B.8 in the plan (OQ-37).
- DynamoDB point-in-time recovery may keep deleted raw reports past 30 days (OQ-31).
- CloudFront and API Gateway logs may hold IP addresses (OQ-29).

## Answered by John after the split (Oct 9, 2026)

These answers came after the log above was split out. Each is recorded in its ADR and in the design doc, section 16.

| Question | Answer | Record |
|---|---|---|
| OQ-42: AWS region for dev and live | us-east-1 | ADR 0034 |
| OQ-43: how long report copies are kept | Raw rows deleted 30 days after the copy in DynamoDB, the lake and Snowflake; daily per-cell counts kept | ADR 0034 |
| OQ-39: model provider | Anthropic API, cheapest Claude model | ADR 0034 |
| OQ-18: remoteness source | U.S. Census TIGER/Line roads plus NPS trail lines | ADR 0035 |
| OQ-17: assistant spend | $10 a month (replaces $15) | ADR 0038 |
| OQ-22: credit wording and page wording | Approved as drafted in ADR 0037 (OpenCelliD and FCC mobile data still to verify) | ADR 0037 |
| OQ-24: horizon defaults | Approved as proposed in ADR 0036 | ADR 0036 |

## Minor defaults chosen by Claude (John can change any of them)

These were decided under John's instruction to settle minor questions with a clear best-practice answer, security first.

| Question | Default | Record |
|---|---|---|
| OQ-38 visitor ID | 128 random bits, stored on the server as a keyed hash | ADR 0025 |
| OQ-26 report days and counter lifetime | UTC day; reports up to 48 hours old; counters expire 72 hours after their day | ADR 0026 |
| OQ-23 late-data rule | Late when the validity time has passed or the last run did not publish | ADR 0027 |
| OQ-25, OQ-30, OQ-33 refresh, stream and time grain | Reference data recomputed only on source change; 2-hour watermark; one row per UTC minute | ADR 0028 |
| OQ-28, OQ-29 limits and log window | Starting Lambda and API limits; access logs kept 7 days | ADR 0029 |
| OQ-35 area counts | H3 resolution 6 areas; counts shown only from 5 reports in 7 days | ADR 0030 |
| OQ-11 carriers and model family | Every carrier in the park's FCC files; logistic regression first | ADR 0031 |
| OQ-32 pinned versions | ODCS 3.0.2 and OpenAPI 3.0.3 | ADR 0032 |
| OQ-39 votes and question text | Votes hold no visitor ID and are deleted after 90 days; question text is not stored | ADR 0033 |
| OQ-41 counters recovery | Point-in-time recovery off for the counters table | ADR 0025 |
| Set-aside rows and call-log retention | Set-aside rows follow the 30-day rule; the call log is kept 90 days | ADR 0034 |

## Minor decisions (folded from ADRs)

These decisions were first written as separate ADRs. They are minor (a setting, a wording rule, a format or a repeat of a platform rule), so they were folded into this table on Oct 9, 2026. The old ADR numbers are kept so existing references still resolve. The full detail of each is in the design doc, section 14.

| Old ADR | Decision | Status |
|---|---|---|
| ADR-0013 | Show the Ookla license notice on the page and in the README | Accepted |
| ADR-0019 | Predict 26 hours of satellite windows so there is no daily gap | Accepted |
| ADR-0020 | Phase A carrier is T-Mobile; Phase A trails are Bright Angel, South Kaibab and North Kaibab | Accepted |
| ADR-0021 | The trip-planning assistant is limited to the prediction span | Accepted |
| ADR-0022 | Point-in-time recovery is off for the hiker reports table | Accepted |
| ADR-0023 | Internet addresses are removed from logs before anything is kept beyond a short log retention period | Accepted |
| ADR-0025 | Visitor ID: a 128-bit random value on the phone, stored on the server only as a keyed hash | Accepted |
| ADR-0026 | Report limits count by UTC day; reports are accepted only within 48 hours; counters expire 72 hours after their day | Accepted |
| ADR-0027 | Data is late when its validity time has passed or the last scheduled run did not publish | Accepted |
| ADR-0028 | Reference data refreshes only when its source changes; the orbit stream and dim_time have fixed parameters | Accepted |
| ADR-0029 | Starting limits for Lambda, API throttling, reserved concurrency, and a 7-day log window | Accepted |
| ADR-0030 | Report counts are shown per H3 resolution 6 area, and only where at least 5 reports exist | Accepted |
| ADR-0031 | Start the confidence model with logistic regression; Phase B carriers are every carrier in the park's FCC files | Accepted |
| ADR-0032 | Pin ODCS v3.0.2 and OpenAPI 3.0.3 | Accepted |
| ADR-0033 | Votes carry no visitor identity and are kept 90 days; assistant question text is not stored by the project | Accepted |
| ADR-0038 | The assistant's monthly spend limit is $10; 20 questions a day; 2,500 input and 800 output tokens per answer | Accepted |
