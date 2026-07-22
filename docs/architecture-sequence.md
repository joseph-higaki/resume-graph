# Architecture — sequence diagrams

As-built view of the pipeline (M1–M3) plus the publishing path. The Astro site
(M4/M5) and the Neo4j layers (M7/M8) don't exist yet and are not depicted.
Authored in Mermaid; a Lucidchart port can trace these once the shapes settle.

Three diagrams, one per lifecycle: the diagrams share participants (build.py,
the exports) but each runs from a different trigger with a different contract,
and folding them into one sequence would bury the two properties worth seeing —
the gate ordering in `make all` and the trust boundary in publishing.

## 1. `make all` — build, gate, export

Two gates, in a deliberate order: `build.py` fails on *structural* problems
(dangling wiki links, IRI collisions) before SHACL is even worth running, then
`validate.py` applies the *semantic* shapes (evidence rule, datatypes).
Every export reads `dist/graph.ttl` — never the vault.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as author / CI runner
    participant MK as Makefile
    participant PY as pytest
    participant B as pipeline/build.py
    participant VX as pipeline/vendor/vault_to_rdf.py
    participant V as pipeline/validate.py
    participant SH as pyshacl
    participant RM as exports/resume_model.py
    participant JR as exports/json_resume.py
    participant PD as exports/pdf.py
    participant GH as exports/graph_html.py

    Dev->>MK: make all
    MK->>PY: uv run pytest
    PY-->>MK: green (fixture vault, projection, roundtrip)

    MK->>B: python pipeline/build.py
    activate B
    B->>VX: export_graph() - subprocess over vault/, --out-dir build/layers/
    VX-->>B: schema.ttl + data.ttl (+ warnings on stderr)
    alt strict (default) and a FATAL_WARNING_MARKERS line matched
        B-->>MK: BuildError - exit 1 (dangling link / IRI collision / skipped field)
    else structurally closed
        B->>B: rdflib Graph.parse() both layers - one merged Graph
        B->>B: write_outputs() - dist/graph.ttl + dist/graph.jsonld
    end
    deactivate B

    MK->>V: python pipeline/validate.py
    V->>SH: run() - shacl_validate(dist/graph.ttl, validation/shapes.ttl, allow_warnings=True)
    alt any sh:Violation (e.g. EvidenceRuleShape)
        SH-->>V: conforms = False
        V-->>MK: report + exit 1 - SHACL gate FAILED
    else conforms (sh:Warning tolerated - the advisory ESCO shape)
        SH-->>V: conforms = True
        V-->>MK: SHACL gate passed
    end

    Note over MK,GH: exports consume dist/graph.ttl only - the vault is never read past this line
    MK->>JR: python -m pipeline.exports.json_resume
    JR->>RM: build_model(dist/graph.ttl)
    RM-->>JR: ResumeModel (Basics, Position, Project, Skill, Certification...)
    JR->>JR: to_json_resume() + write_json() - dist/resume.json
    MK->>PD: python -m pipeline.exports.pdf
    PD->>RM: build_model(dist/graph.ttl)
    RM-->>PD: ResumeModel
    PD->>PD: render_html() - WeasyPrint - dist/resume.pdf (+ resume.html)
    MK->>GH: python -m pipeline.exports.graph_html
    GH->>GH: extract(dist/graph.ttl) then render_html() - dist/graph.html
