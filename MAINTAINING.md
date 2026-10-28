# Maintaining the City Tech AI Talent Pool

This is the handbook for whoever looks after this project. The routine parts need no
programming. Everything happens in a web browser, on GitHub and in Excel.

**Time needed:** about 15 minutes a month, plus an hour each semester to work through items to check.

---

## 1. What this project is

CUNY wants to know which City Tech faculty work in artificial intelligence. Google Scholar pages
are often out of date, so this project builds the record from the sources themselves and
refreshes it every month. It uses **no AI model**: everything is sorted with written rules.

```
 City Tech department directories ──► faculty list (names, titles, offices, bios)
                                                   │
 OpenAlex · CUNY Academic Works · ORCID ·          ▼
 NSF · NIH · faculty bios · uploaded Excel ──► items (papers, presentations, grants, patents)
                                                   │  merge duplicates, sort by type,
                                                   │  confidence, permanent ItemID, AI flag
                                                   ▼
                       Excel workbook (CUNY template)  +  online dashboard
                                                   ▲
                    reviewers tick Check / fix cells in Excel ──► Upload ──┘
```

It runs on GitHub, for free, on the 1st of every month (GitHub Actions). The dashboard is a page
on GitHub Pages that reads one data file. There's no server or database to look after.

## 2. Where everything lives

| File or folder | What it is | Who changes it |
|---|---|---|
| `docs/index.html` | The dashboard | Rarely, for wording or design |
| `docs/data/CityTech_Talent_Pool.xlsx` | **The Excel deliverable** (Download button) | The monthly job |
| `docs/data/talent_pool.json` | The data the dashboard shows | The monthly job |
| `inbox/` | Where uploads land (Upload button); processed files move to `inbox/processed/` | Uploaders |
| `overrides.csv` | **Every review decision** (who decided what, and why) | Written by uploads; can be edited by hand |
| `faculty_extra.csv` | Corrections and additions to the faculty list: other names people publish under, ORCID iDs, Google Scholar details | Written by uploads; can be edited by hand |
| `data/faculty_directory.csv` | Last copy of the directories (used if the college site is down) | The monthly job |
| `data/item_ids.csv` | The permanent ItemIDs (CET-0014 always means the same item) | The monthly job. **Never edit.** |
| `data/imported_items.csv` | Items added through uploads (e.g. Google Scholar collections) | Uploads |
| `output/run_report.md` | This month's report | The monthly job |
| `talentpool/` | The program, one file per job (see section 7) | Only to change the rules |
| `tests/` | Automatic checks run before every update | When you change the rules |
| `DECISIONS.md` | Why the rules are what they are | Add to it when you change a rule |
| `OWNERS.md` | Who is responsible | At every handover |

## 3. Accounts and access

| Thing | Where | Notes |
|---|---|---|
| The repository | GitHub | **Should belong to a City Tech or CUNY GitHub organization with at least two owners**, not one person. Move it with Settings → General → Transfer ownership. |
| Who can upload | Settings → Collaborators | Uploading needs write access to the repository. Add reviewers here. |
| The website | Settings → Pages | Public. Serves `/docs` on `main`. To make it CUNY-only, see section 10. |
| `OPENALEX_API_KEY` | Settings → Secrets and variables → Actions → Secrets | Free key from https://openalex.org/settings/api, registered to a **role email**. Without one, the job shares a small daily quota and may fail. |
| `CONTACT_EMAIL` | Same page → Variables | Sent to the data sources to identify us. Use a role email. |
| Alerts | Repository → Watch → Custom → Issues | Everyone responsible should watch issues. Failures and monthly reviews arrive as issues. |

## 4. What happens automatically

| When | What | What you'll see |
|---|---|---|
| 1st of each month, 7am New York | Monthly update (`monthly.yml`) | A commit "Monthly update …". If anything changed, an issue **"Talent pool review: Month Year"** |
| Whenever a file is uploaded to `inbox/` | `uploads.yml` applies it, then reruns the update | A commit "Apply upload from …", then the dashboard refreshes within ~5 minutes |
| If anything fails | Same jobs | An issue **"Monthly update failed"** or **"Upload could not be processed"**. The live data is never overwritten by a broken run. |
| Jan 20 and Aug 20 | `reminders.yml` | An issue **"Semester checklist"** |
| Every code change | Tests (`tests.yml`) | Green check or red cross next to the commit |

Run the update now: **Actions → Monthly AI talent pool update → Run workflow.**

## 5. Monthly review (about 15 minutes)

Open the "Talent pool review" issue. It lists what changed: people newly in the AI talent pool,
tier changes, new or departed faculty, warnings, and how many items need checking.

