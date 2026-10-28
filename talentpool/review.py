"""Human decisions (overrides.csv), safety checks before publishing, and the monthly report.

overrides.csv has one decision per row and survives every rebuild:

  action          person         item                        field / value
  confirm         (optional)     CET-0014                                     item is theirs and correct
  not_theirs      Lin Zhou       MATH-0102 or *unverified*                    someone else's item
  not_ai / is_ai  (optional)     CET-0014                                     fix the AI flag
  set             (optional)     CET-0014                    ItemType = Conference paper
  department      Fangyang Shen                              value = Computer Systems Technology
  hide            Some Person                                value = reason

`item` may also be an OpenAlex ID (W123...), a DOI, or an exact title.
Uploading an edited workbook (inbox.py) writes these rows for you.
"""
import re
import time
from collections import defaultdict

from .common import REQUEST_FAILURES, norm_doi, norm_title, read_csv, write_csv
from .workbook import EDITABLE

OVERRIDE_FIELDS = ["action", "person", "item", "field", "value", "reviewed_by", "date", "note"]
ACTIONS = {"confirm", "not_theirs", "not_ai", "is_ai", "set", "department", "hide",
           "confirm_theirs"}            # confirm_theirs = older name for confirm


def load_overrides(path):
    rows = []
    for i, r in enumerate(read_csv(path), start=2):
        a = (r.get("action") or "").strip()
        if not a or a.startswith("#"):
            continue
        if a not in ACTIONS:
            continue
        r["item"] = r.get("item") or r.get("paper", "")
        r["_line"], r["_used"] = i, 0
        rows.append(r)
    return rows


def _person_ok(o, it, people):
    who = (o.get("person") or "").strip().lower()
    if not who or who == "*":
        return True
    p = people[it["person"]]
    return who in (p["key"], p["full_name"].lower(), (p.get("email") or "").lower())


def _item_ok(o, it, confirmed):
    k = (o.get("item") or "").strip()
    if not k:
        return False
    if k.lower() == "*unverified*":
        return not confirmed(it)
    if re.fullmatch(r"[A-Z]{2,5}-\d{4}", k):
        return it["item_id"] == k
    if re.fullmatch(r"W\d+", k, re.I):
        return it["openalex_id"].upper() == k.upper()
    if "/" in k and norm_doi(k) == it["doi"]:
        return True
    return norm_title(k) == norm_title(it["title"])


def apply_item_overrides(items, overrides, people, confirmed):
    for it in items:
        for o in overrides:
            a = o["action"]
            if a in ("department", "hide") or not _person_ok(o, it, people) or not _item_ok(o, it, confirmed):
                continue
            o["_used"] += 1
            it["reviewed_by"] = o.get("reviewed_by", "")
            if a in ("confirm", "confirm_theirs"):
                it["review"] = "confirmed"
                it["verified"] = True
            elif a == "not_theirs":
                it["excluded_reason"] = "Not theirs (reviewer" + (f": {o['reviewed_by']}" if o.get("reviewed_by") else "") + ")"
            elif a == "not_ai":
                it["is_ai"], it["ai_themes"], it["ai_evidence"] = False, "", "marked not AI by reviewer"
            elif a == "is_ai":
                it["is_ai"] = True
                it["ai_themes"] = it.get("ai_themes") or "AI (general)"
                it["ai_evidence"] = "confirmed AI by reviewer"
            elif a == "set" and o.get("field") in EDITABLE:
                key = EDITABLE[o["field"]]
                it[key] = int(o["value"]) if key == "year" and str(o["value"]).isdigit() else o.get("value", "")


def apply_person_overrides(people, overrides):
    hidden = set()
    for o in overrides:
        who = (o.get("person") or "").strip().lower()
        for p in people:
            if who in (p["key"], p["full_name"].lower()):
                o["_used"] += 1
                if o["action"] == "hide":
                    hidden.add(p["key"])
                elif o["action"] == "department":
                    p["department"] = o.get("value", p["department"])
    return hidden


def append_overrides(path, new_rows):
    rows = read_csv(path)
    write_csv(path, rows + new_rows, OVERRIDE_FIELDS)


# ----------------------------------------------------------------------------- safety checks + report

GUARD_MIN_ITEMS_RATIO = 0.7     # confirmed items must be >= 70% of last month's
GUARD_MIN_FACULTY_RATIO = 0.8   # faculty in the directory must be >= 80% of last month's


