"""Who the faculty are: read from City Tech's own department directories each month.

Each department's directory page (e.g. /physics/directory.aspx) names its department ID(s),
and the page loads its people from /dashboard/odata/Employees filtered by that ID. We make
the same request the page makes, once per department, and keep only the fields we need
(no phone numbers or photos).

Manual additions live in faculty_extra.csv (other names people publish under, ORCID iDs,
corrections) and are merged in on every run. If the directory can't be read, last month's
copy (data/faculty_directory.csv) is used so a website outage never empties the list.
"""
import os
import re
import time
from pathlib import Path

from .common import SESSION, log, norm_name, name_key, norm_orcid, read_csv, write_csv, REQUEST_FAILURES

SITE = "https://www.citytech.cuny.edu"
COLLEGE = "NYC College of Technology"

# slug on citytech.cuny.edu, department name, ItemID code, school (from /academics/academic-departments.aspx)
DEPARTMENTS = [
    ("african-studies", "African American Studies", "AAS", "School of Arts & Sciences"),
    ("biological", "Biological Sciences", "BIO", "School of Arts & Sciences"),
    ("chemistry", "Chemistry", "CHEM", "School of Arts & Sciences"),
    ("english", "English", "ENG", "School of Arts & Sciences"),
    ("humanities", "Humanities", "HUM", "School of Arts & Sciences"),
    ("mathematics", "Mathematics", "MATH", "School of Arts & Sciences"),
    ("physics", "Physics", "PHYS", "School of Arts & Sciences"),
    ("socialscience", "Social Science", "SOC", "School of Arts & Sciences"),
    ("architecture", "Architectural Technology", "ARCH", "School of Technology & Design"),
    ("communication-design", "Communication Design", "COMD", "School of Technology & Design"),
    ("computer-engineering", "Computer Engineering Technology", "CET", "School of Technology & Design"),
    ("computer-systems", "Computer Systems Technology", "CST", "School of Technology & Design"),
    ("construction-engineering", "Construction Management and Civil Engineering Technology", "CMCE", "School of Technology & Design"),
    ("electrical-telecomm", "Electrical and Telecommunications Engineering Technology", "EET", "School of Technology & Design"),
    ("entertainment", "Entertainment Technology", "ENT", "School of Technology & Design"),
    ("environmental", "Environmental Control Technology", "ECT", "School of Technology & Design"),
    ("mechanical", "Mechanical Engineering Technology", "MECH", "School of Technology & Design"),
    ("business", "Business", "BUS", "School of Professional Studies"),
    ("teacher-education", "Career and Technology Teacher Education", "CTE", "School of Professional Studies"),
    ("dental", "Dental Hygiene", "DEN", "School of Professional Studies"),
    ("health-sciences", "Health Sciences", "HSA", "School of Professional Studies"),
    ("human-services", "Human Services", "HUS", "School of Professional Studies"),
    ("hospitality", "Hospitality Management", "HMGT", "School of Professional Studies"),
    ("law-paralegal", "Law and Paralegal Studies", "LAW", "School of Professional Studies"),
    ("nursing", "Nursing", "NUR", "School of Professional Studies"),
    ("radiologic", "Radiologic Technology and Medical Imaging", "RAD", "School of Professional Studies"),
    ("restorativedentistry", "Restorative Dentistry", "RESD", "School of Professional Studies"),
    ("library", "Library", "LIB", "Library"),
]
DEPT_BY_NAME = {d[1].lower(): d for d in DEPARTMENTS}
KEEP_FIELDS = ("First_name", "Middle_initial", "Last_name", "Title", "Email", "Room_number", "Bio", "Discipline")

# Titles the college's own directory script uses to sort people (from /js/faculty.js), plus
# patterns for the variants seen in practice.
ADJUNCT_RE = re.compile(r"\badj(unct)?\b|\bpart[- ]time\b", re.I)
STAFF_RE = re.compile(r"\bCLT\b|lab(oratory)? tech|office assistant|administrat|secretary|coordinator|"
                      r"director|manager|specialist|assistant to|clerk|technician|advisor|counselor", re.I)
