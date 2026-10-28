# Design decisions

Why the project works the way it does. Add an entry whenever you change a rule, with the
date and what prompted it, so the next person doesn't undo a fix by accident.

---

### Publication data comes from OpenAlex first (2026-10)
Google Scholar has no API, can't be harvested legally at scale, and depends on each
professor keeping a profile up to date, which was the original problem. OpenAlex is free and
openly licensed (CC0), indexes Crossref, PubMed, arXiv and repositories, and records the
institution on each paper. ORCID, Crossref and CUNY Academic Works fill gaps.

### Who counts as faculty comes from the department directories (2026-10)
No publication database knows who is full-time. The directory pages do. `tools/build_roster.py`
reads the saved PDFs: names are 9–10pt bold capitals with the title in small regular type
underneath. Some PDFs drop the letter pairs "fi", "fl" and "ffi" from email addresses, so
emails are matched back to names and repaired where needed.

### "Verified" means the paper itself ties the person to City Tech (2026-10)
OpenAlex sometimes merges different people who share a name into one author profile. On the
first real run, the profiles for Lin Zhou, Nan Li, Satyanand Singh, Joseph B. Franklin and
George Guida were full of other researchers' work. So tiers count only papers that list City Tech
for that person, or are on their ORCID record or in CUNY Academic Works. Other papers on the
profile appear as "unverified". People with only unverified AI papers are marked "Needs review".

### What counts as an AI paper (2026-10, calibrated against all 3,124 City Tech papers)
Strong evidence (enough alone): an AI term in the title; an OpenAlex topic whose name is
about AI; two or more different AI terms in the abstract. Weak evidence (two needed):
an AI term in OpenAlex's auto-generated keywords; one AI term in the abstract.

Each exclusion fixes a real false positive found in review:
- OpenAlex files *quantum information*, *cryptography/coding theory*, *logic and type systems*
  and *security and verification* under its "Artificial Intelligence" subfield. Topics are
  judged by name, not subfield.
- *Educational Robotics and Engineering* (VEX/ROS robotics courses) and *Distributed Control
  Multi-Agent Systems* (vehicle formation control) aren't AI research.
