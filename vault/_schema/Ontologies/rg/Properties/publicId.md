---
type: owl:DatatypeProperty
label: publicId
comment: "Opaque URL segment an Application is published under. Unguessable by design: the published bytes name the employer, so the GUID is what keeps the page unlisted. Absent = projected to its slug, local-only."
domainIncludes: [ "[[Application]]" ]
---
# publicId

32 lowercase hex characters, minted once per application and never regenerated —
the URL is handed to a person, so a rebuild must not move it. Rotating the value
retires the old URL; deleting it takes the application off the site entirely.
