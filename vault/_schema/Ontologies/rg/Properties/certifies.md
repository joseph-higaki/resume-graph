---
type: owl:ObjectProperty
label: certifies
comment: "Links a Certification or Education credential to the skills it attests — a second evidence channel alongside evidencedBy."
domainIncludes: [ "[[Certification]]", "[[Education]]" ]
rangeIncludes: [ "[[Skill]]" ]
---
# certifies

[[Education]] joined the domain 2026-07-20. The decision-3 unlock ("certifies
counts as evidence") always meant degrees too — a master's attests coursework the
holder never shipped in a paid role — but the property was modeled for
Certification alone, so an Education could not carry the link its skills needed.
The evidence rule's SPARQL never cared (`?cert rg:certifies $this` leaves the
subject unbound); only the domain did.

Required on Certification (a credential that attests nothing is a data error),
optional on Education — most degrees here are context, not skill attestation, and
listing every topic a syllabus touched is the keyword-stuffing the gate exists to
prevent.
