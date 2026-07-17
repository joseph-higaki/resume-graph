# resume-graph — Project Brief for Claude Code (PUBLIC repo)

## What this is
A resume-as-knowledge-graph portfolio project. The resume is authored as a **Vault-LD vault**: Markdown notes with YAML-LD frontmatter resolved through a shared `@context` (spec: https://github.com/The-Knowledge-Graph-Guys/vault-ld). A Python pipeline exports the vault to RDF (Turtle + JSON-LD), validates with SHACL, and publishes:
1. A static website (GitHub Pages) with an interactive graph render and in-browser SPARQL.
2. A PDF resume and a JSON Resume export.
3. A **projection mechanism** that builds tailored CV variants for specific job applications by running SPARQL CONSTRUCT over the graph. Application data itself lives in a separate PRIVATE repo (`resume-applications`); this repo ships only the mechanism.

LinkedIn is a downstream copy-paste target, never a source. The project is itself the portfolio artifact: it must demonstrate data engineering practice (semantic modeling, validation gates, CI/CD, graph federation) with an AWS-leaning cloud story.

## Owner context (use for seed data)
- Delivery Manager at EPAM, Barcelona. Ex-C# developer; Python in self-directed projects; targeting data/AI engineering IC roles (e.g., AI engineer in pharma tech).
- Cloud skills: AWS (primary), GCP (secondary). Certs may come later — model them as first-class from day one.

## Architecture: two repos
- **resume-graph (this repo, public)**: vault (the master truth), ontology, pipeline, site, canned queries, CI + Pages deploy.
- **resume-applications (private)**: an overlay vault containing `Application` notes and tailored prose. Its CI checks out this repo, merges the two graphs (RDF merge = just more triples), and runs this repo's projection to produce per-application PDFs as private workflow artifacts. Nothing in THIS repo may reference a target employer.
- Contract between repos: this pipeline must accept `--extra-graph <path.ttl>` and `--application <iri-or-slug>` and behave identically whether the extra graph is present or not.

## Non-negotiable requirements
1. **Source of truth is the vault.** Never hand-edit generated Turtle/JSON-LD. `dist/` is disposable.
2. **Vendor Vault-LD tooling**: copy `vault_to_rdf.py` from the spec repo at a pinned commit into `pipeline/vendor/` (Apache-2.0 — keep license header, record commit hash in `pipeline/vendor/PIN`). We own and may patch it; do not pip-install anything for this.
3. **SHACL is the only validation gate** (no pydantic layer). Shapes must be strict: required properties, datatypes, IRI patterns, and the evidence rule below. pySHACL failure = CI failure, with human-readable violation output.
4. **Evidence rule**: every **claimed** skill must be `rg:evidencedBy` at least one Project or Position. Claimed = has `rg:level` OR is linked from any Position/Project via `usedSkill`. Skills that exist only because an Application `rg:demands` them (stub notes, no level, no usage links) are exempt — their lack of evidence is exactly what gap analysis detects. This is the structural anti-keyword-stuffing guarantee — a core talking point.
5. **Cloud skills surface on their own**: graph UI clusters skills by category so the AWS/GCP cluster is visually distinct with no user action, AND a one-tap canned query lists cloud skills with their evidence.
6. **In-browser SPARQL** via Comunica (or oxigraph-wasm) against the published JSON-LD. No server.
7. **Everything derived from the graph**: exports read `dist/graph.ttl`, never the vault directly. One `make all` builds everything.
8. **Tests**: pytest — export correctness on a fixture vault, wiki-link/IRI resolution, dangling-link detection, projection behavior (with and without extra graph), roundtrip sanity.

## Repo layout
```
resume-graph/
├── .claude/CLAUDE.md
├── Makefile                       # build | validate | export | site | project | all
├── vault/                         # SOURCE OF TRUTH (Vault-LD). Identity is name-based; folders are organizational.
│   ├── context.jsonld             # root @context: cross-cutting core + composes the two schema contexts
│   ├── _schema/                   # the model — changes rarely, architecturally significant
│   │   ├── Ontologies/rg/         # rg: classes/properties as notes (Ontologies/Vocabularies names fixed by the exporter, SPEC §3)
│   │   └── Vocabularies/SkillCategories/  # SKOS concept tree: cloud → cloud-aws / cloud-gcp, data-eng, devops, delivery…
│   └── _data/                     # the résumé — changes often (commit-pure: never mixed with schema/mechanism)
│       ├── positions/             # one note per role
│       ├── organizations/         # employers/institutions (wiki-link targets for positions & education)
│       ├── projects/              # incl. this project itself (dogfood)
│       ├── skills/                # one note per skill
│       ├── bullets/               # one note per resume bullet (rg:Bullet — see authoring model)
│       ├── education/
│       ├── certs/
│       └── profile.md             # the schema:Person hub
├── validation/shapes.ttl          # SHACL (authored directly as Turtle; not vault content)
├── pipeline/
│   ├── vendor/vault_to_rdf.py     # pinned Vault-LD reference exporter (+ PIN file)
│   ├── build.py                   # thin wrapper: vault → dist/graph.{ttl,jsonld} (framed)
│   ├── validate.py                # pySHACL gate
│   ├── project.py                 # SPARQL CONSTRUCT projection for applications (see below)
│   ├── load_neo4j.py              # M7: RDF → native LPG remodel → Neo4j (Aura or local)
│   ├── enrich_gds.py              # M7: runs GDS (PageRank, Louvain) against local Docker Neo4j, writes scores back
│   └── exports/
│       ├── json_resume.py         # graph → dist/resume.json (jsonresume.org schema)
│       └── pdf.py                 # graph → HTML template → PDF (WeasyPrint)
├── queries/                       # canned queries shipped to the site
│   ├── sparql/                    # cloud-skills.rq, skills-by-evidence.rq, career-timeline.rq
│   ├── cypher/                    # M7: Cypher twins of each .rq + assertions/ (CI validation queries)
│   └── README.md                  # side-by-side SPARQL↔Cypher comparison (also a site page)
├── api/                           # M8: AWS Lambda handlers (whitelisted read-only Cypher) + IaC
├── site/                          # Astro + TS + Sigma.js + Comunica
├── tests/  (incl. tests/fixture-vault/)
├── .github/workflows/ci.yml
└── dist/                          # gitignored
```

## Authoring model (Vault-LD)
Frontmatter = triples; body = prose (narrative, learnings, impact stories — free to edit without touching the graph). Wiki-links are edges, resolved to IRIs via `context.jsonld`. Mint IRIs under `https://<domain>/id/…`.

Example `vault/_data/positions/Delivery Manager — EPAM.md`:
```markdown
---
type: "[[Position]]"
roleName: Delivery Manager
organization: "[[EPAM]]"
heldBy: "[[profile]]"
startDate: 2021-06-01
usedSkill: ["[[Stakeholder Management]]", "[[AWS S3]]"]
---
# Delivery Manager — EPAM
Led delivery for a data platform… # TODO(owner)

## Learnings
…
```
**Bullet convention (decided in M1):** one small note per bullet in `vault/_data/bullets/`, typed `[[Bullet]]` with `text`, `audience` (data-eng | ai-eng | delivery | general), `bulletOf` → owning Position/Project, and `order`. Rationale: Vault-LD never exports the body (SPEC §5.3) and the exporter has no blank-node support, so frontmatter notes are the only way audience-tagged bullets reach the graph. Applications later select audiences.

Example `vault/_data/skills/AWS S3.md`:
```markdown
---
type: "[[Skill]]"
prefLabel: AWS S3
broader: "[[cloud-aws]]"
level: working                    # aware | working | proficient | expert
evidencedBy: ["[[Resume Graph]]"]
# escoMatch: <ESCO IRI>          # add when mapped (M6); a SHACL sh:Warning flags the absence
---
# AWS S3
Static hosting + artifact storage for CI pipelines.
```

## Semantic model
- `schema:Person` (hub), `schema:EmployeeRole` + `schema:Organization` (positions), `rg:Project ⊑ schema:CreativeWork`, skills as `skos:Concept` + `schema:DefinedTerm` with `skos:broader` category tree, `schema:EducationalOccupationalCredential` for certs (`rg:certifies` → skills).
- `rg:` vocab defined as ontology notes in the vault (dogfooding the spec's schema layer): `rg:level`, `rg:evidencedBy`, `rg:deliveredDuring`, `rg:audience`, `rg:Application`, `rg:emphasizes`, `rg:excludes`, `rg:demands`, `rg:targetRole`, `rg:status`.
- ESCO: `skos:exactMatch`/`closeMatch` to `http://data.europa.eu/esco/skill/…` IRIs where they exist.

## Application projection (`pipeline/project.py`)
Input: full graph (+ optional `--extra-graph` merged in) and an Application IRI. Behavior:
- SPARQL CONSTRUCT a subgraph: drop anything in `rg:excludes`, order/flag `rg:emphasizes` first, select bullets whose `rg:audience` matches the application's declared audiences, substitute the application's tailored summary for the default profile summary.
- Output `dist/applications/<slug>/graph.ttl` and run both exports against it.
- Must run cleanly with zero applications present (public CI never has any).
- Per-audience `roleName` override (RoleFraming): schema shipped; substitution algorithm + reasoning in `docs/adr/0001-roleframing-projection.md`.

## Site direction
- Astro static build; graph page hydrates Sigma.js (or D3 force) from `graph.jsonld`. Nodes colored by type; skills cluster around category nodes — the cloud cluster must read at a glance. Click node → side panel with details, prose excerpt, evidence links.
- SPARQL panel: CodeMirror preloaded with canned queries as tappable chips; Comunica executes client-side; results table.
- Also embed the JSON-LD in `<head>` as schema.org structured data (SEO win; note it in README).
- Design: do NOT ship the default AI look (cream + serif + terracotta, or near-black + acid green). Direction: graph-workbench — dark slate base, node-type accent palette that doubles as the graph legend, monospace-forward pairing (IBM Plex Mono for data/labels + a grotesk for headings). The live graph IS the hero — the page opens on it, not on a headline. Responsive, keyboard-focusable, respects prefers-reduced-motion.

## CI (`.github/workflows/ci.yml`)
On push to main: uv setup → pytest → build → SHACL validate → exports → Astro build → deploy Pages. Upload `resume.pdf` + `resume.json` as artifacts. README badge. (Private repo has its own workflow; not this repo's concern beyond the `--extra-graph/--application` contract.)

## Milestones
1. **M1 — Vault + export core**: vault scaffold with `context.jsonld`, rg: ontology notes, seed data (profile, 2 positions, 3 projects incl. this one, ~12 skills across cloud-aws/cloud-gcp/data-eng/delivery, category tree), vendored exporter wired via `build.py`, strict `shapes.ttl`, `validate.py`, tests, Makefile. Done = `make all` green.
2. **M2 — Exports**: JSON Resume + PDF from the graph.
3. **M3 — Projection**: `project.py` + `--extra-graph`/`--application` contract + fixture tests (this unblocks the private repo).
4. **M4 — Site**: graph render + node panel.
5. **M5 — SPARQL panel** + canned queries + Pages deploy.
6. **M6 — Polish**: ESCO mappings, README as case study (architecture diagram, decision log, two-repo diagram).
7. **M7 — Neo4j serving projection** (depends only on M1):
   - `load_neo4j.py`: deliberate native LPG remodel, NOT an n10s dump. IRIs kept as `iri` property for lineage; `schema:EmployeeRole` intermediates collapse into qualified relationships `(:Person)-[:HELD_ROLE {start,end,title}]->(:Org)`; `skos:broader` tree → `[:IN_CATEGORY]` / `[:CHILD_OF]`; evidence → `(:Project|:Position)-[:EVIDENCES]->(:Skill)`; demands → `(:Application)-[:DEMANDS]->(:Skill)`. Idempotent (MERGE on `iri`).
   - Also run an n10s import once and document the comparison (native model vs RDF-shaped model) in `queries/README.md` — the "why native" paragraph is a deliverable.
   - `queries/cypher/`: twins of every canned SPARQL query, plus the paradigm-exclusive ones: shortest-path career narrative, skill-gap distance (see private repo), temporal skill lineage.
   - **Validation as Cypher assertions in CI** (property-existence constraints are Enterprise-only): `queries/cypher/assertions/*.cypher` must all return zero rows — claimed-skill-without-evidence, dangling DEMANDS, HELD_ROLE without dates. Run against a Dockerized Neo4j in CI.
   - **GDS runs offline, not on Aura** (Aura Free has no GDS): `enrich_gds.py` spins Docker `neo4j` + GDS plugin in CI, computes PageRank (claim-defensibility score) and Louvain communities (emergent skill clusters vs curated SKOS categories), writes them back as node properties, THEN pushes the enriched graph to AuraDB Free. Compute-offline/serve-precomputed is the pattern; name it in the README.
   - Aura keep-alive: scheduled Actions cron running one trivial query daily; documented as a free-tier failure-mode mitigation.
8. **M8 — Public Neo4j explorer via AWS read layer** (depends on M7):
   - Lambda + API Gateway + Secrets Manager (credentials never client-side). Endpoints expose ONLY whitelisted parameterized Cypher: each canned query + `neighbors(nodeId)` for Bloom-style expand. No free-form Cypher from the internet. Basic throttling via API Gateway.
   - Site page using NVL (Neo4j Visualization Library) hydrated from the API; PageRank sizes nodes, Louvain colors optional toggle vs curated categories. Graceful degradation: if the API/Aura is down, the page says so and links the static RDF graph — the static page remains the landing experience.
   - IaC in `api/` (SAM or Terraform — propose one in M8 planning). Dogfood: on ship, add `AWS Lambda`, `API Gateway`, `Secrets Manager` skill notes evidenced by `[[Resume Graph]]`.

## Working agreements
- Dependencies capped at: rdflib, pyshacl, pyyaml, weasyprint, pytest, neo4j (Python); astro, sigma, @comunica/query-sparql, @neo4j-nvl/base (site). Ask before adding others.
- Patches to the vendored exporter go in as clearly-marked diffs against the PIN commit.
- Seed data uses realistic placeholders marked `# TODO(owner)`.
- No employer/application names anywhere in this repo — that data is private-repo-only.
- Three domains (see README): **data** (`vault/_data/`), **schema** (`vault/_schema/`, `vault/context.jsonld`, `validation/`), **mechanism** (everything else). A `.githooks/pre-commit` keeps data commits pure — never stage résumé content alongside schema/mechanism in one commit.