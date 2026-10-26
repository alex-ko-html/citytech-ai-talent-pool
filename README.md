# City Tech AI Talent Pool

A website listing City Tech faculty with AI publication records, rebuilt automatically
on the 1st of every month.

**Taking this project over? Start with [MAINTAINING.md](MAINTAINING.md)** (the handbook),
then [OWNERS.md](OWNERS.md) (who's responsible) and [DECISIONS.md](DECISIONS.md) (why the
rules are what they are).


- **Front end:** `docs/index.html`, served free by GitHub Pages. It reads `docs/data/talent_pool.json`.
- **Back end:** `citytech_pubs.py`, run monthly by GitHub Actions (`.github/workflows/monthly.yml`).
  It pulls publications from OpenAlex, ORCID, Crossref and CUNY Academic Works, tags AI papers,
  ranks people, and commits the new data file. The site picks it up automatically.

## One-time setup (about 10 minutes)
1. Create a repository on GitHub and upload everything in this folder, including the hidden
   `.github` folder.
2. **Settings → Pages:** Source "Deploy from a branch", branch `main`, folder `/docs`. Save.
   The site appears at `https://<username>.github.io/<repo>/` within a minute or two.
   (Pages on a private repository needs a paid GitHub plan; otherwise make the repo public.)
3. **Settings → Secrets and variables → Actions:**
   - Variables tab: add `CONTACT_EMAIL` = your email.
   - Secrets tab (recommended): add `OPENALEX_API_KEY`, registered to a role email. A free key from
     https://openalex.org/settings/api gives the job its own daily quota.
     Without a key the job shares a small free quota with everyone on GitHub's network.
4. **Actions tab → "Monthly AI talent pool update" → Run workflow** to do the first refresh now.
5. **Watch → Custom → Issues**, so failures and review requests reach you. Ideally the repository
   belongs to a GitHub organization with at least two owners (see MAINTAINING.md, section 3).

## How people are ranked
- A paper counts as AI when its **title** uses specific AI terms, **or** OpenAlex files it under
  an AI topic, **or** its abstract uses two or more AI terms. The site shows the evidence for each paper.
- **Verified** = the paper lists City Tech for that person (or is on their ORCID record /
  CUNY Academic Works). **Unverified** = it only sits on the same OpenAlex profile. Common
  names often get merged with other researchers, so unverified papers never count toward a tier.
- Tiers (edit `TIERS` in `citytech_pubs.py`):
  - Core AI expert: 5+ verified AI papers, 1+ in the last 3 years
  - Active in AI: 2+ verified, 1+ recent
  - Some AI work: 1+ verified
  - Needs review: no verified AI papers but 2+ unverified ones

## Roster
`roster.csv` holds name, aka (other names they publish under), department, status, title, email,
orcid, openalex_id. Only rows whose status contains "Full" are used (`--include-all` adds adjuncts).

City Tech authors who aren't on the roster still appear, marked "Not on roster yet", if they
have 4+ City Tech papers and one in the last 6 years. Turn this off with `--roster-only`.

**Adding departments:** save each department's directory page (full-time and adjunct tabs) as PDFs in one folder, then run `python tools/build_roster.py path/to/pdf-folder`. It extracts names, titles and emails and rewrites `roster.csv`. Adding ORCID iDs to the roster
is the single biggest accuracy improvement.

## Outputs (in `output/`, refreshed monthly)
- `ai_talent_pool.csv`: the ranked list
- `publications.xlsx`: tabs for the talent pool, AI papers, all papers, and coverage
- `faculty_coverage.csv`: roster faculty with no publications found (check by hand)
- `unmatched_authors.csv`: City Tech authors missing from the roster