**Check items in Excel. This is the main review tool:**
1. On the dashboard, click **Download Excel**.
2. **Items To Check** tab: papers on an author profile with the same name but no City Tech
   affiliation. In the yellow **Check** column pick **Confirmed** (it's theirs) or **Not theirs**.
3. Anywhere: fix a wrong **ItemType, ItemTitle, Year, Venue / Funder, Role or Amount** by typing
   over the cell. Use **Not AI** / **Is AI** in Check to correct the AI flag.
4. **Missing item?** Add a row at the bottom of **Items**. Leave ItemID empty and fill in FullName,
   Email, ItemType, ItemTitle, Year and Sources.
5. Put your name in **Reviewed by**, save, then click **Upload** on the dashboard → drag the file
   in → **Commit changes**.

The upload becomes rows in `overrides.csv` (one per decision, with your name and the date) and
is applied at every future run. Don't rename or reorder columns, and don't change ItemIDs.

**Single corrections from anyone:** the dashboard's **Edit** link opens a pre-filled GitHub issue.
Apply it by ticking the item in Excel and uploading, or by adding a row to `overrides.csv`, then close the issue.

### overrides.csv by hand

| action | person | item | field | value | meaning |
|---|---|---|---|---|---|
| `confirm` | | CET-0014 | | | It's theirs and correct |
| `not_theirs` | name | CET-0014, or `*unverified*` | | | Someone else's (`*unverified*` = all their to-check items) |
| `not_ai` / `is_ai` | | CET-0014 | | | Fix the AI flag |
| `set` | | CET-0014 | ItemType | Conference paper | Correct a field |
| `department` | name | | | department | Correct someone's department |
| `hide` | name | | | reason | Remove a person from the site |

Always fill in `reviewed_by`, `date` and `note`.

## 6. Every semester (about an hour)

**The faculty list updates itself.** Each month the job reads every department's directory on
citytech.cuny.edu, so new hires appear and departures drop off automatically. The semester
checklist issue covers what's left:
- Work through the **Items To Check** tab (section 5).
- Skim the report's warnings, e.g. a department whose directory couldn't be read.
- If someone publishes under another name, add it in `faculty_extra.csv` (`aka` column).
  If you know their **ORCID iD**, add it too. That's the biggest single accuracy improvement.
- **Google Scholar** can't be read automatically (no API, and it blocks automated access). To include
  Scholar items, fill a workbook in the CUNY template (the format of the Download) and upload it.
  Duplicates merge automatically.

## 7. Changing the rules

Read `DECISIONS.md` first. Most rules exist because of a real mistake they prevent.

The program, `talentpool/`, has one file per job:

| File | Job | Change it to… |
|---|---|---|
| `directory.py` | Faculty list from the directories | Add a department (`DEPARTMENTS`) or adjust how titles map to full-time / adjunct / staff |
| `sources.py` | Fetch items from each source | Add a source, or adjust how bios are read |
| `items.py` | Merge, type, confidence, ItemIDs | Change type names (`ITEM_TYPES`) or confidence rules |
| `ai.py` | AI flag and tiers | Tier thresholds (`TIERS`), AI words (`AI_TERMS`), topic rules |
| `review.py` | overrides.csv, safety checks, report | Safety-check thresholds (`GUARD_…`) |
| `workbook.py` | The Excel file | Columns (keep the CUNY template's columns first and in order) |
| `inbox.py` | Uploads | Accepted file formats |
| `run.py` | Runs everything in order | Rarely |

After a change, the Tests workflow runs. A red cross means the change broke a known case. Read the
failure, then fix the change, or update the test and record why in `DECISIONS.md`.

On your own computer:
```
pip install -r requirements-dev.txt
python -m pytest -q tests        # about 2 seconds, no internet needed
python -m talentpool             # a real update (needs internet)
python -m talentpool.inbox       # apply files in inbox/
```

## 8. Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| "Monthly update failed", report says **REFUSED** | The safety check saw a big drop (faculty, items or directories) | Read the problems listed. If a source had an outage, rerun later. If the drop is real, run the workflow with **force** ticked. |
| Report warns a department's directory "unavailable" | The college site was down or that page moved | Last month's copy was used. If it persists, check the department's page address in `directory.py`. |
| "Upload could not be processed" | The file isn't our workbook or the CUNY template, or columns were renamed | Fix the file and upload again; the failed file stays in `inbox/` (delete it on GitHub if replacing) |
| Failure at "Run tests first" | A code change broke a rule | Open the run log, read the failing test, fix or revert |
| "failed requests to api.openalex.org", HTTP 429 | Daily quota used up | Add or renew `OPENALEX_API_KEY` (section 3) |
| No update this month | GitHub disables schedules in public repos after 60 days without activity | Actions → Monthly AI talent pool update → **Enable workflow** (the monthly commit normally prevents this) |
| Dashboard didn't change after an upload | Pages caches for a few minutes, or the rebuild is still running | Check Actions; wait 10 minutes; hard-refresh |
| A known expert is missing | Not full-time in the directory, a name mismatch, or papers without City Tech affiliation | Add their ORCID or `aka` in `faculty_extra.csv`; confirm items in Items To Check |
| Someone got another person's papers | Same-name confusion | **Not theirs** in Excel, or `not_theirs` in `overrides.csv` |

## 9. Handover checklist

**Outgoing maintainer**
- [ ] Repository owned by an organization, incoming person (and a backup) as owners
- [ ] `OPENALEX_API_KEY` registered to a role email; incoming person can log in or make a new one
- [ ] `CONTACT_EMAIL` set to a role email
- [ ] Reviewers added as collaborators
- [ ] `OWNERS.md` updated
- [ ] Open issues reviewed or explained
- [ ] 30-minute walkthrough: one monthly review together using this file

**Incoming maintainer**
- [ ] Watch the repository (Watch → Custom → Issues)
- [ ] Run the update once yourself (section 4)
- [ ] Download the Excel, tick one item, upload it, and see it applied
- [ ] Read `DECISIONS.md`

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
Note: with a private repository, the Upload button still works for collaborators, and the dashboard's
Edit links need viewers to have repository access.
