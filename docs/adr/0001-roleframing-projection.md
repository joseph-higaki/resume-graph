# ADR 0001 — RoleFraming: per-audience `roleName` override

**Status:** Accepted. Schema + shapes + SHACL tests **implemented** (`1d39525`
schema, `3f8dd6f` seed data). The `project.py` substitution in §4 is **pending** —
it lands with M3-core, because `pipeline/project.py` does not exist yet.

**Date:** 2026-07-17
**Context prompt:** "resume customization by application" (`next-prompts.md`).

---

## 1. Context

The résumé must let its author consciously reword a Position's role for different
targets — e.g. **"Delivery Manager"** (default / coordinator-facing) vs
**"Engineering Delivery Lead"** (engineer-facing) — without:

- inventing a title never held (**honesty**),
- leaking any employer/application name into this **public** repo, or
- requiring **blank nodes** (the vendored exporter has none).

The reusable dimension already in the model is `rg:audience`
(`data-eng | ai-eng | delivery | general`): Bullets are audience-tagged and an
Application declares the audiences it wants. RoleFraming extends that *same*
dimension to the role label, rather than inventing a new axis.

Alternatives rejected:

- **Inline override on the Application note** (`rg:relabelPosition [[…]]; rg:relabelTo "…"`):
  handles only one position per application, and can live only in the private repo.
  Doesn't compose, and can't be a reusable engineer-vs-coordinator framing.
- **A generic `rg:Framing(framingOf, property, value, audience)`**: premature.
  Two concrete scalar overrides exist (summary substitution + roleName) and they
  differ mechanically (summary is app-level & single; framing is per-position &
  per-audience). Generalize only when a third appears (YAGNI).

## 2. Decision — model (implemented)

A `RoleFraming` is a first-class note carrying an audience-specific alternative
`sdo:roleName` for a Position.

| Field | Predicate | Rule |
|-------|-----------|------|
| `type` | `rdf:type` → `rg:RoleFraming` | — |
| `framingOf` | `rg:framingOf` (object) | exactly one `rg:Position` |
| `audience` | `rg:audience` (string) | exactly one of `data-eng \| ai-eng \| delivery` — **never `general`** (that IS the default) |
| `roleName` | `sdo:roleName` (string) | exactly one; the override wording |

Reuse over minting: the override value *is* `sdo:roleName`; the dimension *is*
`rg:audience`. Only `rg:RoleFraming` (class) and `rg:framingOf` (property) are new.

**Files (in the vault, self-documenting):**
- `vault/_schema/Ontologies/rg/Classes/RoleFraming.md` — class + rationale in body.
- `vault/_schema/Ontologies/rg/Properties/framingOf.md` — object property.
- `vault/_schema/Ontologies/rg/Properties/audience.md` — domain extended.
- `vault/_schema/Ontologies/rg/context.jsonld` — `framingOf` mapped `@type:@id`.
- `validation/shapes.ttl` — `RoleFramingShape` + `RoleFramingUniqueShape`.

**SHACL:** `RoleFramingShape` enforces the table above; `sh:in` deliberately
**omits `general`**, encoding "general == default" at the gate.
`RoleFramingUniqueShape` is an `sh:sparql` constraint forbidding two framings on
the same `(Position, audience)` — a **cross-node** cardinality (two distinct nodes
sharing a key), which a property shape can't see, so it needs SPARQL (same reason
as the evidence rule). It holds over the **merged** public+private graph, so a
private overlay framing can't silently collide with a public one.

## 3. Placement (public vs private)

- **Reusable, audience-keyed framings** (no employer) → `vault/_data/framings/`
  in THIS repo. They are résumé content → **data** domain (commit-pure with
  content). The M4/M5 site may expose an "as engineer / as delivery lead" toggle
  from them, entirely from public data.
- **Application-specific one-offs** → the **private** overlay repo, authored
  identically, merged via `--extra-graph`. Same class, gated by the shapes
  shipped here.

## 4. Implementation spec — `pipeline/project.py` (PENDING)

Framing substitution is an **independent stage** of the projection
(order-independent of the bullet / `rg:emphasizes` / `rg:excludes` ops). It runs
against the merged rdflib `Graph` for a resolved target Application IRI
(`app_iri`), **before** the final scaffolding cleanup. Prefixes `rg:`/`sdo:` are
bound as elsewhere in the pipeline.

