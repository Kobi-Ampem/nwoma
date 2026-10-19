# Nwoma: project brief

Decisions agreed on 19 Oct 2026. This file records why the project is shaped the way it is.

## What Nwoma is

**Nwoma** (Asante Twi: paper, book, document) turns messy clinical documents, PDFs or scans in English
or French, into structured, coded and verified patient records. A clinician reviews only the fields
the system is unsure about, and the result is exported as FHIR.

It transcribes. It never diagnoses, interprets results or recommends treatment.

## Decisions

| Decision | Choice |
|---|---|
| Name | Nwoma. No company name: one was only needed for a pitch exercise. |
| Repo | `Kobi-Ampem/nwoma`. A rename stays possible: GitHub redirects old URLs, but a GitHub Pages URL does not, so settle the name before the demo link is shared. |
| Document types | Lab reports and referral letters, in English and French, digital and scanned |
| Data | Synthetic only: Synthea patients rendered through templates, so every label is exact and no real patient data is ever used |
| Extraction | A fine-tuned multilingual encoder, with an LLM fallback for low-confidence fields (the cascade) |
| Codes | LOINC for lab tests, ICD-10 for diagnoses, mapped by hybrid retrieval |
| Output | FHIR R4 Bundle with Provenance (which fields a human confirmed) |
| Pricing (business design) | Free (€0, 100 documents a month, own model only) · Clinic (€49 a month, regional price for West Africa, 2,000 documents then €0.03 each, full cascade) · Hospital (annual licence: compliant hosting, records-system integration, single sign-on, audit log, SLA). Proposed prices; only the Free behaviour is built. |

## Architecture: only what is necessary

Rule for this build: no over-engineering. If a simpler way is effective, use it.

| Instead of | Nwoma uses | Why the simpler way is enough |
|---|---|---|
| S3 upload + SQS queue + worker | One synchronous `POST /extract` | A document takes seconds; a spinner is enough |
| A database of records | Nothing stored: review in the browser, FHIR download | No data to secure or retain, which is also a privacy feature |
| Cognito accounts | No accounts | The demo only handles synthetic documents |
| S3 + CloudFront for the frontend | GitHub Pages | Free, nothing to configure |
| AWS CDK | One AWS SAM template | One function does not need a CDK project |

**AWS footprint:** one Lambda container image behind a function URL, ECR, SSM Parameter Store for
the LLM key, reserved concurrency as a throttle and kill switch, a budget alarm, 7-day log retention,
and an OIDC role for GitHub Actions. **$0 a month inside the free tier**; ECR storage costs roughly
$0.05 a month after the first 12 months.

Every service left out gets an ADR saying what a production version would add, and what would
trigger adding it.

## Milestones

| Version | Target date | Contents |
|---|---|---|
| v0.5 | ~16 Nov 2026 | Data generator, both extractors, cascade, code mapping, evaluation report (command line) |
| v1.0 | ~28 Nov 2026 | Validation agent, API, review UI, deployment, MCP server |

Estimated effort: about 94 hours.
