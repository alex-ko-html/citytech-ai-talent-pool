# City Tech AI Talent Pool

Who at City Tech works in artificial intelligence, and the publications, presentations, grants
and patents that show it. Rebuilt automatically on the 1st of every month. No AI model is used.

- **Dashboard:** https://alex-ko-html.github.io/citytech-ai-talent-pool/ (one block per faculty member:
  School | Name | Department, then Year · Type · Title · Source · Check · Edit)
- **Excel:** the dashboard's **Download Excel** button, in the CUNY Talent Pool template format
  (Items, Faculty, Sources, Items Excluded, plus Items To Check)
- **Corrections:** tick **Check** / fix cells in the Excel and use the dashboard's **Upload** button

**Taking this project over? Start with [MAINTAINING.md](MAINTAINING.md)**, then
[OWNERS.md](OWNERS.md) (who's responsible) and [DECISIONS.md](DECISIONS.md) (why the rules are what they are).

## Where the data comes from
| Source | Gives |
|---|---|
| City Tech department directories | The faculty list (full-time), titles, offices, and bios with self-reported publications and grants |
| OpenAlex | Every paper listing City Tech, with type, venue, abstract, open-access links |
| CUNY Academic Works | City Tech's repository: presentations, posters, OER, deposited papers |
| ORCID | Works on faculty ORCID records (when we know the iD) |
| NSF, NIH | Grants awarded to City Tech, with PI / co-PI |
| Uploaded workbooks | Anything added by hand, e.g. Google Scholar collections |

## Run it yourself
```
pip install -r requirements-dev.txt
python -m pytest -q tests     # offline checks, ~2 seconds
python -m talentpool          # full update (needs internet)
```
