---
type: owl:Class
label: Bullet
comment: "One resume bullet: a text statement attached to a Position or Project, tagged with an audience for projection."
subClassOf: [ sdo:Statement ]
---
# Bullet

M1 decision — bullets are notes, not body prose. Vault-LD exports frontmatter
only (SPEC §5.3), so body bullets can never reach the graph, and the exporter
has no blank-node support for inline `{text, audience}` objects. A bullet note
costs one small file and buys: SHACL validation, audience selection in the M3
projection (`rg:audience` matching an Application's declared audiences), and a
clickable node in the graph UI.

Fields: `text` (sdo:text), `audience` (rg:audience — one of data-eng | ai-eng |
delivery | general), `bulletOf` (owning Position/Project), `order` (render order).

2026-07-20 — Bullets became the carrier for client engagements (see [[Project]])
and a valid [[evidencedBy]] target. A skill evidenced by a Bullet names the single
accomplishment that proves it, and the path skill → bullet → position recovers the
employer and dates that the Bullet itself deliberately does not carry: a Bullet has
no dates of its own, so a claim can never contradict the role it sits in.
