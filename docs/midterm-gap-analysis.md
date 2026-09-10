# Midterm completion gap analysis

Assessment date: 2026-09-10  
Source: `parcial12026-2-EN.docx.pdf` (6 pages)  
Scope: repository, automated checks, and read-only verification of the live AWS deployment

## Executive conclusion

The software and AWS implementation are substantially more complete than the
submission package. The critical reservation path, concurrency control,
separate OLTP/OLAP databases, Glue ETL, scheduler, crawlers, and catalogs exist.
The largest grading risk is that the required final document has not been
assembled and several design decisions remain formally unanswered even though
the code already embodies an answer.

The project is **not ready for final submission as-is**. The blockers are:

1. no final, consolidated submission document;
2. no completed application-level NFR table for all six mandatory categories;
3. 81 `[POR RESPONDER]` markers remain in the project-definition document;
4. the repository has no configured GitHub remote;
5. AWS evidence contains contradictory stale statements;
6. three required architecture/analytics PNG previews are missing from the
   working tree, while the documentation links to them;
7. the declared submission language is English, but most final-design and
   evidence documents are in Spanish.

These are primarily documentation, evidence, and packaging gaps. Rebuilding
the application is not the priority.

## Compliance matrix

| PDF requirement | Current evidence | Status | Remaining work |
|---|---|---|---|
| Context and explicit assumptions | `docs/01-definicion-del-proyecto.md` | Partial | Convert the questionnaire into approved statements; remove 81 unanswered markers and “proposed” language. |
| Team-specific constraint | Q-001 says the team received none | Partial | State this clearly in the final document and be ready to explain it; ideally retain professor confirmation. |
| FR table: ID, description, actor, priority | 40 detailed FRs in `docs/02-functional-requirements.md` | Strong but unapproved | Change status from “proposed baseline pending team confirmation”; explicitly approve inferred policy values. |
| Multi-leg, hold/payment, cancellation, agency decisions | FR-001–027 and implementation | Complete | Summarize the decisions in the final narrative rather than making the evaluator infer them. |
| NFR: performance | Q-052/053 unanswered | Missing | Define measurable p95/p99 targets, workload, data size, direct vs connection search, and evidence method. |
| NFR: consistency/concurrency | Q-054/055 proposed; real PostgreSQL tests documented | Strong | Promote to a formal NFR ID and link test results. |
| NFR: availability | Q-056/057 unanswered | Missing | Set target availability, measurement window, RTO/RPO, architecture implication, and Academy limitation. |
| NFR: security | Q-059–061 unanswered; controls exist in code/IaC | Partial | Formalize data classification, TLS/encryption/secrets/logging controls and applicable Colombian privacy assumption. |
| NFR: scalability | Q-058 unanswered; analytical 10× scenario exists | Partial | Define application workload growth and first bottleneck, not only analytical cost growth. |
| NFR: auditability | Q-062 unanswered; FR-035 and audit table exist | Partial | Set event scope and retention as a measurable NFR. |
| ER diagram in consistent notation | Draw.io ERD exists | Partial | Explicitly declare Crow's Foot and export a final legible PNG/PDF. Resolve the duplicate preview naming. |
| Brief dictionary per entity | `docs/data-dictionary.md` | Complete | Include or reference it from the final document and verify every ERD entity is present. |
| Explain multi-leg, recurring flight, seat assignment, inventory | schema, `database-design.md`, ADR-0001 | Complete | Consolidate justifications into the ER section. |
| Backend architecture and monolith decision | implementation and ADRs imply modular monolith | Partial | Add a dedicated design section connecting monolith, transactions, locking, payment simulation, B2B API, and ETL to FR/NFR IDs. |
| Frontend architecture | static client and `frontend/README.md` | Partial | Explain SPA choice against performance NFR; document stale-seat behavior, shared agency UI, COP-only scope, and language decision. |
| FastAPI search/create/query | live API and source | Complete | Capture stable evidence and link OpenAPI/commands. |
| Real concurrency mechanism | canonical `SELECT ... FOR UPDATE` | Complete | Keep the concrete 20-client × 30-repeat evidence in the final appendix. |
| Declare implementation deviations | three ADRs | Partial | Add one explicit “design vs implementation deviations” table; ADR existence alone is easy to miss. |
| Execution guide | backend/deployment/readme files | Complete but fragmented | Provide one root-level start-to-finish guide for evaluator use. |
| Source code on GitHub | local Git repository only; no remote configured | Missing | Create remote, push the final branch/tag, and record the URL and commit hash. |
| Separate PostgreSQL OLTP and OLAP | two live private RDS instances | Complete | Update stale evidence with identifiers sanitized as appropriate. |
| Functional ETL | two successful Glue runs observed | Complete | Capture run ID, timestamps, DPU-seconds, row counts, and reconciliation in final evidence. |
| Both databases in Glue Catalog | 12 OLTP and 13 OLAP tables observed live | Complete | Save reproducible CLI output or screenshots in the evidence appendix. |
| ETL choice and freshness/cost trade-off | hourly Glue trigger and analytics docs | Strong | Reconcile the active hourly trigger with the recommendation to disable it outside demonstrations. |
| Service justification table | `docs/analytics-architecture.md` | Strong | Ensure every AWS service in the actual stack is covered, including EC2, OLTP RDS, EBS/public IP, and the reused LabRole. |
| Cost projection and 10× scenario | `docs/cost-analysis.md` plus older estimates | Strong but inconsistent | Select one authoritative table and remove/revise conflicting USD 84.98 estimates. |
| Updated AWS architecture diagram | `.drawio` exists | Partial | Export `arquitectura-aws.drawio.png`; verify both RDS, Glue job, trigger, crawlers, catalogs, S3 endpoint, and network boundaries are readable. |
| Prompt-log appendix | `Prompts.md` | Partial | Turn it into a brief appendix mapping major prompt → refinement/correction → resulting artifact; remove workflow chatter that adds no defense value. |
| Complete final document | 22 separate Markdown documents | Missing | Assemble one English report in the exact order of sections 5.1–5.7 plus assumptions, deviations, evidence, costs, and prompt appendix. |
| Oral defense readiness | technical depth is present | Partial | Prepare short explanations and change-impact drills for the professor's scenario variations. |

