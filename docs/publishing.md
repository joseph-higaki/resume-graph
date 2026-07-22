# Publishing

What lands on `https://joseph-higaki.github.io/resume-graph/`, how it gets there,
and what the unlisted application URLs do and do not protect.

## The site

```
/                                     graph.html — the viewer is the landing page
/graph.html /graph.jsonld /graph.ttl  the graph, three ways
/resume.html /resume.json /resume.pdf the derived résumé
/robots.txt                           permissive; see "Crawling" below
/application/<publicId>/              unlisted, one per tailored CV
    index.html graph.html graph.ttl resume.html resume.json resume.pdf
```

`index.html` is a byte copy of `graph.html`, not a redirect: the root is the one
page every visitor loads, and a redirect would spend a round trip on it. The
duplicate costs ~160 KB against a 1 GB Pages limit.

Everything under `/` is derived from `dist/` by `make pages`, which CI runs
verbatim — the deployable tree has a single definition, so `make serve` previews
exactly what deploys.

## Applications: unlisted, not private

**Anything on this site is world-readable.** The employer name is inside
`graph.ttl`, `resume.json`, and the PDF regardless of what the folder is called.
`rg:publicId` buys unguessability and nothing else. The realistic threat is not a
crawler, it is a forwarded link.

The three mitigations, in order of how much work they actually do:

1. **The opaque directory.** A 128-bit segment is not enumerable. This is the
   whole protection; the rest is hygiene.
2. **`<meta name="robots" content="noindex, nofollow, noarchive">`** on every
   projected HTML page, stamped by `project.py`, unconditionally — a file that
   starts on disk and later gets copied somewhere public must already refuse on
   its own. It does not cover `resume.pdf` / `graph.ttl` / `resume.json`, which
   cannot carry a meta tag and would need an `X-Robots-Tag` header that GitHub
   Pages does not serve.
3. **`<meta name="referrer" content="no-referrer">`.** Closes the likelier leak:
   without it, every outbound click from the page hands the secret URL segment to
   a third party in the `Referer` header.

`robots.txt` deliberately does **not** `Disallow: /application/`. A disallowed
URL is never fetched, so the `noindex` is never read — and a URL that leaked from
somewhere else would then be indexed URL-only, which is the exact outcome the
`noindex` exists to prevent. Allow the crawl, refuse the index.

If a CV ever needs to be genuinely private, this mechanism is the wrong one; put
it behind an authenticating host instead.

## How a CV reaches the site

The two repos never share a git history. Only a signal crosses the boundary.

```
resume-applications                          resume-graph
  vault/applications/*.md   ── make applications ──▶ dist/applications/<publicId>/
  (publicId: <32 hex>)      ◀───────────────────────  (the pipeline lives here)

  make publish  ─▶ published/<publicId>/     (promote — the deploy queue)
  git commit    ─▶ .github/workflows/publish.yml
                        │ repository_dispatch: applications-updated
                        ▼
                   resume-graph CI ── checkout published/ (read-only PAT)
                                   ── make pages APPS_REPO=.apps
                                   ── deploy-pages
```

Building and publishing are separate on purpose. `make applications` can be
re-run at will without touching the site; `make publish` + a commit is the
deliberate, reviewable act of putting a CV on the public web.

The tailored CVs exist in this public repo's git history at no point. They are
checked out into `.apps/` (gitignored) during a CI run and live on only inside
the ephemeral Pages artifact.

### 1. Minting a `publicId`

The pipeline never generates ids — it only reads `rg:publicId` from the note.
Mint one yourself and paste it into the application note's frontmatter in the
private repo:

```bash
python3 -c "import uuid; print(uuid.uuid4().hex)"
```

Minted **once per application, never regenerated** — the URL goes out to a
person, so a rebuild must not move it. SHACL enforces the shape
(`^[0-9a-f]{32}$`); anything else fails validation before it can deploy.

**`make publish` only promotes directories named by 32 hex characters.** An
application whose note carries no `rg:publicId` is projected to its readable slug
instead, so it is structurally unpublishable — a folder named after an employer
cannot reach a public host by accident.

### 2. Publishing and re-publishing