```

- `build.py` runs the vendored exporter as a **subprocess**, not an import — the
  pinned tool keeps its own CLI contract, and patches stay diffable against PIN.
- `ResumeModel` is the shared read model: `json_resume` and `pdf` never touch
  rdflib themselves, so a projected graph swaps in with zero export changes.
- `graph_html` bypasses `ResumeModel` deliberately — it renders the *graph*
  (nodes, edges, categories), not the résumé document shape.

## 2. `make applications` — overlay build + projection

Mechanism lives here, data and artifacts live in the private repo. The overlay
is a throwaway vault: this repo's `context.jsonld` + `_schema` copied under the
private notes so `[[Application]]` resolves. `--no-strict` is correct **here
and nowhere else** — links to public notes are intentionally dangling; the same
`@base` mints byte-identical IRIs and the RDF merge in `project.py` unifies
them.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as author
    participant MK as Makefile
    participant OV as APPS_REPO/build/vault (throwaway overlay)
    participant B as pipeline/build.py (--no-strict)
    participant P as pipeline/project.py
    participant G as rdflib Graph (merged)
    participant EX as exports (pdf / json_resume / graph_html)

    Dev->>MK: make applications [APP=slug]
    MK->>OV: cp context.jsonld + _schema + private vault notes
    MK->>B: build.py --vault overlay --no-strict
    Note right of B: dangling links to public notes are the mechanism working -<br/>same context, same @base, identical IRIs
    B-->>MK: APPS_REPO/build/graph.ttl (overlay triples)

    MK->>P: python -m pipeline.project --export --clean --extra-graph overlay.ttl
    P->>G: load_graph(dist/graph.ttl + extras) - RDF merge, just more triples
    P->>P: resolve_application(slug) or applications() for all
    Note over P: zero Applications (public CI) - clean no-op, exit 0

    loop each rg:Application
        P->>G: project() - copy the merged graph, then stage in code order
        P->>G: _apply_role_framings() - audience roleName override (ADR 0001)
        P->>G: _select_bullets() - drop bullets outside declared audiences
        P->>G: _apply_excludes() - _purge() targets as subject AND object
        P->>G: _prune_unevidenced_claims() - purge, or demote demanded skills to gaps
        P->>G: _prune_orphan_organizations() - after all removals have landed
        P->>G: _substitute_summary() + _substitute_job_title() (rg:targetRole)
        P->>G: _strip_framings() - scaffolding never ships
        P->>P: dir_for() - rg:publicId if set, else readable slug
        P->>P: serialize - out-dir/<dir>/graph.ttl
        P->>EX: _run_exports() - write_pdf, write_json, graph_html render
        EX-->>P: resume.pdf / resume.json / graph.html (copied to index.html)
        P->>P: _stamp_private() - noindex,nofollow + no-referrer metas
    end
```

- Stage order is load-bearing at three points, all annotated in `project.py`:
  claim pruning must follow excludes, org pruning must follow every removal,
  framings are stripped last because roleName substitution still reads them.
- The exports are unchanged and unaware — they take a graph path, so a
  projection is just a different `graph.ttl` pointed at the same code.
- `_stamp_private` is unconditional: any projected page may later be copied to
  a public host, so it carries its own refusal from birth.

## 3. Publishing — `make publish` → `make deploy` → CI → Pages

The trust boundary: nothing employer-shaped ever enters this repo's git
history. Publishing is a deliberate git commit in the *private* repo; the
public CI checks that tree out at deploy time and it exists only inside the
ephemeral Pages artifact.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as author
    box Local machine
        participant MK as Makefile
    end
    box resume-applications (private repo)
        participant PRIV as published/ tree on GitHub
    end
    box resume-graph CI (GitHub Actions)
        participant BV as job build-validate
        participant DP as job deploy-pages
    end
    participant PAGES as GitHub Pages

    Dev->>MK: make publish
    MK->>MK: gate - only dirs named ^[0-9a-f]{32}$ (rg:publicId) stage
    Note right of MK: no publicId = structurally unpublishable -<br/>an employer-named folder can never reach a public host
    MK->>Dev: staged in APPS_REPO/published/<id>/ - commit there to deploy
    Dev->>PRIV: git commit + push published/ (deliberate, reviewable, un-publish = git rm)

    Dev->>MK: make deploy
    MK->>MK: guards - published/ clean AND branch not ahead of origin
    MK->>BV: gh api repos/.../dispatches event_type=applications-updated
    Note over BV: same workflow also fires on push to main and workflow_dispatch -<br/>every trigger rebuilds pages/ from scratch

    BV->>BV: checkout + uv sync --locked
    BV->>BV: make all (diagram 1 - test, build, SHACL gate, exports)
    BV->>BV: upload-artifact graph-and-exports (per-run inspection)
    opt APPS_TOKEN set (never on forks or PRs)
        BV->>PRIV: actions/checkout resume-applications - .apps (read-only PAT)
        PRIV-->>BV: published/<id>/ trees
    end
    BV->>BV: make pages APPS_REPO=.apps - graph.html doubles as index.html,<br/>published/ folds into pages/application/<id>/
    BV->>DP: upload-pages-artifact - needs build-validate, main only
    DP->>PAGES: actions/deploy-pages@v4 - replaces the whole site
    PAGES-->>Dev: live at /resume-graph/ (+ unlisted /application/<id>/)
    MK-->>Dev: verifies a run actually started, prints live URLs
```

- The applications checkout runs on **every** deploy, not just dispatches —
  Pages replaces the whole site each time, so a conditional fetch would let a
  routine push to main silently delete the application pages.
- `make deploy`'s guards exist because CI serves the *pushed* `published/`
  tree: a local publish never committed deploys nothing, silently — the one
  failure this mechanism invites.
- `make pages` is the single definition of the deployable tree; CI runs the
  same target as `make serve` locally, so preview and deploy cannot drift.
