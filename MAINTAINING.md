# Maintaining the City Tech AI Talent Pool

This is the handbook for whoever looks after this project. It assumes no programming
background for the routine parts. Everything routine happens in a web browser on GitHub.

**Time needed:** about 15 minutes a month, plus about an hour each semester.

---

## 1. What this project is

CUNY wants to know which City Tech faculty are experts in artificial intelligence. Google
Scholar pages are often out of date, so this project builds the list from publication
databases instead and refreshes it every month.

```
 roster.csv ──┐   (who the faculty are: built from the department directory pages)
              ▼
 GitHub Actions, 1st of every month
   1. runs the tests
   2. citytech_pubs.py pulls every City Tech paper from OpenAlex, plus ORCID,
      Crossref and CUNY Academic Works
   3. tags AI papers, ranks people into tiers, applies the review decisions in overrides.csv
   4. safety checks: refuses to publish if the results look broken
   5. saves docs/data/talent_pool.json  ──►  website (GitHub Pages, docs/index.html)
   6. opens a GitHub issue if anything needs a person to look at it
```

The website is a single page that reads one data file. There is no server and no database,
and nothing to pay for.

## 2. Where everything lives

| File | What it is | When you touch it |
|---|---|---|
| `roster.csv` | Every faculty member: name, department, full-time/adjunct, title, email, ORCID | Each semester (section 6) |
| `overrides.csv` | Decisions people made during review ("that paper isn't theirs") | During monthly review (section 5) |
| `OWNERS.md` | Who is responsible right now | At every handover |
| `docs/index.html` | The website | Rarely: wording or design changes |
| `docs/data/talent_pool.json` | The data the website shows. Written by the monthly job. | Never by hand |
| `output/` | Monthly spreadsheets and `run_report.md`. Written by the monthly job. | Read only |
| `citytech_pubs.py` | The program that does the work | Only to change the rules (section 7) |
| `tools/build_roster.py` | Turns saved directory PDFs into `roster.csv` | Each semester |
| `tests/` | Automatic checks that run before every update | When you change the rules |
| `DECISIONS.md` | Why things are the way they are | Read before changing the rules |
| `.github/workflows/` | The schedules: monthly update, tests, semester reminder | Rarely |

## 3. Accounts and access

| Thing | Where | Notes |
|---|---|---|
| The repository | GitHub | **Should belong to a GitHub organization with at least two owners**, not to one person's account. If a personal account owns it and that person leaves, the project is stranded. Move it with Settings → General → Transfer ownership. |
| The website | Settings → Pages | Public. Serves the `/docs` folder of the `main` branch. To make it CUNY-only, see section 10. |
| `OPENALEX_API_KEY` | Settings → Secrets and variables → Actions → Secrets | Free key from https://openalex.org/settings/api. Register it with a **shared or role email** (e.g. the department's), not a personal one. Without a key the job shares a small free daily quota and may fail. |
| `CONTACT_EMAIL` | Same page → Variables | Sent to OpenAlex/Crossref to identify us. Use a role email. |
| Alerts | Repository → Watch → Custom → Issues | Everyone responsible should watch issues. Failures and review requests arrive as issues. |

No passwords or personal credentials are stored in the code.

## 4. What happens automatically

| When | What | What you'll see |
|---|---|---|
| 1st of each month, 7am New York | Monthly update (`monthly.yml`) | A new commit "Monthly update …". If anything changed, an issue **"Talent pool review: Month Year"** |
| If the update fails | Same job | An issue **"Monthly update failed"**. Last month's data stays live. |
| Jan 20 and Aug 20 | Reminder (`reminders.yml`) | An issue **"Semester checklist: refresh the roster"** |
| Every change to the code | Tests (`tests.yml`) | A green check or red cross next to the commit |

To run the update now: **Actions → Monthly AI talent pool update → Run workflow.**

## 5. Monthly review (about 15 minutes)

