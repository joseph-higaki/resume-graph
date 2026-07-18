# Upload report — 2026-07-17 artifact ingestion

Ingestion of the resume artifacts in `input/` into `vault/_data/`. This report is the
handoff for a future Claude Code session to **interview the owner** and resolve every
open item below. Requested as `doc/uppload_report_20260717.md` in `next-prompts.md`;
normalized to `docs/upload_report_20260717.md`.

> **STATUS — 2026-07-18: the interview was run. See "Interview resolutions" immediately
> below.** Everything from "## Sources processed" onward is the original 2026-07-17
> ingestion record, kept for history. Parts of it are now stale: several open items are
> resolved, the two EPAM positions it names were replaced by four, and all three
> RoleFramings were deleted. Trust the resolutions section over the historical body.

---

## Interview resolutions — 2026-07-18

### Original checklist status

1. **RoleFraming wordings + IBM title — RESOLVED.** All three RoleFraming *instances*
   deleted (owner: "no audience override yet"); the `rg:RoleFraming` *class* stays for
   the private repo. IBM title = "Team Leader - Application Development" (LinkedIn form).
2. **Verizon / Scotiabank granularity — RESOLVED.** Verizon kept at 4 positions;
   Scotiabank kept at 2 (standalone, not grouped); TransSolutions = 1 org, 3 positions.
3. **IBM team size / HLS geographies — PARTIAL.** Geographies RESOLVED = Europe/LATAM/APAC
   (LinkedIn). **IBM team size 11 vs 16 still PENDING.**
4. **Org casing — RESOLVED.** LinkedIn casing (australworks, InOrbis Analytics,
   TransSolutions Systems).
5. **Date approvals — PENDING.** Month→day expansion and project startDate assumptions not
   explicitly blessed. (FS split boundaries approved: FS-A ends 2022-12, FS-B 2023-01→2024-09.)
6. **Cert/education date modeling + cloud-azure — PENDING.** Schema decision, untouched.
7. **`ai` category — PENDING confirm.** Category exists and validates; not formally blessed.
8. **Skill-level calibration + stubs — RESOLVED** (details below); stub *promotion* PARKED.
9. **Skipped certs — PENDING.**
10. **Canonical summary + jobTitle — PENDING.** Now interacts with the Semantic Web PM
    headline; `profile` still reads "Delivery Manager - Healthcare & Life Sciences" /
    "Software Engineer". Recommended next item.
11. **Languages / honors — PENDING.**

### EPAM restructure + new `rg:titleOfRecord` (beyond the checklist; `make all` green)

A single employment with rotating functional roles over time is modeled as multiple
`rg:Position` nodes sharing an `rg:titleOfRecord` (the HR title), each with its own
`roleName` (headline) + dates. The export groups by (organization, titleOfRecord). The two
old EPAM positions were **deleted** and replaced by four:

| roleName | titleOfRecord | dates | engagement |
|---|---|---|---|
| Project Manager and Team Lead | Delivery Manager - Financial Services | 2022-02 → 2022-12 | Corporate Action Workflow Management |
| Program Manager and Technical Product Owner | Delivery Manager - Financial Services | 2023-01 → 2024-09 | Personal Investor Data Modernization |
| Delivery and Staffing Manager | Delivery Manager - Healthcare & Life Sciences | 2025-05 → 2025-09 | — (T&M staffing) |
| Semantic Web Technologies Program Manager | Delivery Manager - Healthcare & Life Sciences | 2025-10 → present | — (evidence anchor: Ontology Engineering + Knowledge Graphs) |

- `roleName` = export headline; `rg:titleOfRecord` = HR title, set **only** on grouped
  positions (standalone ones omit it). **Do not de-duplicate the grouped EPAM entries —
  the repetition is intentional.**
- Engagement-specific bullets re-homed to their Project; role-level bullets to the Position.
- `rg:titleOfRecord` is a new `owl:DatatypeProperty` — ontology note + rg context key +
  `PositionShape` constraint. **Schema-domain: commit apart from data.**
