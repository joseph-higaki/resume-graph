---
type: owl:Ontology
label: rg — resume graph vocabulary
comment: "Domain vocabulary for the resume knowledge graph: skills with evidence, positions, projects, bullets, and application projections."
---
# rg — resume graph vocabulary

Everything the resume graph needs that schema.org and SKOS don't already say.
Classes anchor to schema.org via `subClassOf` so external consumers get familiar
types; the rg: layer carries the resume-specific semantics (the evidence rule,
audience-tagged bullets, application projections).

Design decisions:

- **Bullets are notes, not body text.** Vault-LD never exports the body (SPEC §5.3)
  and the exporter has no blank-node support, so an audience-tagged bullet can only
  reach the graph as its own typed note (`rg:Bullet` in `vault/bullets/`).
- **`domainIncludes`/`rangeIncludes`, not `rdfs:domain`/`range`.** Multiple
  `rdfs:domain` values mean the *intersection* of the classes (a subject would be
  inferred to be all of them at once); schema.org's `domainIncludes` documents a
  union without triggering that entailment.