def check_and_report(payload, previous, overrides, dept_status, stats, force=False):
    s = payload["stats"]
    problems, warnings = [], []
    if not s["faculty"]:
        problems.append("No faculty found: the directories couldn't be read and there's no saved copy.")
    missing = sum(1 for _, _, st in dept_status if st == "Missing")
    if missing > len(dept_status) / 2:
        problems.append(f"{missing} of {len(dept_status)} department directories couldn't be read.")
    if not stats.get("openalex_citytech_works"):
        problems.append("OpenAlex returned no City Tech papers (outage, or the daily quota/API key).")
    if previous:
        ps = previous.get("stats", {})
        if ps.get("items") and s["items"] < GUARD_MIN_ITEMS_RATIO * ps["items"]:
            problems.append(f"Confirmed items dropped from {ps['items']} to {s['items']}.")
        if ps.get("faculty") and s["faculty"] < GUARD_MIN_FACULTY_RATIO * ps["faculty"]:
            problems.append(f"Faculty dropped from {ps['faculty']} to {s['faculty']} (directory problem?).")
    for name, msg, st in dept_status:
        if st != "Used":
            warnings.append(f"Directory, {name}: {msg}.")
    for host, n in sorted(REQUEST_FAILURES.items()):
        warnings.append(f"{n} failed requests to {host}.")
    for o in overrides:
        if not o["_used"]:
            warnings.append(f"overrides.csv line {o['_line']} ({o['action']} {o.get('person','')} "
                            f"{o.get('item') or o.get('value','')}) matched nothing this month.")
    before = {p["key"]: p for p in (previous or {}).get("faculty", [])}
    new_tier, changed = [], []
    for p in payload["faculty"]:
        b = before.get(p["key"])
        if p["tier"] and (not b or not b.get("tier")):
            new_tier.append((p["name"], p["tier"], p["department"]))
        elif b and b.get("tier") != p["tier"]:
            changed.append((p["name"], b.get("tier") or "none", p["tier"] or "none"))
    new_faculty = [p["name"] + f" ({p['department']})" for p in payload["faculty"] if before and p["key"] not in before]
    left = [b["name"] for k, b in before.items() if k not in {p["key"] for p in payload["faculty"]}]
    rep = {
        "date": time.strftime("%Y-%m-%d"), "status": "REFUSED" if problems and not force else "OK",
        "problems": problems, "warnings": warnings, "stats": s, "source_stats": dict(stats),
        "new_ai_people": new_tier, "tier_changes": changed, "new_faculty": new_faculty, "left_directory": left,
        "items_to_check": s.get("items_to_check", 0),
        "attention": bool(problems or new_tier or changed or warnings or new_faculty or left),
    }
    return (not problems or force), rep


def report_markdown(rep):
    s, ss = rep["stats"], rep["source_stats"]
    L = [f"# Talent pool update — {rep['date']}", "", f"**Status: {rep['status']}**", ""]
    if rep["problems"]:
        L += ["## Problems (nothing was overwritten)", *[f"- {x}" for x in rep["problems"]], "",
              "If the change is real, rerun the workflow with **force** ticked.", ""]
    L += ["## Numbers",
          f"- Faculty (full-time, from the directories): {s['faculty']} in {s['departments']} departments",
          f"- Items (High/Medium confidence): {s['items']} · to check: {s['items_to_check']} · excluded: {s['items_excluded']}",
          "- By type: " + ", ".join(f"{k} {v}" for k, v in s["by_type"].items()),
          "- By source: " + ", ".join(f"{k} {v}" for k, v in s["by_source"].items()),
          f"- AI-related items: {s['ai_items']} · people with a tier: {s['ai_people']}",
          f"- OpenAlex City Tech papers scanned: {ss.get('openalex_citytech_works', 0)} · NSF awards: {ss.get('nsf_awards', 0)} · "
          f"NIH projects: {ss.get('nih_projects', 0)} · bio items: {ss.get('bio_items', 0)}", ""]
    def sec(t, xs, f=str):
        if xs:
            L.extend([f"## {t}", *[f"- {f(x)}" for x in xs], ""])
    sec("Newly in the AI talent pool", rep["new_ai_people"], lambda x: f"{x[0]} ({x[2]}): {x[1]}")
    sec("AI tier changes", rep["tier_changes"], lambda x: f"{x[0]}: {x[1]} → {x[2]}")
    sec("New in the directory", rep["new_faculty"])
    sec("No longer in the directory", rep["left_directory"])
    sec("Warnings", rep["warnings"])
    if rep["items_to_check"]:
        L += [f"## {rep['items_to_check']} items to check",
              "Same-name matches without a City Tech affiliation. Open the Excel's *Items To Check* tab, "
              "mark Confirmed or Not theirs, and upload it.", ""]
    L += ["How to act on any of this: MAINTAINING.md → *Monthly review*."]
    return "\n".join(L)