- HLS-B carries a `TODO(owner)` placeholder bullet — needs real scope/outcomes, and a
  decision on whether hands-on SPARQL/SHACL/RDF/OWL claims are warranted from that role.

### Fabricated node removed

`Personal Finances Lakehouse` was scaffold, not a real project — **deleted**. It was the
sole evidence for five skills, which correctly collapsed to stubs (the anti-stuffing
mechanism working as designed): **dbt, Amazon Athena, AWS IAM, BigQuery, Google Cloud
Storage**. Python/Docker/SQL/AWS S3 survived on their other, real evidence.

### Skill calibration (item 8)

- **Basis = peak proficiency** (recency conveyed by position dates), not current.
- **AI skills** (Anthropic Claude, Generative AI, Prompt Engineering) stay `working`.
- **Bumped aware→working:** Amazon Aurora, Java, OWL.
- **Stay `aware`** (honest oversight): AWS Lambda, DynamoDB, ECS, EKS, Appian, GraphQL.
- **BigQuery + GCS:** owner wants `working`, but they lost their (fabricated) evidence with
  PFL — **parked** until a real Position/Project evidences them.
- **Stub promotion (14 stubs) PARKED** pending the owner's incoming personal GitHub repos,
  the intended real evidence anchors for the pivot skills.

### Still-open reality check

Confirm **`Biomedical GraphRAG Bench`** is a real repo — after the PFL removal it is the
sole evidence for Docker and a key anchor for Knowledge Graphs / SPARQL / RDF / Python.

### Commit hygiene (nothing committed yet)

Three pure commits pending per the pre-commit purity hook:
- **schema:** `rg:titleOfRecord` (ontology note, rg `context.jsonld`, `validation/shapes.ttl`).
- **data:** 4 new positions, 2 position deletions, bullet/skill repoints, PFL deletion, level changes.
- **mechanism:** `tests/test_validate.py` (two fixture retargets — the general-audience framing target and the AWS S3 evidence spot-check).

---

## Sources processed

| Source | File | Vintage | Role in reconciliation |
|---|---|---|---|
| S1 | `input/linkedin_profile.pdf` | 2026-07 export | Primary: positions, dates, education, summary |
| S2 | `input/linkedin_certifications.pdf` | 2026-07 export | Primary: certifications |
| S3 | `input/linkedin_skills.pdf` | 2026-07 export | Primary: skill inventory (~80 skills) |
| S4 | `input/joseph.higaki.cv.en.202509.pdf` | 2025-09 | Bullet detail, engagement-level projects, metrics |
| S5 | `input/Joseph Higaki - Product and Delivery Manager.docx` | ~2025 (EPAM-branded) | Alternative framings; **names the pharma client — excluded** |
| S6 | `input/linkedin_CCAF-skills.png` | 2026 | Skills certified by Claude Certified Architect – Foundations |
| S7 | `input/linkedin_data-engineering-zoomcamp-skills.png` | 2026 | Skills certified by Data Engineering Zoomcamp |

Note: `next-prompts.md` labeled the CCAF png as the "overall list of skills" — it is
actually the CCAF cert's skill list; the overall list is `linkedin_skills.pdf` (S3),
which was not named in the prompt but was present in `input/` and ingested.

## What was ingested

- **16 positions** (replacing 2 seed placeholders), modeled at LinkedIn granularity:
  2× EPAM, 2× australworks, 1× InOrbis, 2× Scotiabank, 1× TamboSolar, 1× IBM,
  4× Verizon, 3× TransSolutions Systems.
- **9 engagement projects** hung off positions via `deliveredDuring` (EPAM 2, InOrbis 2,
  Scotiabank 2, IBM 1, TamboSolar 2). The 3 self-directed seed projects kept.
- **~45 new skills** + evidence rewiring of existing ones; 1 new SKOS category (`ai`).
- **15 certifications**, **5 education credentials**, **36 bullets** (audience-tagged),
  **3 role framings**, updated **profile**.
