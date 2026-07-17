---
type: owl:Class
label: Skill
comment: "A skill claim. Claimed skills (rg:level present, or referenced via rg:usedSkill) must carry rg:evidencedBy — enforced by SHACL."
subClassOf: [ skos:Concept, sdo:DefinedTerm ]
---
# Skill

One note per skill in `vault/skills/`. Skills sit in the SKOS category tree via
`broader` → a `SkillCategories` concept, which is what makes the cloud cluster
render as a visual unit on the site.

The evidence rule is the anti-keyword-stuffing guarantee: a skill without a
Project or Position behind it cannot claim a level and cannot be published.
Stub skills that exist only because an Application `rg:demands` them are exempt
— their missing evidence is exactly what gap analysis detects.
