# Changelog

Notable changes to the rules, data or website. Newest first. (Routine monthly data updates
are not listed; they're in the commit history and `output/run_report.md`.)

## 2026-10-28 (version 2)
- Restructured to the review sketch and the CUNY Talent Pool data template.
- Faculty list read automatically from all 28 department directories (PDF tools removed).
- All item types (articles, conference papers, presentations, books, grants, patents...), sorted by rules.
- New sources: NSF and NIH grants, faculty bios; Google Scholar via uploaded workbooks.
- Excel deliverable in the template format with Check / correction columns; Upload button applies it.
- Dashboard: School | Name | Department blocks with Year · Type · Title · Source · Check · Edit.
- Program split into talentpool/ (one file per job); 18 offline tests.

## 2026-10-26
- Moved to GitHub (alex-ko-html/citytech-ai-talent-pool); public site on GitHub Pages.
- First GitHub run exposed topic false positives (substring matches, robot hardware); rules tightened, tests added.

## 2026-10
- Handover setup: `overrides.csv` for review decisions, safety checks that refuse broken runs,
  monthly `run_report.md`, GitHub issues for failures and review, test suite, semester reminder,
  pinned dependencies, `MAINTAINING.md`, `DECISIONS.md`, `OWNERS.md`.
- AI classification calibrated against all 3,124 City Tech papers in OpenAlex (see DECISIONS.md).
- Verified vs. unverified papers; "Needs review" tier.
- City Tech authors missing from the roster shown as "Not on roster yet".
- Website: searchable talent pool with evidence for every paper (`docs/index.html`).
- Roster built from 18 Arts & Sciences directory PDFs: 560 people, 174 full-time.
