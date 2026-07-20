---
type: owl:DatatypeProperty
label: issued
comment: "Month a Certification or Education credential was granted. xsd:gYearMonth — the source data only has month precision, not day."
domainIncludes: [ "[[Certification]]", "[[Education]]" ]
---
# issued

Required on Certification, optional on Education. A certificate prints an issue
month; a degree comes from LinkedIn's education section, which carries year ranges
only — so Education is dated by `sdo:startDate`/`sdo:endDate` and uses `issued`
only when a real conferral month is known.
