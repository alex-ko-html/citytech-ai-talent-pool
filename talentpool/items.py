"""One "item" = one publication, presentation, grant or patent belonging to one faculty member.

Every source (OpenAlex, CUNY Academic Works, ORCID, NSF, NIH, faculty bios, uploaded workbooks)
produces items in the same shape. They're merged per person (same DOI or same title = same item),
sorted into a type, given a confidence, and given a permanent ItemID like CET-0014.
"""
import re
from collections import defaultdict

from .common import norm_doi, norm_title, similar_titles, read_csv, write_csv

# The template's types first (these get their own count columns on the Faculty sheet), then extras.
ITEM_TYPES = ["Journal article", "Conference paper", "Book", "Book chapter", "Conference presentation",
              "Technical report", "Paper (venue type unclear)", "Patent", "Grant"]
EXTRA_TYPES = ["Preprint", "Dataset", "Dissertation", "Open educational resource", "Other"]

# OpenAlex record types that aren't research items: listed on "Items Excluded" instead.
NOT_RESEARCH = {"paratext", "erratum", "retraction", "supplementary-materials", "libguides",
                "peer-review", "grant"}

# Rank decides whose metadata wins when sources disagree (lower = preferred).
SOURCE_RANK = {"OpenAlex": 0, "CUNY Academic Works": 1, "ORCID": 2, "NSF": 3, "NIH": 4,
               "Dept bio": 5, "Google Scholar": 6, "Crossref": 7, "Manual": 8}
HIGH_SOURCES = {"CUNY Academic Works": "in CUNY Academic Works", "ORCID": "on their own ORCID record",
                "NSF": "NSF award to City Tech", "NIH": "NIH award to City Tech"}


CONFERENCE_VENUE = re.compile(r"\bproceedings?\b|\bconference\b|\bsymposium\b|\bworkshop\b|\bexposition\b|"
                              r"\bcongress\b|\bmeeting\b|\bSPIE\b|\bIEEE\b.*\b(conf|symp)", re.I)


def _by_venue(st, venue):
    if st == "conference" or CONFERENCE_VENUE.search(venue or ""):
        return "Conference paper"
    if st == "journal":
        return "Journal article"
    return "Paper (venue type unclear)"


def type_from_openalex(work_type, source_type="", venue=""):
    t, st = (work_type or "").lower(), (source_type or "").lower()
    if t in NOT_RESEARCH:
        return None
    if t in ("article", "other", ""):            # OpenAlex files many proceedings papers as "other"
        return _by_venue(st, venue)
    return {"book-chapter": "Book chapter", "book": "Book", "monograph": "Book", "report": "Technical report",
            "preprint": "Preprint", "dataset": "Dataset", "dissertation": "Dissertation",
            "review": "Journal article", "letter": "Journal article", "editorial": "Other",
            "standard": "Technical report", "reference-entry": "Book chapter",
            "conference-paper": "Conference paper", "proceedings-article": "Conference paper",
            "conference-abstract": "Conference presentation", "poster": "Conference presentation",
            "presentation": "Conference presentation", "patent": "Patent",
            "book-section": "Book chapter", "book-part": "Book chapter"}.get(t) or _by_venue(st, venue)


def type_from_text(*texts):
    """For repository records, bio headings and uploads: sort by the words used."""
    s = " ".join(t or "" for t in texts).lower()
    rules = [
        (r"\bpatent", "Patent"), (r"\bgrants?\b|\baward\b|\bfunded\b|\bfunding\b", "Grant"),
        (r"present|poster|talk|keynote|invited|panel|seminar|webinar", "Conference presentation"),
        (r"proceeding|conference paper|conference", "Conference paper"),
        (r"book chapter|chapter", "Book chapter"), (r"\bbooks?\b|monograph", "Book"),
        (r"technical report|\breport\b|white paper", "Technical report"),
        (r"oer|open educational|textbook|course material|ny_oers", "Open educational resource"),
        (r"thesis|dissertation", "Dissertation"), (r"preprint|arxiv", "Preprint"),
        (r"dataset|data set", "Dataset"), (r"journal|article|peer[- ]reviewed", "Journal article"),
    ]
    for rx, t in rules:
        if re.search(rx, s):
            return t
    return "Paper (venue type unclear)"


def new_item(person, source, **kw):
    it = {
        "person": person, "item_type": "", "title": "", "year": "", "date": "", "venue": "",
        "authors": "", "role": "", "amount": "", "award_id": "", "doi": "", "url": "",
        "sources": [source], "verified": False, "confidence": "", "scholar_citations": "",
        "citations": "", "citation_as_listed": "", "abstract": "", "abstract_source": "",
        "fulltext_url": "", "fulltext_type": "", "oa_status": "", "openalex_id": "",
        "topics": [], "keywords": "", "excluded_reason": "", "item_id": "", "review": "",
    }
    it.update({k: v for k, v in kw.items() if v not in (None,)})
    it["doi"] = norm_doi(it["doi"])
    it["title"] = re.sub(r"\s+", " ", it["title"] or "").strip()
    if it["year"] and not str(it["year"]).isdigit():
        m = re.search(r"(19|20)\d\d", str(it["year"]))
        it["year"] = int(m.group(0)) if m else ""
    elif it["year"]:
        it["year"] = int(it["year"])
    return it


