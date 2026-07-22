---
type: owl:Class
label: Project
comment: "A self-directed piece of work — a thing built outside a client engagement — that evidences skills."
subClassOf: [ sdo:CreativeWork ]
---
# Project

Projects are first-class evidence carriers: `rg:evidencedBy` on a skill points
here (or at a Position, or at a [[Bullet]]). Every Project asserts
`sdo:creator` → the [[Person]] — the edge that anchors self-directed work to
the hub, the way `rg:heldBy` anchors a Position.

**Self-directed work only** (decision 2026-07-20). Client engagements used to be
modeled as Projects delivered during a Position (`rg:deliveredDuring`, removed
2026-07-23 with the scope change); they are now [[Bullet]] notes on the Position
itself. The engagement was never an artifact anyone can look at — it was a set of
accomplishments inside a role — and modeling it as one double-counted the work in
the graph: the same months rendered as both a project node and a role. Bullets
also carry `rg:audience`, so the projection can select them; a Project could
only be included or excluded wholesale.

Authoring test: if the work has no public URL and no existence outside an employer's
account, it is a Bullet.