- "CNN" matched the news network, and "GAN" is also a surname. Both removed.
- "Deep learning" as a teaching philosophy ("Place-Based Learning as a High Impact
  Educational Practice") is rejected when it's the only evidence and the text is about education.
- One passing mention in an abstract, such as "artificial intelligence" in an essay about Star Wars,
  isn't enough on its own.
- "AI" in a title counts only in capitals, so "aid" and "Ai Weiwei" don't.

- (2026-10-26, first GitHub run, which checked every paper rather than only papers with AI words)
  Topic names are matched as whole words: "Neurodegenerative" contains "generative", and
  "Paleontology" and "Gerontology" contain "ontology". Robotics topics count only for learning,
  planning or perception (path planning, localization, social robots), not robot hardware,
  mechanics or control (micro/nano robotics, soft robotics, prosthetics). The same phrase
  appearing in both keywords and abstract counts as one weak signal, not two.

The cases are kept as tests in `tests/test_classifier.py`.

### Tiers (2026-10)
Core AI expert: 5+ verified AI papers, 1+ in the last 3 years. Active: 2+ and 1+ recent.
Some AI work: 1+. These are deliberately simple so a reader can check them by hand.
Publication counts miss teaching, grants, patents and industry work, so the site says the list is a
starting point for outreach, not a ranking of people.

### People not on the roster still appear (2026-10)
The first roster covered only Arts & Sciences. Most AI publishing at City Tech happens in the
technology departments, so leaving out unrostered authors would have hidden most of the experts.
They're shown as "Not on roster yet" if they have 4+ City Tech papers and one within 6 years.
That filters out student co-authors and people who left. Name variants ("Yu-Wen Chen" and "Yuwen Chen")
are merged by last name and first initial.

### Human decisions live in overrides.csv (2026-10)
Review work would be wasted if the next monthly rebuild undid it. Every decision is one row,
with who made it and why. Rows that stop matching anything are reported, not silently dropped.

### Safety checks before publishing (2026-10)
If City Tech papers drop below 70% of last month, or the talent pool shrinks below 60%, the
run is refused and the live site keeps last month's data. Outages and quota problems at a data
source look exactly like this, and publishing them would make experts vanish from the site.
A maintainer can override with "force" after checking.

### Alerts arrive as GitHub issues (2026-10)
GitHub sends scheduled-job failure emails only to the person who created the schedule
(GitHub docs, "Notifications for workflow runs"). After a handover that person may be gone.
Issues reach everyone watching the repository.

### A commit every month, even when a run fails (2026-10)
GitHub disables scheduled workflows in public repositories after 60 days without repository
activity (GitHub docs, "Disabling and enabling a workflow"). The job always commits its report,
so the schedule stays alive.

### OpenAlex paging without cursors (2026-10)
In 2026 OpenAlex began requiring an API key for cursor paging. Plain `page=` paging still works
without one, up to 10,000 results per query; City Tech has about 3,100 papers. The optional
`OPENALEX_API_KEY` gives the job its own daily quota.

### Static website on GitHub Pages (2026-10)
No server to patch, no database to back up, no cost, and the data file is readable by anyone
who wants to reuse it. Everything shown is public: bibliographic records and the public
faculty directory.

### Hosting: public site on GitHub Pages (2026-10-26)
Considered Cloudflare Pages + Cloudflare Access (free; lets the repository stay private and
limits viewers to CUNY email addresses). Chose a public GitHub Pages site because everything
shown is already public (bibliographic records, the faculty directory) and one platform means
one fewer account to hand over. To switch to CUNY-only access, follow MAINTAINING.md section 10.

### Version 2: faculty from the directories, every item type, Excel round-trip (2026-10-28)
Restructured after review feedback (a sketch of the dashboard plus the CUNY Talent Pool
publication data template, first used for Computer Engineering Technology):

- **Faculty list from the department directories, not PDFs.** Each directory page names its
  department ID; the page loads people from `/dashboard/odata/Employees?$filter=Dept_ID eq N`. The job
  makes that same per-department request monthly and keeps only name, title, email, office and bio
  (never phone numbers). The CET pilot used the same feed. Titles are sorted into full-time / adjunct /
  staff with the lists the college's own directory script uses. If the site is down, last month's copy is
  used; if more than half the departments can't be read, the run is refused.
- **All item types, not only papers.** Types follow the template (Journal article, Conference paper,
  Book, Book chapter, Conference presentation, Technical report, Paper (venue type unclear), Patent,
  Grant) plus Preprint, Dataset, Dissertation, Open educational resource, Other. OpenAlex "article" is
  split by venue type (journal vs conference); errata, paratext and similar go to Items Excluded.
- **Grants from NSF and NIH.** Both are free public APIs. NSF lists co-investigators with their
  @citytech.cuny.edu email, so they're matched exactly. NIH yearly records are combined per project.
- **Faculty bios are a source ("Dept bio").** Many bios list publications and grants under headings.
  These are read with rules (headings decide the type; quotes or the text after "(year)" give the title)
  and merged with matching items from other sources.
- **Google Scholar via uploads only.** It has no API and blocks automated access (CAPTCHA). Teams can
  upload workbooks in the template; their items merge in with their stated sources and confidence.
- **Confidence replaces verified/unverified.** High = the paper lists City Tech, or it's in Academic Works,
  an NSF/NIH award to City Tech, their ORCID record, their bio, or a reviewer confirmed it. Medium = two
  sources, or a Scholar profile listing City Tech. Low = only a same-name author profile (these go to
  Items To Check and never count toward a tier).
- **Permanent ItemIDs** (DEPT-0001), stored in `data/item_ids.csv`, so a reviewer's tick still points at
  the same item next month. Uploaded workbooks from other teams use their own numbering, so their
  IDs are ignored and their rows imported as new items (duplicates merge).
- **Review happens in Excel.** Static hosting can't save clicks, and a login system would be more to
  hand over. So the dashboard links to the Excel; reviewers tick Check / fix cells and upload it,
  and every decision becomes a row in overrides.csv with the reviewer's name.
- **"Not on roster yet" removed.** With every department's directory read, City Tech authors who
  don't match anyone are students, visitors or former faculty. They're listed in `output/unmatched_authors.csv`.
- **Crossref not queried separately.** OpenAlex already includes Crossref's DOIs and metadata.