- **20 new organizations**; seed placeholders (Acme Consulting, State University,
  BSc Computer Science, seed EPAM position + bullets, seed framing) deleted.

---

## 1. Title/wording conflicts → RoleFramings created (interview: resolve wording)

Per the prompt, conflicting wordings were captured as `rg:RoleFraming` notes rather
than silently picking one. Each needs owner confirmation:

| Framing note | Position | Audience | roleName captured | Origin of conflict |
|---|---|---|---|---|
| `dm-epam-hls-delivery` | DM Healthcare & Life Sciences — EPAM | delivery | "Product and Delivery Manager" | docx CV headline vs LinkedIn title |
| `dm-epam-fs-data-eng` | DM Financial Services — EPAM | data-eng | "Delivery Manager / Technical Product Owner" | LinkedIn body ("Technical Project Coordinator / Proxy Technical Product Owner / Program Management") + CV ("Acted as technical Product Owner") vs plain title |
| `dm-epam-fs-ai-eng` | DM Financial Services — EPAM | ai-eng | "Engineering Delivery Lead" | carried over from seed framing (was `dm-epam-ai-eng`); wording never confirmed |

Wording conflicts **not** turned into framings (word-order variants, no audience
dimension — resolve by picking one):

- IBM: "Team Leader - Application Development" (LinkedIn, **used as default**) vs
  "Application Development Team Leader" (CV).
- EPAM FS/HLS: hyphen/colon punctuation differs between LinkedIn and docx; LinkedIn
  punctuation used.

## 2. Structural conflicts (interview: pick the model)

1. **Verizon, 2011–2017.** LinkedIn: 4 positions (Business Analyst → BA Supervisor →
   Senior Scrum Master → Software Engineering Supervisor). CV 2025-09: one position
   ("Software Engineering Supervisor, Mar 2011 - Aug 2017") with a "previously held
   roles" bullet. **Modeled as 4 positions** (LinkedIn granularity preserves the
   career-timeline story; a projection can collapse later). Confirm.
2. **Scotiabank, 2019–2020.** LinkedIn: 2 positions (Digital Banking Products, then
   Digital Customer Identity). CV: one "Agile Delivery Manager" Aug 2019 – Sep 2020.
   **Modeled as 2 positions.** Confirm.
3. **TransSolutions Systems.** LinkedIn splits the internship under a separate company
   page "Trans Solutions Systems S.A.". **Normalized to one organization**, 3 positions.
4. **IBM team size**: LinkedIn says 11 people / two agile teams; CV says 16 engineers.
   Bullet text avoids the number; position body records both. Which is right (or do
   they measure different scopes/moments)?
5. **EPAM HLS geographies**: LinkedIn says Europe, LATAM, APAC; docx says Europe and
   India. Bullet uses the LinkedIn wording. Confirm.
6. **australworks casing**: "australworks" (LinkedIn, used) vs "AustralWorks" (CV).
   Also "InOrbis" vs "Inorbis" — LinkedIn casing used for both.

## 3. Date assumptions (best-assumption rule applied)

- All sources give **month precision only**. Expanded as startDate = 1st of month,
  endDate = last day of month. Affects every position.
- LinkedIn's own duration math is internally consistent everywhere it was checked
  (Verizon group = 6 yr 6 mo ✓, TransSolutions group = 8 yr 3 mo ✓, EPAM FS = 2 yr 8 mo ✓).
- No date conflicts between S1 and S4 for any shared position. The only soft gap:
  intern ends Mar 2002, Software Programmer starts Dec 2002 (9-month student gap —
  assumed intentional, no fix needed).
- **Project startDates are assumptions** (sources give years at best): Personal
  Investor Data Modernization → 2023-01-01 (CV says "2023, 2024"); Corporate Action
  Workflow Management → 2022-02-01 (= position start); Solar Savings Calculator →
  2017-01-01 (before the FY2018–FY2020 growth it enabled); all other engagement
  projects → their position's start date.