## Verified implementation evidence

The following checks were performed during this assessment:

- live `GET /api/v1/health`: successful;
- Glue Catalog live inventory: 12 selected OLTP tables and 13 analytical
  tables;
- Glue trigger: activated, hourly at minute 0 UTC;
- Glue jobs: two successful runs; the scheduled run reported 131 seconds and
  262 DPU-seconds;
- local Python unit/API/analytics subset: 23 passed, one deprecation warning;
- frontend contract/DOM suite: 27 passed;
- positive and negative infrastructure validation: passed;
- one EC2 `t3.micro`, two private encrypted RDS PostgreSQL 16.10
  `db.t3.micro`, S3 artifacts bucket, two JDBC connections, two crawlers, two
  Glue databases, and the ETL job exist in the stack.

The full PostgreSQL integration/concurrency suite was not rerun in this audit.
The repository contains prior concrete evidence of 20 concurrent sessions,
30 repetitions, direct and two-leg cases (1,200 total attempts). Before final
submission it should be rerun once from a clean documented environment and its
fresh output captured.

## Contradictions and quality issues to fix

### Evidence contradicts live state

`docs/evidence/aws-deployment.md` still says analytics has not been deployed.
`docs/evidence/analytics-validation.md` starts with successful AWS deployment
evidence but ends by saying remote Glue/CloudFormation validation is pending.
Both are false at the current date and weaken trust in the submission.

### Requirements are not formally closed

`docs/02-functional-requirements.md` is marked “proposed baseline pending team
confirmation.” The source questionnaire still leaves performance,
availability, recovery, scale, security, privacy, audit, observability,
maintainability, model, backend, frontend, AWS evidence, costs, traceability,
and defense questions unanswered. Code cannot substitute for explicit
requirements in a rubric that grades declared decisions.

### Architecture documentation is fragmented

There is no single backend/frontend architecture chapter. The relevant facts
are distributed among the project questionnaire, README files, ADRs, code, and
analytics documents. The evaluator cannot trace every design decision from one
place to an FR/NFR without doing repository archaeology.

### Visual deliverables are broken

The diagram catalog links to:

- `diagramas/arquitectura-aws.drawio.png`;
- `diagramas/flujo-datos-analitica.drawio.png`;
- `diagramas/flujo-etl.drawio.png`.

All three are deleted in the current working tree. Only the editable Draw.io
sources remain. The ERD also has confusing duplicate preview names:
`airline-oltp-erd.drawio.png` is deleted while `airline-oltp-erd.png` is
untracked.

### Delivery state is unsafe

