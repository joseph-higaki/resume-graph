---
type: owl:ObjectProperty
label: evidenced by
comment: "Links a claimed skill to the Project, Position, or Bullet that proves it. Every claimed skill needs at least one — the SHACL gate fails otherwise."
domainIncludes: [ "[[Skill]]" ]
rangeIncludes: [ "[[Project]]", "[[Position]]", "[[Bullet]]" ]
---
# evidencedBy

Inverse-ish of [[usedSkill]]: `usedSkill` is authored on the work, `evidencedBy`
on the skill. Both are kept explicit (no inference at export time); SHACL checks
they stay consistent via the evidence rule.

[[Bullet]] joined the range in the 2026-07-20 work-project migration. Pointing at
a Bullet rather than its owning Position is the finer-grained claim — it names the
one accomplishment that proves the skill, and it makes skill → bullet → position a
real multi-hop path instead of a single flat edge.