def _absorb(a, b):
    """Merge item b into item a (same person, same work)."""
    if SOURCE_RANK.get(b["sources"][0], 9) < SOURCE_RANK.get(a["sources"][0], 9):
        keep = dict(a)
        a.update({k: v for k, v in b.items() if v not in ("", [], None)})
        for k, v in keep.items():
            if a.get(k) in ("", [], None) and v not in ("", [], None):
                a[k] = v
        a["sources"] = keep["sources"]
    else:
        for k, v in b.items():
            if a.get(k) in ("", [], None) and v not in ("", [], None):
                a[k] = v
    for s in b["sources"]:
        if s not in a["sources"]:
            a["sources"].append(s)
    a["verified"] = a["verified"] or b["verified"]
    if b.get("citation_as_listed") and not a.get("citation_as_listed"):
        a["citation_as_listed"] = b["citation_as_listed"]
    if b.get("scholar_citations") not in ("", None):
        a["scholar_citations"] = b["scholar_citations"]
    if b.get("confidence") and not a.get("confidence"):
        a["confidence"] = b["confidence"]


def merge_items(items):
    """Same person + (same DOI, award ID or title) = one item. Hand-typed citations (bios,
    uploads) are matched by fuzzy title as well."""
    by_person = defaultdict(list)
    for it in items:
        if it["title"] or it["award_id"]:
            by_person[it["person"]].append(it)
    out = []
    for person, lst in by_person.items():
        lst.sort(key=lambda i: SOURCE_RANK.get(i["sources"][0], 9))
        kept, index = [], {}
        for it in lst:
            keys = [("doi", it["doi"])] if it["doi"] else []
            if it["award_id"]:
                keys.append(("award", re.sub(r"\W", "", it["award_id"]).upper()))
            keys.append(("title", norm_title(it["title"])[:150]))
            hit = next((index[k] for k in keys if k[1] and k in index), None)
            if hit is None and it["sources"][0] in ("Dept bio", "Google Scholar", "Manual", "Crossref"):
                hit = next((k for k in kept if (not it["year"] or not k["year"] or abs(int(k["year"]) - int(it["year"])) <= 1)
                            and similar_titles(k["title"], it["title"])), None)
            if hit is None:
                kept.append(it)
                hit = it
            else:
                _absorb(hit, it)
            for k in keys:
                if k[1]:
                    index[k] = hit
        out += kept
    return out


def set_confidence(it):
    """High / Medium / Low, with the reason in brackets (the template's convention)."""
    if it.get("review") == "confirmed":
        return "High (confirmed by reviewer)"
    if it["verified"] and "OpenAlex" in it["sources"]:
        reason = "City Tech affiliation on paper"
    else:
        reason = next((HIGH_SOURCES[s] for s in it["sources"] if s in HIGH_SOURCES), "")
    if reason:
        return f"High ({reason})" + (f"; {len(it['sources'])} sources" if len(it["sources"]) > 1 else "")
    if it.get("confidence") and not (len(it["sources"]) > 1 and it["confidence"].startswith("Low")):
        return it["confidence"]                   # supplied by the source (bio, uploaded workbook)
    if len(it["sources"]) > 1:
        return "High (found in " + " and ".join(it["sources"]) + ")"
    if it["sources"] == ["Google Scholar"]:
        return "Medium (Google Scholar profile listing City Tech)"
    return "Low (same-name author profile; no City Tech affiliation on the paper)"


def is_confirmed(it):
    return it["confidence"].startswith(("High", "Medium"))


class ItemIds:
    """Permanent IDs (DEPT-0001). Stored in data/item_ids.csv so a reviewer's tick on
    CET-0014 still points at the same item next month."""
    FIELDS = ["item_id", "person", "doi", "title_key", "award_id"]

    def __init__(self, path):
        self.path = path
        self.rows = read_csv(path)
        self.by = {}
        self.next = defaultdict(int)
        for r in self.rows:
            self._index(r)

    def _index(self, r):
        for k in (("doi", r["doi"]), ("award", r["award_id"]), ("title", r["title_key"])):
            if k[1]:
                self.by[(r["person"],) + k] = r["item_id"]
        code, _, n = r["item_id"].rpartition("-")
        if n.isdigit():
            self.next[code] = max(self.next[code], int(n))

    def assign(self, it, dept_code):
        keys = [("doi", it["doi"]), ("award", re.sub(r"\W", "", it["award_id"]).upper()),
                ("title", norm_title(it["title"])[:150])]
        for k in keys:
            if k[1] and (it["person"],) + k in self.by:
                it["item_id"] = self.by[(it["person"],) + k]
                return it["item_id"]
        code = dept_code or "OTH"
        self.next[code] += 1
        r = {"item_id": f"{code}-{self.next[code]:04d}", "person": it["person"], "doi": keys[0][1],
             "award_id": keys[1][1], "title_key": keys[2][1]}
        self.rows.append(r)
        self._index(r)
        it["item_id"] = r["item_id"]
        return it["item_id"]

    def save(self):
        write_csv(self.path, self.rows, self.FIELDS)
