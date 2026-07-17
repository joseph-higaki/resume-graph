# resume-graph

A résumé authored as a knowledge graph. The source of truth is a
[Vault-LD](https://github.com/The-Knowledge-Graph-Guys/vault-ld) vault — Markdown
notes with YAML-LD frontmatter — exported to RDF, validated with SHACL, and
published as an interactive graph site with in-browser SPARQL, plus PDF / JSON
Resume exports and per-application tailored variants.

## Repository domains

The repo is partitioned into three domains that change at different cadences.
Keeping them separate is what lets a résumé-wording edit read as a *content*
change in the history, not an architectural one. Identity in the graph is
minted from note **names**, not folders (the exporter emits no location data),
so this layout is organizational — moving a note changes no triples.

| Domain | Location | What it is |
|--------|----------|------------|
| **data** | `vault/_data/` | The résumé content — positions, organizations, projects, skills, bullets, education, certs, profile. Changes often. |
| **schema** | `vault/_schema/`, `vault/context.jsonld`, `validation/` | The model: the `rg` ontology (classes + properties as notes), the SKOS skill-category vocabulary, the shared JSON-LD context, and the SHACL validation contract (`validation/shapes.ttl`). Changes rarely; architecturally significant. |
| **mechanism** | `pipeline/`, `site/`, `queries/`, `api/`, `.github/`, `Makefile` | The machine that turns the vault into artifacts — exporter wrapper, validator, projection, site, CI. |

Everything else (`docs/`, this README, `.claude/`, configs) is neutral.

### Commit hygiene

A pre-commit hook (`.githooks/pre-commit`) keeps **data commits pure**: a commit
that touches `vault/_data/` may not also touch schema or mechanism. Neutral files
may ride with either side. Activate once per clone:

```sh
make hooks        # git config core.hooksPath .githooks
```

Bypass a deliberate cross-domain commit (e.g. a structural migration) with
`git commit --no-verify`.

## Build

```sh
make all          # test → build → validate
```

_This README is a seed; the full architecture case study lands in M6._