Open the "Talent pool review" issue. It lists what changed since last month. For each item:

**New in the talent pool, "not on roster".** Someone publishes with a City Tech affiliation
but isn't in `roster.csv`. Look them up in the City Tech directory.
- Current faculty: add them to `roster.csv` (or wait for the semester roster refresh) and
  meanwhile record their department in `overrides.csv` (`department` row).
- Student, visitor or former faculty: add a `hide` row.

**Needs review.** Their AI papers sit on their OpenAlex profile but none lists City Tech,
usually because OpenAlex merged several people who share a name. Open their entry on the website and
read the unverified papers.
- None are theirs: `not_theirs, <name>, *unverified*`
- Some are theirs: a `confirm_theirs` row for each paper that is.

**Tier changes / no longer listed.** Usually fine (new papers, or papers aging out of the
3-year window). Check anything surprising.

**Warnings: "overrides.csv line N matched nothing".** A paper or person in a decision row
no longer appears. Usually harmless; delete the row if it's obsolete.

Then close the issue.

### Recording a decision in overrides.csv

On GitHub, open `overrides.csv` → pencil icon → add a line → **Commit changes**.
Decisions take effect at the next monthly run (or run it now, section 4).

| action | person | paper | value | meaning |
|---|---|---|---|---|
| `not_ai` | name | paper | | Paper isn't really about AI |
| `is_ai` | name | paper | | Paper is about AI but wasn't detected |
| `not_theirs` | name | paper, or `*unverified*` | | Paper belongs to someone else with the same name |
| `confirm_theirs` | name | paper | | Unverified paper is theirs; it now counts |
| `department` | name | | department | Set the department of someone not on the roster |
| `hide` | name | | reason | Remove the person from the site |

