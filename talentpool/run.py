"""The monthly update, start to finish.  Run:  python -m talentpool

 1. Faculty      read every department directory (directory.py), add faculty_extra.csv
 2. Items        OpenAlex, CUNY Academic Works, ORCID, NSF, NIH, faculty bios, uploaded items (sources.py)
 3. Sort         merge duplicates, type, confidence, permanent ItemIDs (items.py)
 4. AI           flag AI-related items with rules and rank people (ai.py), no AI model involved
 5. Review       apply overrides.csv (review.py)
 6. Check        refuse to publish if the results look broken compared with last month
 7. Publish      Excel workbook + dashboard data in docs/data/, report in output/
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import sources as S
from .ai import tag_items, tier_people, TIERS, REVIEW_TIER, RECENT_YEARS
from .common import SESSION, log, write_csv
from .directory import load_directory, is_faculty, Roster, DEPARTMENTS
from .items import merge_items, set_confidence, is_confirmed, ItemIds, ITEM_TYPES, EXTRA_TYPES
from .review import (load_overrides, apply_item_overrides, apply_person_overrides, check_and_report,
                     report_markdown)
from .workbook import write_workbook

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_NAME = "CityTech_Talent_Pool.xlsx"


def source_rows(stats, dept_status, skipped):
    used = sum(1 for _, _, s in dept_status if s == "Used")
    def st(key, name):
        return "Skipped" if name in skipped else ("Used" if stats.get(key) else "Used (0 results)")
    return [
        ("City Tech department directories", "https://www.citytech.cuny.edu/<department>/directory.aspx "
         "(data feed /dashboard/odata/Employees?$filter=Dept_ID eq N)",
         f"Faculty list, titles, offices, emails and bio text, {used} of {len(dept_status)} departments read live",
         "Used" if used else "Cached"),
        ("Faculty bios (Dept bio)", "Bio field of the directory feed",
         f"{stats.get('bio_items', 0)} self-reported publications, presentations, grants and patents", st("bio_items", "bios")),
        ("OpenAlex", "api.openalex.org (institution ROR 021a7pw18)",
         f"{stats.get('openalex_citytech_works', 0)} City Tech-affiliated works; earlier career from matched author profiles",
         st("openalex_citytech_works", "openalex")),
        ("CUNY Academic Works", "academicworks.cuny.edu OAI-PMH, City Tech sets ny_*",
         f"{stats.get('academic_works_records', 0)} repository records", st("academic_works_records", "academicworks")),
        ("ORCID public API", "pub.orcid.org v3.0", f"{stats.get('orcid_items', 0)} works from faculty ORCID records "
         "(only faculty whose ORCID iD is known)", st("orcid_items", "orcid")),
        ("Crossref REST API", "api.crossref.org", "Not queried directly: OpenAlex already includes Crossref DOIs and metadata",
         "Covered by OpenAlex"),
        ("NSF Award Search API", "api.nsf.gov/services/v1/awards", f"{stats.get('nsf_awards', 0)} City Tech awards; "
         "PI / co-PI matched by email", st("nsf_awards", "grants")),
        ("NIH RePORTER API", "api.reporter.nih.gov/v2/projects/search", f"{stats.get('nih_projects', 0)} City Tech projects",
         st("nih_projects", "grants")),
        ("Google Scholar", "scholar.google.com", f"No API and automated access is blocked (CAPTCHA). "
         f"{stats.get('imported_items', 0)} items added from uploaded workbooks (including Scholar collections)",
         "Via uploads"),
    ]


# Earlier-career papers from OpenAlex author profiles that don't list City Tech ("Low").
# Only AI-related ones are worth a person's time (this is an AI talent pool), and a profile with
# hundreds of them almost certainly merges several people who share a name.
MERGED_PROFILE_LIMIT = 150


def limit_unconfirmed(items, roster):
    low = defaultdict(list)
    for it in items:
        if it["confidence"].startswith("Low") and it["sources"] == ["OpenAlex"] and not it.get("review"):
            low[it["person"]].append(it)
    drop, notes = set(), []
    for key, lst in low.items():
        if len(lst) > MERGED_PROFILE_LIMIT:
            drop.update(id(i) for i in lst)
            notes.append(f"{roster.by_key[key]['full_name']}: OpenAlex profile has {len(lst)} papers without City Tech "
                         f"affiliation, probably several people with this name; set aside. Adding their ORCID iD "
                         f"(faculty_extra.csv) fixes this.")
        else:
            drop.update(id(i) for i in lst if not i.get("is_ai"))
    S.STATS["unconfirmed_set_aside"] = len(drop)
    S.STATS["merged_profiles"] = notes
    return [i for i in items if id(i) not in drop], notes


def build_payload(people, faculty, items, tiers, stats, dept_status, generated):
    idx = {p["key"]: i for i, p in enumerate(faculty)}
    shown = [it for it in items if not it["excluded_reason"] and it["person"] in idx]
    fac = []
    for p in faculty:
        t = tiers.get(p["key"], {})
        mine = [i for i in shown if i["person"] == p["key"]]
        fac.append({"key": p["key"], "name": p["full_name"], "last": p["last_name"], "title": p["title"],
                    "department": p["department"], "school": p["school"], "email": p["email"],
                    "profile": p["directory_profile"], "orcid": p["orcid"], "openalex_id": p.get("openalex_id", ""),
                    "tier": t.get("tier", ""), "ai_confirmed": t.get("ai_confirmed", 0), "ai_recent": t.get("ai_recent", 0),
                    "ai_unconfirmed": t.get("ai_unconfirmed", 0), "areas": t.get("ai_areas", []),
                    "n": sum(1 for i in mine if is_confirmed(i)), "n_check": sum(1 for i in mine if not is_confirmed(i))})
    rows = [{"id": it["item_id"], "p": idx[it["person"]], "type": it["item_type"], "title": it["title"],
             "year": it["year"], "venue": it["venue"], "src": it["sources"], "conf": it["confidence"],
             "ok": is_confirmed(it), "rev": it.get("review") == "confirmed", "url": it["url"],
             "role": it["role"], "amount": it["amount"], "ai": bool(it.get("is_ai")),
             "aie": it.get("ai_evidence", "")[:160]} for it in shown]
    conf = [i for i in shown if is_confirmed(i)]
    stats_out = {
        "faculty": len(faculty), "departments": len({p["department"] for p in faculty}),
        "items": len(conf), "items_to_check": len(shown) - len(conf),
        "items_excluded": sum(1 for i in items if i["excluded_reason"]),
        "by_type": dict(Counter(i["item_type"] for i in conf).most_common()),
        "by_source": dict(Counter(s for i in conf for s in i["sources"]).most_common()),
        "ai_items": sum(1 for i in conf if i.get("is_ai")),
        "ai_people": sum(1 for f in fac if f["tier"] and f["tier"] != REVIEW_TIER),
        "citytech_works": stats.get("openalex_citytech_works", 0),
    }
    return {"generated": generated, "repo": os.environ.get("GITHUB_REPOSITORY", ""), "recent_years": RECENT_YEARS, "tiers": [t for t, _, _ in TIERS] + [REVIEW_TIER],
            "types": ITEM_TYPES + EXTRA_TYPES, "schools": sorted({p["school"] for p in faculty if p["school"]}),
            "workbook": f"data/{WORKBOOK_NAME}", "stats": stats_out, "faculty": fac, "items": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default=os.environ.get("CONTACT_EMAIL", ""), help="contact email sent to APIs")
    ap.add_argument("--out", default=str(ROOT / "output"))
    ap.add_argument("--site-dir", default=str(ROOT / "docs"))
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--overrides", default=str(ROOT / "overrides.csv"))
    ap.add_argument("--faculty-extra", default=str(ROOT / "faculty_extra.csv"))
    ap.add_argument("--skip", nargs="*", default=[],
                    choices=["directory", "openalex", "academicworks", "orcid", "grants", "bios"])
    ap.add_argument("--include-adjuncts", action="store_true")
    ap.add_argument("--no-full-career", action="store_true", help="only City Tech-affiliated OpenAlex works")
    ap.add_argument("--force", action="store_true", help="publish even if the safety checks object")
    a = ap.parse_args(argv)
    if a.email:
        SESSION.headers["User-Agent"] = f"CityTechTalentPool/2.0 (mailto:{a.email})"
    out, site, data = Path(a.out), Path(a.site_dir), Path(a.data_dir)
    for d in (out, site / "data", data):
        d.mkdir(parents=True, exist_ok=True)
    generated = time.strftime("%Y-%m-%d")

    # 1. faculty
    people, dept_status = load_directory(data / "faculty_directory.csv", a.faculty_extra,
                                         live="directory" not in a.skip)
    overrides = load_overrides(a.overrides)
    hidden = apply_person_overrides(people, overrides)
    for p in people:
        p["_faculty"] = is_faculty(p, a.include_adjuncts) and p["key"] not in hidden
    faculty = [p for p in people if p["_faculty"]]
    roster = Roster(faculty)
    log(f"Faculty: {len(faculty)} of {len(people)} directory entries ({len(DEPARTMENTS)} departments)")

    # 2. items
    items, unmatched = [], {}
    if "openalex" not in a.skip:
        oa, unmatched = S.harvest_openalex(roster, a.email, full_career=not a.no_full_career)
        items += oa
    if "academicworks" not in a.skip:
        items += S.harvest_academic_works(roster)
    if "orcid" not in a.skip:
        items += S.harvest_orcid(roster)
    if "grants" not in a.skip:
        items += S.harvest_nsf(roster) + S.harvest_nih(roster)
    if "bios" not in a.skip:
        items += S.harvest_bios(roster)
    items += S.load_imported(data / "imported_items.csv", roster)

    # 3-5. merge, AI flag, IDs, review decisions, confidence
    items = merge_items(items)
    tag_items(items)
    ids = ItemIds(data / "item_ids.csv")
    for it in sorted(items, key=lambda i: (str(i["year"]), i["title"])):
        ids.assign(it, roster.by_key[it["person"]]["dept_code"])
    for it in items:
        it["confidence"] = set_confidence(it)
    apply_item_overrides(items, overrides, roster.by_key, is_confirmed)
    for it in items:
        it["confidence"] = set_confidence(it)
    items, set_aside = limit_unconfirmed(items, roster)
    tiers = tier_people(faculty, items, is_confirmed)

    # 6. safety checks
    payload = build_payload(people, faculty, items, tiers, S.STATS, dept_status, generated)
    site_json = site / "data" / "talent_pool.json"
    previous = None
    if site_json.exists():
        try:
            previous = json.loads(site_json.read_text(encoding="utf-8"))
            if "faculty" not in previous:     # data file from the previous (v1) design
                previous = None
        except ValueError:
            previous = None
    ok, rep = check_and_report(payload, previous, overrides, dept_status, S.STATS, a.force)
    md = report_markdown(rep)
    (out / "run_report.md").write_text(md, encoding="utf-8")
    (out / "run_report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    log("\n" + md)
    if not ok:
        log("REFUSED: results look broken compared with last month; nothing was overwritten.")
        sys.exit(2)

    # 7. publish
    write_workbook(site / "data" / WORKBOOK_NAME, people, items,
                   tiers, source_rows(S.STATS, dept_status, a.skip), generated)
    site_json.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    ids.save()
    write_csv(out / "unmatched_authors.csv",
              [{"name": n, **u} for n, u in sorted(unmatched.items(), key=lambda kv: -kv[1]["works"])],
              ["name", "works", "orcid", "openalex_id"])
    log(f"Published {payload['stats']['items']} items for {len(faculty)} faculty.")
    return payload


if __name__ == "__main__":
    main()
