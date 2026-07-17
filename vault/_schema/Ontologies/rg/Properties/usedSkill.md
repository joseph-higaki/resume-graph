---
type: owl:ObjectProperty
label: used skill
comment: "A Position or Project declares the skills exercised in it. Being referenced here makes a skill *claimed* (evidence rule applies)."
domainIncludes: [ "[[Position]]", "[[Project]]" ]
rangeIncludes: [ "[[Skill]]" ]
---
# usedSkill

Inverse-ish of [[evidencedBy]]: `usedSkill` is authored on the work, `evidencedBy`
on the skill. Both are kept explicit (no inference at export time); SHACL checks
they stay consistent via the evidence rule.