FACULTY_RE = re.compile(r"professor|lecturer|instructor|chair|librarian", re.I)
FIELDS = ["key", "full_name", "first_name", "last_name", "middle", "title", "status", "department",
          "dept_code", "school", "college", "email", "office", "directory_profile", "orcid", "aka",
          "discipline", "source", "bio"]


def classify_status(title):
    t = re.sub(r"\s+", " ", title or "").strip()
    if ADJUNCT_RE.search(t):
        return "Adjunct (lab staff)" if STAFF_RE.search(t) else "Adjunct"
    if FACULTY_RE.search(t) and not re.search(r"assistant to|office", t, re.I):
        return "Full-time (substitute)" if re.search(r"\bsub(stitute)?\b", t, re.I) else "Full-time"
    return "Staff"


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\t", " ")).strip()


def person_key(email, full_name):
    return (email or "").strip().lower() or "name:" + " ".join(norm_name(full_name))


def dept_ids(slug):
    for page in ("directory.aspx", "faculty.aspx"):
        try:
            r = SESSION.get(f"{SITE}/{slug}/{page}", timeout=60)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {slug}/{page}: {e}")
            continue
        if r.status_code == 200:
            m = re.search(r"Dept_IDs\s*=\s*\[([\d,\s]+)\]", r.text)
            if m:
                return [int(x) for x in m.group(1).split(",") if x.strip()]
    return []


def fetch_department(slug, name, code, school):
    ids = dept_ids(slug)
    people, answered = [], False
    for did in ids:
        try:
            r = SESSION.get(f"{SITE}/dashboard/odata/Employees",
                            params={"$filter": f"Dept_ID eq {did}", "$orderby": "Last_name"}, timeout=60)
            r.raise_for_status()
            data = r.json()
            answered = True
        except Exception as e:  # noqa: BLE001
            log(f"  ! directory feed for {name} ({did}): {e}")
            REQUEST_FAILURES["www.citytech.cuny.edu"] += 1
            continue
        for e in (data.get("value") if isinstance(data, dict) else data) or []:
            e = {k: e.get(k) for k in KEEP_FIELDS}
            first, last = _clean(e["First_name"]), _clean(e["Last_name"])
            if not (first or last):
                continue
            full = f"{first} {last}".strip()
            email = _clean(e["Email"])
            title = _clean(e["Title"])
            people.append({
                "key": person_key(email, full), "full_name": full, "first_name": first, "last_name": last,
                "middle": _clean(e["Middle_initial"]), "title": title, "status": classify_status(title),
                "department": name, "dept_code": code, "school": school, "college": COLLEGE,
                "email": email, "office": _clean(e["Room_number"]),
                "directory_profile": f"{SITE}/faculty/{email.split('@')[0].lower()}" if email else "",
                "orcid": "", "aka": "", "discipline": _clean(e["Discipline"]),
                "source": "City Tech directory", "bio": e["Bio"] or "",
            })
        time.sleep(0 if os.environ.get("TALENTPOOL_TEST") else 0.3)
    return ids, people, answered


def load_directory(cache_path, extra_path, live=True):
    """Returns (people, department_status). people = everyone in the directories (all statuses)."""
    cached = {}
    for r in read_csv(cache_path):
        cached.setdefault(r["department"], []).append(r)
    seen_path = Path(cache_path).with_name("directory_departments.txt")
    answered_before = set(seen_path.read_text().splitlines()) if seen_path.exists() else set()
    answered_now = set()
    people, status = [], []
    for slug, name, code, school in DEPARTMENTS:
        got, ids, answered = [], [], False
        if live:
            ids, got, answered = fetch_department(slug, name, code, school)
        if got or (answered and not cached.get(name)):
            answered_now.add(name)
            status.append((name, f"{len(got)} people (directory IDs {ids})", "Used"))
        elif cached.get(name) or name in answered_before:
            got = cached.get(name, [])
            answered_now.add(name)
            status.append((name, f"directory unavailable; used last month's copy ({len(got)} people)", "Cached"))
        else:
            status.append((name, "directory unavailable and no saved copy", "Missing"))
        people += got
    # same person listed in two departments: keep first, note the second
    seen, unique = {}, []
    for p in people:
        if p["key"] in seen:
            continue
        seen[p["key"]] = p
        unique.append(p)
    write_csv(cache_path, unique, FIELDS)
    seen_path.write_text("\n".join(sorted(answered_now)))
    apply_extras(unique, read_csv(extra_path))
    return unique, status


