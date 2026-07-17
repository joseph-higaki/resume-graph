---
type: owl:Class
label: Application
comment: "A job application: target role, demanded skills, and projection directives (emphasizes / excludes / audiences / tailored summary)."
---
# Application

Application *instances* live only in the private `resume-applications` overlay
vault — nothing in this public repo may reference a target employer. The class,
its properties, and the SHACL shape ship here so the projection mechanism
(`pipeline/project.py`, M3) behaves identically with or without an extra graph.
