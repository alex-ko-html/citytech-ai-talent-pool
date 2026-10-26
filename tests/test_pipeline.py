"""End-to-end monthly run against a fake OpenAlex: ranking, review decisions, safety checks."""
import csv, importlib, json, shutil, sys
from pathlib import Path
import pytest
import citytech_pubs
from fake_openalex import default_works, make_fake_get

ROOT = Path(__file__).resolve().parents[1]


def run(tmp, citytech=None, elsewhere=None, overrides=None, extra=()):
    C = importlib.reload(citytech_pubs)
    ct, el = default_works()
    C.get = make_fake_get(citytech if citytech is not None else ct, elsewhere if elsewhere is not None else el)
    shutil.copy(ROOT / "roster.csv", tmp / "roster.csv")
    ov = tmp / "overrides.csv"
    with open(ov, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["action", "person", "paper", "value", "reviewed_by", "date", "note"])
        for row in overrides or []:
            w.writerow(row)
    sys.argv = ["x", "--roster", str(tmp / "roster.csv"), "--full-career", "--skip", "orcid", "crossref",
                "academicworks", "--out", str(tmp / "out"), "--site-data", str(tmp / "site.json"),
                "--overrides", str(ov), *extra]
    C.main()
    return json.loads((tmp / "site.json").read_text()), json.loads((tmp / "out" / "run_report.json").read_text())


def people(site):
    return {p["name"]: p for p in site["people"]}


def test_ranking(tmp_path):
    site, rep = run(tmp_path)
    P = people(site)
    assert P["Viviana Acquaviva"]["tier"] == "Core AI expert" and P["Viviana Acquaviva"]["verified"] == 5
    assert P["Lin Zhou"]["tier"] == "Needs review"               # AI papers only off-affiliation
    assert P["Yuwen Chen"]["on_roster"] is False                  # "Yu-Wen Chen" merged in -> 4 papers
    assert "Oleg Berman" not in P and "Sean P. Macdonald" not in P
    assert "Some Student" not in P                                # one-off co-author filtered out
    assert rep["status"] == "OK"


def test_review_decisions_persist(tmp_path):
    site, rep = run(tmp_path, overrides=[
        ["not_theirs", "Lin Zhou", "*unverified*", "", "tester", "2026-10-21", "different people"],
        ["department", "Yuwen Chen", "", "Computer Engineering Technology", "tester", "", ""],
        ["not_ai", "Viviana Acquaviva", "W5", "", "tester", "", "ethics essay"],
        ["hide", "Nobody Here", "", "left", "tester", "", ""],
    ])
    P = people(site)
    assert "Lin Zhou" not in P
    assert P["Yuwen Chen"]["department"] == "Computer Engineering Technology"
    assert P["Viviana Acquaviva"]["verified"] == 4
    assert any("matched nothing" in w for w in rep["warnings"])   # the stale 'hide' row is flagged


def test_broken_run_does_not_overwrite(tmp_path):
    good, _ = run(tmp_path)
    ct, _ = default_works()
    with pytest.raises(SystemExit) as e:
        run(tmp_path, citytech=ct[:2])                             # OpenAlex "lost" most papers
    assert e.value.code == 2
    assert json.loads((tmp_path / "site.json").read_text()) == good  # last good data kept
    rep = json.loads((tmp_path / "out" / "run_report.json").read_text())
    assert rep["status"] == "REFUSED"


def test_month_to_month_changes_reported(tmp_path):
    run(tmp_path)
    ct, el = default_works()
    from fake_openalex import work, author
    ct.append(work(99, "Large language models for tutoring", 2026, [author("Viviana Acquaviva", "A1")]))
    ct += [work(100 + k, f"Computer vision study {k}", 2025, [author("New Person", "A77")]) for k in range(4)]
    site, rep = run(tmp_path, citytech=ct, elsewhere=el)
    assert ("New Person", "Active in AI", False) in [tuple(x) for x in rep["new_people"]]