- Overlapping side ventures are real, not errors: TamboSolar (2016–2020) overlaps
  Verizon/IBM/Scotiabank; australworks co-founder (2009–2013) overlaps
  TransSolutions/Verizon.

## 4. Schema gaps found during ingestion (interview: decide)

1. **Certification dates cannot enter the graph.** The shared `context.jsonld` maps no
   issued/expires key (the exporter skips unmapped keys with a warning). Dates are
   parked in cert note bodies. Candidate fix: map `issued`/`expires` →
   `sdo:validFrom`-style predicates + extend `CertificationShape`. Schema-domain change.
2. **Education has no date keys wired either** (start/end year in prose). Same decision.
3. **No `cloud-azure` category.** Azure Data Fundamentals cert exists but its skills
   were mapped to generic ones (SQL, Data Warehousing). Add `cloud-azure` + an Azure
   skill, or accept the loss?
4. **New `ai` category added** (`_schema/Vocabularies/SkillCategories/ai.md`,
   prefLabel "AI Engineering") for the Anthropic/GenAI cluster. This is a
   **schema-domain file — commit it separately from the `_data` files** or the
   pre-commit purity hook will (correctly) reject the commit.
5. **Languages and honors not modeled** (Spanish native, English C1; Verizon Ovation
   Award, IBM Manager's Choice ×2). Parked in `profile.md` body. Model or skip?

## 5. Privacy exclusions (deliberate)

- **The docx names the pharma client (starts with "Astra…")** — excluded everywhere;
  all notes say "a key pharmaceutical client". The repo rule bars employer/client
  names in the public repo.
- **Phone number** (+34 …) appears in the 2025-09 CV — excluded from `profile.md`.
- Deloitte (pen-test vendor) and all employer names were kept: they are on the public
  LinkedIn profile already. Flag if you disagree.

## 6. Skill levels are Claude's assumptions (interview: calibrate)

`rg:level` was assigned conservatively; nothing in the sources states proficiency.
Rough rules used: daily-driver tech of the .NET years → proficient; management-era
delivery skills → expert/proficient; team-oversight tech exposure (AWS services, Java
at EPAM) → aware; self-directed/certified recent stack → working. Review the full
list, especially: `Java` (aware), all `cloud-aws` service skills (aware), `Anthropic
Claude` (working, evidenced by Resume Graph — is "built with Claude Code" acceptable
evidence?), `ETL`/`Power BI`/`CMDB` (proficient).

## 7. Skills seen in sources but NOT ingested

Merged into an ingested skill (dedupe): Ontologies (→ Ontology Engineering), ELT
(→ ETL), Data Build Tool (DBT) + dbt duplicate, Airflow duplicate, Docks (sic → Docker),
GCS + Cloud Storage (→ Google Cloud Storage), T-SQL (→ Microsoft SQL Server),
Generative AI Development (→ Generative AI), Claude Code Subagents (→ Anthropic
Claude), SAFE (→ Scaled Agile Framework), ProjectManagement + Software Project
Management (→ Project Management), Organizational Leadership + Agile Leadership
(→ Team Leadership), IT Service Management + ITIL Certified (→ ITIL), SDLC duplicate.

Skipped as too generic / low-signal / off-model (recoverable from S3 if wanted):
Engineering Data Management, Data Architects, Data Management, vs code, Cloud
Computing (redundant with the `cloud` category), Client Delivery, Agile, Agile
Methodologies, Agile Application Development, Software Development, SDLC, Managed
Services, Requirements Gathering/Analysis/Management, Analysis, Business Process
Design, Business Systems Analysis, Databases, Database Queries, HTML, UML, JavaScript,
Angular, Web Development, Mobile Product Development, Mobile Application Development,
Internet Banking, Credit Scoring, Supplier Risk Management, Corporate Identity,
Photovoltaics, Technology Start-up, Machine Learning Algorithms, Informatica,
Salesforce, English/Business English (languages, see §4.5).

Ingested as **stubs** (exist, no level, no usedSkill link — exempt from the evidence
rule; they surface in gap analysis until evidenced): Snowflake, Looker, Apache
Airflow, Terraform, Master Data Management, Big Data Analytics, Anthropic API,
Model Context Protocol, Design Thinking.

## 8. Certifications not ingested (badge-level; confirm or add)

Salesforce Essential Training, Advanced SQL Part 1 & 2 (LinkedIn courses, 2022),
MySql and SQL Hard (TestDome, 2021), Financial Markets (Yale, 2020), Management 3.0
Foundations (2019), Agile Leadership Core #LeadershipDancefloor (ICF España, 2019 —
listed in the LinkedIn profile header, so arguably worth adding), IBM Blockchain
Essentials (2018), Data Science Foundations L1 (2018), Watson and Cloud Foundations
(2018, expired), IBM Cloud Essentials (2017), IBM Agile Explorer (2018), IBM CLM for
SAFe L1 (2018, expired), ITIL Foundation (2012) and ITIL Intermediate (2014, folded
into ITIL Expert), AWS Cloud Practitioner 2020 issuance (folded into the 2024 renewal).

