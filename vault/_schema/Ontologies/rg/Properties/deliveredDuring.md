---
type: owl:ObjectProperty
label: delivered during
comment: "Links a Project to the Position it was delivered under (absent for self-directed projects)."
domainIncludes: [ "[[Project]]" ]
rangeIncludes: [ "[[Position]]" ]
---
# deliveredDuring

Zero instances since the 2026-07-20 migration: client engagements became Bullets on
their Position, so `rg:Project` now means self-directed work only and nothing is
"delivered during" a role. Kept in the model because the relation is still the right
one the day a personal project is genuinely built inside a paid engagement — a
Bullet's `bulletOf` says the opposite thing (the statement belongs to the role),
not a substitute.