EXTRA_FIELDS = ["email", "full_name", "aka", "orcid", "department", "title", "status", "openalex_id",
                "scholar_profile", "scholar_interests", "scholar_total_pubs", "scholar_citations",
                "hindex", "iindex", "scholar_checked_on", "notes", "updated_by", "updated_on"]


def apply_extras(people, extras):
    """faculty_extra.csv: manual corrections and additions, matched by email (or name)."""
    by_key = {p["key"]: p for p in people}
    for x in extras:
        k = person_key(x.get("email"), x.get("full_name"))
        p = by_key.get(k)
        if not p and x.get("full_name"):
            nk = name_key(x["full_name"])
            p = next((q for q in people if name_key(q["full_name"]) == nk), None)
        if not p:
            if not x.get("full_name"):
                continue
            dept = DEPT_BY_NAME.get((x.get("department") or "").lower())
            p = {"key": k, "full_name": x["full_name"], "first_name": x["full_name"].split()[0],
                 "last_name": x["full_name"].split()[-1], "middle": "", "title": x.get("title", ""),
                 "status": x.get("status") or "Full-time", "department": x.get("department", ""),
                 "dept_code": dept[2] if dept else "OTH", "school": dept[3] if dept else "",
                 "college": COLLEGE, "email": x.get("email", ""), "office": "", "directory_profile": "",
                 "orcid": "", "aka": "", "discipline": "", "source": "faculty_extra.csv", "bio": ""}
            people.append(p)
            by_key[k] = p
        for f in ("aka", "title", "status"):
            if x.get(f):
                p[f] = x[f]
        if x.get("orcid"):
            p["orcid"] = norm_orcid(x["orcid"])
        if x.get("department"):
            dept = DEPT_BY_NAME.get(x["department"].lower())
            p["department"] = x["department"]
            if dept:
                p["dept_code"], p["school"] = dept[2], dept[3]
        for f in EXTRA_FIELDS[7:]:
            if x.get(f):
                p[f] = x[f]
    return people


def is_faculty(p, include_adjuncts=False):
    return p["status"].startswith("Full-time") or (include_adjuncts and p["status"] == "Adjunct")


class Roster:
    """Matches author names / ORCID / email on papers and grants to faculty."""

    def __init__(self, people):
        self.people = people
        self.by_key, self.by_orcid, self.by_email, self.by_openalex = {}, {}, {}, {}
        self.by_name = {}
        for p in people:
            p.setdefault("name", p["full_name"])
            self.by_key[p["key"]] = p
            if p.get("orcid"):
                self.by_orcid[p["orcid"]] = p
            if p.get("email"):
                self.by_email[p["email"].lower()] = p
            if p.get("openalex_id"):
                self.by_openalex[p["openalex_id"].upper()] = p
            names = [p["full_name"]] + [a for a in (p.get("aka") or "").split(";") if a.strip()]
            if p.get("middle"):
                names.append(f"{p['first_name']} {p['middle']} {p['last_name']}")
            for nm in names:
                k = name_key(nm)
                if k:
                    lst = self.by_name.setdefault(k, [])
                    if p not in lst:
                        lst.append(p)

    def match(self, name=None, orcid=None, openalex_id=None, email=None):
        if email and email.lower() in self.by_email:
            return self.by_email[email.lower()], "email"
        if openalex_id and openalex_id.upper() in self.by_openalex:
            return self.by_openalex[openalex_id.upper()], "openalex_id"
        if orcid and norm_orcid(orcid) in self.by_orcid:
            return self.by_orcid[norm_orcid(orcid)], "orcid"
        cands = self.by_name.get(name_key(name), [])
        if len(cands) == 1:
            return cands[0], "name"
        if len(cands) > 1:                         # ambiguous: require the full first name
            first = (norm_name(name) or [""])[0]
            exact = [c for c in cands if (norm_name(c["full_name"]) or [""])[0] == first]
            if len(exact) == 1:
                return exact[0], "name"
        return None, None
