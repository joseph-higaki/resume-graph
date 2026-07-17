---
type: owl:Class
label: RoleFraming
comment: "An audience-specific alternative wording for a Position's roleName. Projection substitutes it for the Position's default roleName when an Application declares the matching audience; with no framing, the default stands."
---
# RoleFraming

M3 decision — per-audience role wording is a note, not an inline override. The
exporter has no blank-node support, so an override can't ride on the Application
as an anonymous `{ position, roleName }` object; and keying it on `rg:audience`
(not an employer) keeps reusable framings in the PUBLIC vault. The Position
keeps a truthful default `roleName`; a RoleFraming is an alternative HONEST
phrasing of the same role for one audience — never a title you weren't given.

Fields: `framingOf` (the Position reframed), `audience` (rg:audience — one of
data-eng | ai-eng | delivery; never `general`, which is the default), `roleName`
(sdo:roleName — the override wording).

Projection consumes framings, then strips them: they never appear in the CV
output. The default site/graph shows default roleNames; only a projection for an
Application declaring the matching audience swaps in the framed wording.
