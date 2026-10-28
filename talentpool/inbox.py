"""Processes files uploaded to the inbox/ folder (the dashboard's Upload button).  Run:
    python -m talentpool.inbox

Accepted files
  * Our own workbook, edited: Check column (Confirmed / Not theirs / Not AI / Is AI), corrected
    cells, and new rows with an empty ItemID. Becomes rows in overrides.csv and imported_items.csv.
  * Any workbook in the CUNY template format, e.g. a department's Google Scholar collection.
    Its items are added (duplicates merge automatically); its Faculty sheet fills ORCID and
    Google Scholar columns.
  * A CSV faculty list (name, email, department, title, ...): adds or corrects people
    in faculty_extra.csv.
Processed files move to inbox/processed/ so nothing is applied twice.
"""
import os
import re
import shutil
import sys
import time
from pathlib import Path

from .common import log, read_csv, write_csv, norm_orcid, name_key
from .directory import load_directory, EXTRA_FIELDS, person_key, Roster
from .review import OVERRIDE_FIELDS, append_overrides
from .sources import IMPORT_FIELDS
from .workbook import read_workbook, EDITABLE

ROOT = Path(__file__).resolve().parents[1]
CHECK_ACTIONS = {"confirmed": "confirm", "✓": "confirm", "yes": "confirm", "y": "confirm", "x": "confirm",
                 "not theirs": "not_theirs", "not mine": "not_theirs", "no": "not_theirs", "✗": "not_theirs",
                 "not ai": "not_ai", "is ai": "is_ai"}


def _s(v):
    return "" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)).strip()


def _find_person(row, roster, people_by_key):
    email = _s(row.get("Email")).lower()
    if email and email in people_by_key:
        return people_by_key[email]
    p, _ = roster.match(_s(row.get("FullName")) or f"{_s(row.get('FirstName'))} {_s(row.get('LastName'))}", email=email)
    return p


def process_workbook(path, roster, people_by_key, current, who, today):
    wb = read_workbook(path)
    ours = any("Check" in r for r in wb.get("Items", [])[:1]) or "Items To Check" in wb
    overrides, imports, extras, skipped = [], [], [], 0
    for sheet in ("Items", "Items To Check"):
        for r in wb.get(sheet, []):
            iid = _s(r.get("ItemID"))
            reviewer = _s(r.get("Reviewed by")) or who
            if ours and iid in current:
                cur = current[iid]
                act = CHECK_ACTIONS.get(_s(r.get("Check")).lower())
                if act and not (act == "confirm" and _s(cur.get("Check")).lower() == "confirmed"):
                    overrides.append({"action": act, "item": iid, "reviewed_by": reviewer, "date": today,
                                      "note": _s(r.get("Correction notes"))})
                for col in EDITABLE:
                    new, old = _s(r.get(col)), _s(cur.get(col))
                    if new != old and new:
                        overrides.append({"action": "set", "item": iid, "field": col, "value": new,
                                          "reviewed_by": reviewer, "date": today, "note": f"was: {old}"[:200]})
                continue
            if not _s(r.get("ItemTitle")):
                skipped += 1
                continue
            p = _find_person(r, roster, people_by_key)
            if not p:
                skipped += 1
                continue
            row = {f: _s(r.get(f)) for f in IMPORT_FIELDS if f in r}
            row.update({"person": p["key"], "added_by": reviewer, "added_on": today})
            if not row.get("Sources"):
                row["Sources"] = "Manual"
            imports.append(row)
    for r in wb.get("Faculty", []):
        p = _find_person(r, roster, people_by_key)
        if not p:
            continue
        orcid = norm_orcid(_s(r.get("ORCID")))
        note = _s(r.get("Notes"))
        x = {"email": p["email"], "full_name": p["full_name"],
             "orcid": orcid if orcid and ("not confirmed" not in (_s(r.get("ORCID")) + note).lower()) else "",
             "scholar_profile": _s(r.get("ScholarProfile")), "scholar_interests": _s(r.get("ScholarInterests")),
             "scholar_total_pubs": _s(r.get("TotalPubs")), "scholar_citations": _s(r.get("Citations")),
             "hindex": _s(r.get("Hindex")), "iindex": _s(r.get("Iindex")),
             "scholar_checked_on": _s(r.get("ScholarCheckedOn")), "notes": note if not ours else "",
             "updated_by": who, "updated_on": today}
        if any(x[k] for k in EXTRA_FIELDS[3:15] if k in x):
            extras.append(x)
    return overrides, imports, extras, skipped, ("our workbook" if ours else "template workbook")