## 9. Summary/profile variants (interview: pick canonical wording)

Three summaries exist; `profile.md` currently carries a condensation of (a):

- (a) LinkedIn About (2026): "Software & Data Engineering Leader with 10+ years…"
  — leadership-forward, lists GxP/SOX/GDPR.
- (b) CV 2025-09: "Software Engineering Delivery Manager with 10+ years…"
  — delivery-manager-forward.
- (c) docx: "Strategic software engineering delivery manager…" — adds RFP/multi-vendor
  angle and semantic-technology skills block (ontology engineering, metadata
  alignment — the strongest data-eng framing of the three).

Also: `jobTitle` set to "Delivery Manager - Healthcare & Life Sciences"; LinkedIn
headline calls him "Software Engineer". Which identity leads?

## 10. SHACL validation status — PASSED (no worst case needed)

Post-ingestion, `make all` is fully green:

- `make build`: 1137 triples (978 data + 159 schema), **zero exporter warnings**
  (no dangling wiki links, no skipped frontmatter fields).
- `make validate`: **SHACL gate passed — 0 violations**; 132 `sh:Warning` results,
  all the expected advisory "no ESCO mapping yet" warnings (M6 milestone, fires once
  per skill).
- `make test`: 11 passed. Two SHACL tests (`test_roleframing_*`) had hardcoded seed
  position names ("Delivery Manager — EPAM", "Senior Software Engineer — Acme
  Consulting") and were retargeted to real positions ("Delivery Manager Financial
  Services — EPAM", "Senior Scrum Master — Verizon") in `tests/test_validate.py` —
  a mechanism-domain change, commit separately from data.

The prompt's worst-case allowance (ship data that fails SHACL and report it) was
not needed: everything ingested conforms. The evidence rule holds because skills
without corroborating positions/projects were deliberately ingested as unclaimed
stubs (§7) rather than given levels.

## Interview question checklist (for the next session)

1. Resolve the three RoleFraming wordings (§1) and the IBM title variant.
2. Verizon and Scotiabank: keep LinkedIn granularity or collapse per CV? (§2.1–2.2)
3. IBM team size 11 vs 16; EPAM HLS geographies. (§2.4–2.5)
4. Confirm org casing: australworks, InOrbis Analytics, TransSolutions Systems. (§2.6)
5. Approve month→day date expansion and the project startDate assumptions. (§3)
6. Decide cert/education date modeling (schema change) and cloud-azure. (§4)
7. Approve the `ai` category; commit split reminder (schema vs data). (§4.4)
8. Calibrate skill levels; bless or replace the stub list. (§6–7)
9. Any of the skipped certs worth modeling? (§8)
10. Pick the canonical summary + jobTitle. (§9)
11. Languages/honors: model or keep as prose? (§4.5)