The analytical implementation, migration `0008`, diagram changes, evidence,
and cost report are uncommitted. There is no Git remote. A working AWS demo
cannot satisfy the explicit GitHub deliverable without a reproducible pushed
revision matching the deployed system.

### Language and presentation do not match the team's decision

Q-005 declares English, yet most architecture, analytics, deployment, and
evidence text is Spanish. The PDF is English. A final English document is the
safest coherent choice; internal Spanish notes can remain outside the submitted
artifact.

## Priority backlog

### P0 — required before submission

1. Write and approve a formal NFR table covering performance, concurrency,
   availability, security, scalability, and auditability with measurable
   conditions and explicit business risks.
2. Replace the questionnaire with final decisions or complete all 81 answers;
   remove “pending confirmation” status from the FR baseline.
3. Produce a single English final report following the PDF's order, with
   cross-references to FR/NFR IDs.
4. Regenerate all diagram previews and embed the ERD and AWS architecture in
   the report.
5. Correct contradictory AWS evidence and capture the live Glue catalog/job
   evidence.
6. Reconcile all cost tables around one dated authoritative projection. The
   measured current run-rate is about USD 67.41/month before credits; explain
   why older USD 84.98 assumptions differ.
7. Configure GitHub, commit a clean reproducible state, push, and record a
   release commit/tag in the report.
8. Rerun the real PostgreSQL concurrency test and full integration suite from
   the documented setup; preserve output with date and commit hash.

### P1 — needed for an outstanding score

1. Add a backend/frontend decision table: decision, alternative, FR/NFR,
   rationale, consequence.
2. Add an explicit deviations table describing what changed between initial
   ER/backend design and implementation and why.
3. Expand the AWS service table to cover every billable or architecturally
   relevant deployed component, not only analytical additions.
4. Convert `Prompts.md` into a concise appendix emphasizing human review,
   corrections, and resulting decisions.
5. Create a one-command or short evaluator path: clone, configure, start,
   migrate/seed, test, call API, inspect AWS evidence.
6. Add screenshots only where helpful for the oral defense; retain CLI/JSON
   output as reproducible primary evidence.

### P2 — hardening and defense preparation

1. Add explicit CloudWatch log retention and cost alarms or document them as
   production recommendations if Academy prevents implementation.
2. Explain the unencrypted EC2 root volume as a limitation; RDS is encrypted.
3. Measure host memory before considering EC2 downsizing.
4. Practice impact analysis for: aircraft change, late payment, partial
   cancellation, OLAP outage, 10× peak, stricter availability, and reduced
   budget.
5. Prepare a five-minute live demo with a fallback evidence package in case
   Learner Lab is unavailable.

## Rubric risk assessment

This is not a predicted professor grade. It identifies where evidence is likely
to land if submitted without remediation.

| Criterion | Current risk | Reason |
|---|---|---|
| Functional requirements (10%) | Medium | Detailed and scenario-specific, but still marked proposed and not integrated into a final document. |
| Non-functional requirements (10%) | **Critical** | Mandatory application-level categories and metrics remain unanswered. |
| ER model (15%) | Low–medium | Strong schema/dictionary, but notation is not formally declared and final preview is broken. |
| Backend/frontend design (15%) | High | Working implementation, but architecture decisions are fragmented and poorly connected to final NFRs. |
| First backend implementation (10%) | Low | Strong implementation and concurrency evidence; needs a fresh reproducible run and GitHub revision. |
| ETL, catalog, costs (20%) | Low–medium | Live and functional, but evidence and cost documents contradict older text and diagrams are missing previews. |
| Clarity and traceability (10%) | **Critical** | No consolidated document, 81 open answers, mixed language, stale evidence, and uncommitted artifacts. |

The visible rubric rows in the supplied PDF add to 90%, although the heading
says 20 points; the source appears to omit or misformat 10%. This should be
clarified with the professor rather than silently inventing a criterion.

## Definition of done

The project is ready to submit when a fresh clone of the GitHub release can:

1. open one English final report with every required section;
2. see measurable FR/NFR tables and follow every major architecture decision
   back to a requirement;
3. view the ERD and AWS diagram without Draw.io;
4. run the documented tests, including PostgreSQL concurrency;
5. verify or inspect captured evidence for two RDS databases, successful ETL,
   both Glue catalogs, and the scheduler;
6. reproduce the cost calculations and 10× scenarios from stated assumptions;
7. inspect a concise prompt/refinement appendix;
8. identify the exact Git commit that matches the evidence and deployment.