`paper` can be the OpenAlex ID (the `W…` number at the end of the paper's OpenAlex link),
the DOI, or the exact title. Always fill in `reviewed_by`, `date` and `note`, so the next
maintainer knows who decided and why.

## 6. Every semester (about an hour)

Faculty join and leave, so the roster goes stale. The reminder issue has this checklist.

1. For each department, open its City Tech directory page and print it to PDF from the
   browser: once on the **Full-Time Faculty** tab, once on the **Adjunct Faculty** tab.
   Put all the PDFs in one folder.
2. Rebuild the roster. This step needs Python on a computer (or ask someone who has it):
   ```
   pip install -r tools/requirements.txt
   python tools/build_roster.py path/to/pdf-folder
   ```
   It prints how many people it found per department and flags anyone without an email.
3. Compare with the old roster (GitHub shows the differences when you commit). Large drops
   usually mean a PDF is missing. Carry over the `aka` and `orcid` columns from the old file
   for people who are still there.
4. Commit the new `roster.csv` and run the update.

**Departments to include:** every department in the Schools of Arts & Sciences, Technology &
Design, and Professional Studies. The technology and engineering departments matter most
for AI. If they're missing, most AI experts show up only as "not on roster".

**ORCID iDs** (a column in `roster.csv`) are the biggest single accuracy improvement: they
tie a person to their papers without guessing from names. Add them whenever you learn one.

## 7. Changing the rules

Read `DECISIONS.md` first; most rules exist because of a real mistake they prevent.

| To change | Edit | Where |
|---|---|---|
| Tier thresholds | `TIERS`, `RECENT_YEARS` | `citytech_pubs.py`, "AI expertise" section |
| AI words and phrases | `AI_TERMS` | same |
| Which OpenAlex topics count | `AI_TOPIC_RE`, `NOT_AI_TOPIC_RE` | same |
| Who appears when not on roster | `UNROSTERED_MIN_PUBS`, `UNROSTERED_MAX_GAP` | same |
| Safety-check sensitivity | `GUARD_MIN_WORKS_RATIO`, `GUARD_MIN_PEOPLE_RATIO` | "safety checks" section |
| Website wording or look | text in `docs/index.html` | |

After a change, the Tests workflow runs automatically. A red cross means the change broke
one of the known cases in `tests/test_classifier.py`; read the failure, then either fix the
change or, if the old behavior was wrong, update the test and say why in `DECISIONS.md`.

To try it on your own computer:
```
pip install -r requirements-dev.txt
python -m pytest -q tests          # about a second, no internet needed
python citytech_pubs.py --roster roster.csv --full-career --site-data docs/data/talent_pool.json
```

## 8. Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| Issue "Monthly update failed", report says **REFUSED** | The safety check saw a big drop (papers or people) | Read the report. If OpenAlex had an outage, rerun later. If the drop is real (e.g. a smaller roster), run the workflow with **force** ticked. |
| Failure at "Run tests first" | Someone changed the code and broke a rule | Open the run log, read the failing test, fix or revert the last change |
| Report warns "failed requests to api.openalex.org", or HTTP 429 | Daily quota used up | Add or renew `OPENALEX_API_KEY` (section 3), then rerun |
| No update happened at all this month | GitHub turns off schedules in public repositories after 60 days with no activity | Actions → Monthly AI talent pool update → **Enable workflow**. (The monthly commit normally prevents this.) |
| Failure at "Save results", push rejected | Someone edited files while the job ran | Rerun the workflow |
| Website says the data didn't load | Pages not set up, or the data file is missing | Settings → Pages must serve `main` / `/docs`; run the update once |
| Website didn't change after a run | Pages caches for a few minutes | Wait 10 minutes, hard-refresh |
| A known AI expert is missing | Not on the roster, no City Tech affiliation on papers, or a name mismatch | Check `output/faculty_coverage.csv`. Add their ORCID, or an `aka` name, in `roster.csv` |
| Someone got another person's papers | Same-name confusion | Use `not_theirs` in `overrides.csv` |
| An OpenAlex error mentions an API key | OpenAlex changed its access rules | Get a key (section 3). Check https://docs.openalex.org for current rules |

## 9. Handover checklist

**Outgoing maintainer**
- [ ] Repository owned by an organization, with the incoming person (and a backup) as owners
- [ ] `OPENALEX_API_KEY` registered to a role email; incoming person knows how to log in or make a new one
- [ ] `CONTACT_EMAIL` set to a role email
- [ ] `OWNERS.md` updated
- [ ] Open issues reviewed or explained
- [ ] A 30-minute walkthrough: one monthly review together, using this file

**Incoming maintainer**
- [ ] Watch the repository (Watch → Custom → Issues)
- [ ] Run the update once yourself (section 4). That re-confirms the schedule and shows you a report.
- [ ] Read `DECISIONS.md`
- [ ] Put the semester reminder dates in your calendar too

## 10. Making the site CUNY-only (Cloudflare)

Today the site is public on GitHub Pages (see DECISIONS.md, "Hosting"). If CUNY decides only
CUNY staff should see it, move it to Cloudflare, which is free at this size:

1. Make the GitHub repository private (Settings → General → Danger zone → Change visibility),
   and turn off GitHub Pages (Settings → Pages → Unpublish). GitHub Pages on private
   repositories needs a paid GitHub plan.
2. In Cloudflare: **Workers & Pages → Create → Pages → Connect to Git**, pick this repository,
   framework preset **None**, build command empty, build output directory **`docs`**.
   Cloudflare redeploys automatically after every monthly commit.
3. In Cloudflare **Zero Trust → Access → Applications → Add → Self-hosted**: domain
   `*.<project>.pages.dev` (the `*` also covers preview links), policy **Allow** with
   **Emails ending in** `@cuny.edu` (add a second rule for `@citytech.cuny.edu`).
   Turn on **One-time PIN** under Zero Trust → Settings → Authentication.
4. Test in a private browser window: you should be asked for your email and sent a code.

The free Zero Trust plan covers up to 50 people. Record the Cloudflare account owner in OWNERS.md.