```bash
# in resume-graph
make applications          # build every application from the private overlay
make serve                 # preview http://localhost:8000/application/<publicId>/
make publish               # promote into ../resume-applications/published/

# in resume-applications — this commit IS the publish
git add published/ && git commit -m "publish <publicId>" && git push
```

That push is enough if `publish.yml` and `GRAPH_REPO_TOKEN` are set up. Otherwise
trigger the deploy yourself, from resume-graph:

```bash
make deploy                # dispatch from your own gh credentials
```

`make deploy` is the manual twin of `publish.yml` — the same signal, sent from
your laptop instead of a runner. It refuses to fire if `published/` has
uncommitted changes or unpushed commits, because **CI checks out the pushed
tree**: a local `make publish` you never pushed deploys nothing, successfully and
silently. It then confirms a run actually started (see the `/dispatches` trap
below) and prints the live URLs.

Re-publishing an updated CV is the same sequence, unchanged: the `publicId`
stays fixed, so the rebuilt pages replace the old ones at the same URL and every
link already in someone's inbox keeps working.

### 3. Removing a CV

```bash
# in resume-applications
git rm -r published/<publicId>
git commit -m "unpublish <publicId>" && git push

# from resume-graph, unless auto-deploy is set up
make deploy
```

The old URL 404s on the next deploy. Rotating a URL instead of removing it is a
new `publicId` in the note, then rebuild, publish, and `git rm` the old
directory — but assume anyone who had the old URL kept a copy of the content.

## Secrets

Two fine-grained PATs, each scoped to exactly one repository. Only the first is
required:

| Stored in | Name | Scope | Permission | Required? |
|---|---|---|---|---|
| `resume-graph` | `APPS_REPO_TOKEN` | `resume-applications` | Contents: **Read** | **yes** |
| `resume-applications` | `GRAPH_REPO_TOKEN` | `resume-graph` | Contents: **Read and write** | only for auto-deploy |

`APPS_REPO_TOKEN` has no substitute: a CI runner cannot read a private repo
without one. Unset — forks, pull requests, a fresh clone — CI deploys the public
site alone and says so in the log, which is a correct build rather than a
failure. That is the contract from `.claude/CLAUDE.md`: the pipeline behaves
identically whether the overlay is present or not.

`GRAPH_REPO_TOKEN` only automates the signal. Skip it (and `publish.yml` with it)
and run `make deploy` after each publish — your `gh` login already has access to
both repos. Its write permission is not a typo: `repository_dispatch` requires
Contents write, which is exactly why that token is scoped to one repo and
carries nothing else.

## Failure modes

- **Application pages vanish after a routine push.** The `Fetch published
  applications` step is gated on the token, not on the event type, precisely so
  this cannot happen: Pages replaces the entire site on every deploy, so every
  deploy must re-fetch. If they do disappear, the token expired — fine-grained
  PATs have a maximum lifetime and expire silently.
- **Dispatch is accepted but nothing runs.** `POST /dispatches` answers `204` on
  success *and* when it matched no workflow — it has no way to report having done
  nothing. GitHub honours `repository_dispatch` only for a workflow file already
  committed to the **default branch**, so the very first deploy fails this way:
  the dispatch lands before `ci.yml` carrying `repository_dispatch` is pushed.
  `make deploy` diffs the run list before and after and fails loudly on this.
- **A push to the overlay triggers no workflow at all.** `publish.yml`'s
  `branches:` filter must list the overlay's actual default branch —
  `resume-applications` and `resume-graph` both default to `main` (as of
  2026-07-21; `resume-applications` was renamed from `master` to match). If
  either is renamed again, update the filter. A `branches:` filter that
  matches nothing produces no run, no warning, and no failed check — there is
  nothing in the UI
  to notice.
- **Actions is not the suspect.** Private repos run Actions on the free tier
  (2,000 minutes/month). `gh run list -R <repo>` returning empty means the
  trigger never matched, not that Actions is unavailable.
- **A stale slug-named directory in `dist/applications/`.** Left behind when an
  application gains a `publicId` after having been built without one. Harmless —
  `make publish` skips it — but delete it to keep the local tree honest.