def process_faculty_csv(path, who, today):
    rows = []
    for r in read_csv(path):
        low = {k.lower().strip(): v for k, v in r.items()}
        name = low.get("full_name") or low.get("fullname") or low.get("name") or \
            f"{low.get('firstname', low.get('first_name', ''))} {low.get('lastname', low.get('last_name', ''))}".strip()
        if not name:
            continue
        rows.append({"email": low.get("email", ""), "full_name": name, "aka": low.get("aka", ""),
                     "orcid": low.get("orcid", ""), "department": low.get("department", ""),
                     "title": low.get("title", ""), "status": low.get("status", ""), "notes": low.get("notes", ""),
                     "updated_by": who, "updated_on": today})
    return rows


def upsert_extras(path, new):
    rows = read_csv(path)
    by = {person_key(r.get("email"), r.get("full_name")): r for r in rows}
    for x in new:
        k = person_key(x.get("email"), x.get("full_name"))
        cur = by.get(k)
        if cur:
            cur.update({f: v for f, v in x.items() if v})
        else:
            by[k] = x
            rows.append(x)
    write_csv(path, rows, EXTRA_FIELDS)


def main(inbox=None, data_dir=None, overrides_path=None, extra_path=None, workbook=None):
    inbox = Path(inbox or ROOT / "inbox")
    data_dir = Path(data_dir or ROOT / "data")
    overrides_path = overrides_path or ROOT / "overrides.csv"
    extra_path = extra_path or ROOT / "faculty_extra.csv"
    workbook = Path(workbook or ROOT / "docs" / "data" / "CityTech_Talent_Pool.xlsx")
    files = [f for f in sorted(inbox.glob("*")) if f.is_file() and f.suffix.lower() in (".xlsx", ".csv")]
    if not files:
        log("Inbox is empty.")
        return []
    who = os.environ.get("GITHUB_ACTOR", "uploader")
    today = time.strftime("%Y-%m-%d")
    people, _ = load_directory(data_dir / "faculty_directory.csv", extra_path, live=False)
    roster = Roster(people)
    by_key = {p["key"]: p for p in people}
    current = {}
    if workbook.exists():
        wb = read_workbook(workbook)
        for sheet in ("Items", "Items To Check"):
            current.update({_s(r.get("ItemID")): r for r in wb.get(sheet, [])})
    summary = []
    for f in files:
        if f.suffix.lower() == ".xlsx":
            ov, imp, ext, skipped, kind = process_workbook(f, roster, by_key, current, who, today)
            append_overrides(overrides_path, ov)
            old = read_csv(data_dir / "imported_items.csv")
            write_csv(data_dir / "imported_items.csv", old + imp, IMPORT_FIELDS)
            upsert_extras(extra_path, ext)
            msg = (f"{f.name} ({kind}): {len(ov)} review decisions, {len(imp)} items added, "
                   f"{len(ext)} faculty updates, {skipped} rows skipped (no title, or person not found)")
        else:
            ext = process_faculty_csv(f, who, today)
            upsert_extras(extra_path, ext)
            msg = f"{f.name} (faculty list): {len(ext)} people added or updated"
        log(msg)
        summary.append(msg)
        dest = inbox / "processed" / f"{today}_{f.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
    return summary


if __name__ == "__main__":
    for line in main():
        print(line)