### Step A — conflict pre-check (validate before mutating)

```python
CONFLICTS = """
SELECT ?pos (COUNT(DISTINCT ?framed) AS ?n) WHERE {
  ?f a rg:RoleFraming ; rg:framingOf ?pos ; rg:audience ?a ; sdo:roleName ?framed .
  ?app rg:audience ?a .
} GROUP BY ?pos HAVING (COUNT(DISTINCT ?framed) > 1)
"""
if list(graph.query(CONFLICTS, initBindings={"app": app_iri})):
    raise ProjectionError(f"{app_iri} matches conflicting RoleFramings for a position")
```

### Step B — substitute (SPARQL UPDATE)

```python
SUBSTITUTE = """
DELETE { ?pos sdo:roleName ?default }
INSERT { ?pos sdo:roleName ?framed }
WHERE {
  ?pos a rg:Position ; sdo:roleName ?default .
  ?f a rg:RoleFraming ; rg:framingOf ?pos ; rg:audience ?a ; sdo:roleName ?framed .
  ?app rg:audience ?a .
}
"""
graph.update(SUBSTITUTE, initBindings={"app": app_iri})
```

### Step C — strip scaffolding (framings never appear in the CV)

```python
graph.update("DELETE { ?f ?p ?o } WHERE { ?f a rg:RoleFraming ; ?p ?o . }")
```

Nothing points *to* a framing (`framingOf` runs framing→position), so deleting its
outgoing triples removes it entirely.

### Why these choices

- **`DELETE`/`INSERT` over `CONSTRUCT`.** CONSTRUCT builds a fresh graph, forcing
  you to re-emit every kept triple and then reconcile a duplicate `roleName`
  (default *and* framed). DELETE/INSERT is surgical: it touches only the
  `roleName` of framed positions; unframed positions and all other triples are
  untouched. Right tool for "override one value in place."
- **`initBindings`, not string-formatting the IRI.** Parametrizing `?app` keeps
  the application IRI out of the query text — no IRI injection; rdflib binds it
  safely. Same discipline as SQL parameters.
- **Check-then-mutate, fail loud.** Step A runs before Step B, so projection
  either substitutes cleanly or names the offending position — never silently
  picks one of two wordings.
- **Why conflicts are rare (so fail-fast is correct, not lazy).** An application
  declares audiences for *bullet selection* — a data-eng app declares
  `["data-eng","general"]`. Framings exist only for specific audiences, so only
  `data-eng` framings match → exactly one. A conflict needs an app declaring *two
  specific* audiences (`["data-eng","ai-eng"]`) — applying as two things at once,
  almost always an authoring mistake, which is exactly what should fail.
- **Escalation** if two-specific-audience apps ever become legitimate: add an
  ordered `rg:audiencePriority` on the Application and resolve by highest priority.
  Do not build it now.

## 5. Consequences

- **Zero-application contract preserved.** With no Application, Step B's WHERE
  never binds `?app` → roleNames unchanged; framings sit valid in the base graph
  and are stripped only during a projection. Public CI stays green.
- The public `dist/graph.ttl` **does** contain RoleFraming triples (valid,
  SHACL-checked). The site may ignore or use them.
- New model surface: one class, one property, two shapes — kept distinct from
  summary-substitution rather than unified (see §1 rejected alternatives).

## 6. Remaining work

- [ ] `pipeline/project.py` Steps A–C (this spec), inside M3-core.
- [ ] Projection tests (distinct from the SHACL tests already shipped):
  - app declaring `ai-eng` → EPAM position `roleName` becomes the framed value;
    other positions keep their default.
  - app with no matching framing → default preserved.
  - two conflicting specific-audience framings for one position → `ProjectionError`.
  - projected graph contains **zero** `rg:RoleFraming` triples (scaffolding stripped).
  - zero-application projection runs clean, `roleName`s unchanged.

## 7. References

- Schema commit `1d39525`; seed-data commit `3f8dd6f`.
- SHACL tests: `tests/test_validate.py::test_roleframing_*`.
- Seed example: `vault/_data/framings/dm-epam-ai-eng.md`.
- Brief: `.claude/CLAUDE.md` → "Application projection (`pipeline/project.py`)".
