#!/usr/bin/env python3
"""
City Tech (NYC College of Technology, CUNY) faculty publication harvester.

Pulls publications for City Tech full-time faculty from several open sources,
merges and de-duplicates them, and writes:
    output/publications.csv        one row per (faculty member, publication)
    output/publications.xlsx       same, as a spreadsheet (if openpyxl installed)
    output/faculty_coverage.csv    per-faculty counts by source (find gaps)
    output/unmatched_authors.csv   City Tech-affiliated authors NOT on your roster
    output/dashboard.html          searchable, filterable dashboard (open in a browser)

Sources (all free, no API key needed):
    1. OpenAlex        - every work with a City Tech affiliation (successor to
                         Microsoft Academic; covers Crossref, PubMed, arXiv, repositories)
    2. ORCID           - works listed on each faculty member's ORCID record
    3. CUNY Academic Works - City Tech's institutional repository (OAI-PMH);
                         catches posters, OER, creative work, items without DOIs
    4. Crossref        - DOI metadata for faculty with an ORCID iD

Why a roster file: no public bibliographic source knows who is FULL-TIME.
Get that list from City Tech HR / Faculty Affairs (or the college directory) and
put it in roster.csv with columns:
    name, department[, orcid][, openalex_id]
orcid and openalex_id are optional but sharply improve accuracy.

Usage:
    pip install requests pandas openpyxl
    python citytech_pubs.py --roster roster.csv --email you@citytech.cuny.edu
    python citytech_pubs.py --roster roster.csv --since 2015 --full-career
    python citytech_pubs.py --suggest-roster          # build a starter roster from OpenAlex
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Please install dependencies: pip install requests pandas openpyxl")

CITYTECH_ROR = "021a7pw18"          # ROR id for New York City College of Technology
OPENALEX = "https://api.openalex.org"
ORCID_API = "https://pub.orcid.org/v3.0"
CROSSREF = "https://api.crossref.org"
ACADEMIC_WORKS_OAI = "https://academicworks.cuny.edu/do/oai/"
CITYTECH_AW_PREFIX = "ny_"          # City Tech collections in Academic Works are ny_*

SESSION = requests.Session()
REQUEST_FAILURES = defaultdict(int)       # host -> failed requests (reported in run_report)
CITYTECH_WORKS_SEEN = {}
SITE_DATA_PATH = ""


# ----------------------------------------------------------------------------- helpers

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def get(url, params=None, accept_json=True, tries=4):
    for attempt in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=60,
                            headers={"Accept": "application/json"} if accept_json else {})
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json() if accept_json else r.text
        except requests.RequestException as e:
            if attempt == tries - 1:
                log(f"  ! request failed: {url} ({e})")
                REQUEST_FAILURES[re.sub(r"^https?://([^/]+).*", r"\1", url)] += 1
                return None
            time.sleep(2 ** attempt)
    REQUEST_FAILURES[re.sub(r"^https?://([^/]+).*", r"\1", url)] += 1
    return None


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def norm_name(s):
    s = strip_accents(s).lower()
    s = re.sub(r"\b(dr|prof|professor|phd|ph\.d|jr|sr|ii|iii)\b\.?", " ", s)
    return re.sub(r"[^a-z ]+", " ", s).split()


def name_key(name):
    """(last name, first initial) - tolerant to middle names / initials."""
    if "," in (name or ""):                       # "Last, First"
        last, first = name.split(",", 1)
        parts = norm_name(first) + norm_name(last)
    else:
        parts = norm_name(name)
    if not parts:
        return None
    return (parts[-1], parts[0][0])


def norm_title(t):
    t = strip_accents(html.unescape(t or "")).lower()
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def norm_doi(d):
    if not d:
        return ""
    d = d.strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)


def norm_orcid(o):
    m = re.search(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dx])", (o or "").lower())
    return m.group(1).upper() if m else ""


# ----------------------------------------------------------------------------- roster

class Roster:
    def __init__(self, rows):
        self.people = []
        self.by_key = defaultdict(list)
        self.by_orcid = {}
        self.by_openalex = {}
        for r in rows:
            p = {
                "name": r.get("name", "").strip(),
                "department": (r.get("department") or "").strip(),
                "orcid": norm_orcid(r.get("orcid", "")),
                "openalex_id": (r.get("openalex_id") or "").strip().split("/")[-1],
                "title": (r.get("title") or "").strip(),
                "email": (r.get("email") or "").strip(),
            }
            if not p["name"]:
                continue
            self.people.append(p)
            # "aka" column: other names the person publishes under (maiden name etc.), ";"-separated
            for nm in [p["name"]] + [a for a in (r.get("aka") or "").split(";") if a.strip()]:
                k = name_key(nm)
                if k and p not in self.by_key[k]:
                    self.by_key[k].append(p)
            if p["orcid"]:
                self.by_orcid[p["orcid"]] = p
            if p["openalex_id"]:
                self.by_openalex[p["openalex_id"].upper()] = p

    @classmethod
    def load(cls, path, include_all=False):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = [{(k or "").strip().lower(): v for k, v in r.items()} for r in csv.DictReader(f)]
        # Optional "status" column (e.g. Full-time / Adjunct / Lecturer). If present,
        # keep only full-time rows unless --include-all is passed.
        if rows and "status" in rows[0] and not include_all:
            before = len(rows)
            rows = [r for r in rows if "full" in (r.get("status") or "").lower()]
            log(f"Roster: kept {len(rows)} full-time of {before} rows (status column)")
        return cls(rows)

    def match(self, name=None, orcid=None, openalex_id=None):
        if openalex_id and openalex_id.upper() in self.by_openalex:
            return self.by_openalex[openalex_id.upper()], "openalex_id"
        if orcid and norm_orcid(orcid) in self.by_orcid:
            return self.by_orcid[norm_orcid(orcid)], "orcid"
        k = name_key(name)
        cands = self.by_key.get(k, [])
        if len(cands) == 1:
            return cands[0], "name"
        if len(cands) > 1:                         # ambiguous: require full first name
            first = norm_name(name)[0] if norm_name(name) else ""
            exact = [c for c in cands if norm_name(c["name"])[0] == first]
            if len(exact) == 1:
                return exact[0], "name"
        return None, None


# ----------------------------------------------------------------------------- OpenAlex

def openalex_institution_id(mailto):
    data = get(f"{OPENALEX}/institutions/ror:{CITYTECH_ROR}", {"mailto": mailto})
    if not data:
        sys.exit("Could not resolve City Tech in OpenAlex.")
    inst = data["id"].split("/")[-1]
    log(f"OpenAlex institution: {data.get('display_name')} ({inst}), "
        f"{data.get('works_count', '?')} works")
    return inst


OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "")


def openalex_paged(endpoint, flt, mailto, select=None):
    """Page through results. (Since 2026 OpenAlex needs an API key for cursor paging;
    plain page= paging works without one, up to 10,000 results per query.)"""
    page, seen = 1, 0
    while True:
        params = {"filter": flt, "per-page": 200, "page": page, "mailto": mailto}
        if select:
            params["select"] = select
        if OPENALEX_API_KEY:
            params["api_key"] = OPENALEX_API_KEY
        data = get(f"{OPENALEX}/{endpoint}", params)
        if not data:
            return
        results = data.get("results", [])
        for item in results:
            yield item
        seen += len(results)
        if not results or seen >= data.get("meta", {}).get("count", 0) or seen >= 10000:
            return
        page += 1


def openalex_record(work, person, how, citytech_affil):
    return {
        "faculty_name": person["name"],
        "department": person["department"],
        "title": (work.get("display_name") or work.get("title") or "").strip(),
        "publication_date": work.get("publication_date") or "",
        "year": work.get("publication_year") or "",
        "type": work.get("type") or "",
        "venue": ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
        "doi": norm_doi(work.get("doi")),
        "url": work.get("doi") or work.get("id"),
        "openalex_work_id": (work.get("id") or "").split("/")[-1],
        "citations": work.get("cited_by_count", ""),
        "source": "OpenAlex",
        "match_method": how,
        "citytech_affiliation_on_paper": citytech_affil,
        # used for AI classification (not all written to the CSV)
        "topics": [{"name": t.get("display_name", ""),
                    "subfield": (t.get("subfield") or {}).get("display_name", ""),
                    "score": t.get("score", 0)} for t in (work.get("topics") or [])],
        "keywords": "; ".join(k.get("display_name", "") for k in (work.get("keywords") or [])
                              if (k.get("score") or 0) >= 0.5),
        "abstract": rebuild_abstract(work.get("abstract_inverted_index")),
        "not_on_roster": person.get("not_on_roster", False),
        "openalex_author_id": person.get("openalex_id", ""),
    }


WORK_FIELDS = ("id,doi,display_name,publication_date,publication_year,type,"
               "primary_location,authorships,cited_by_count,topics,keywords,"
               "abstract_inverted_index")


def rebuild_abstract(inv):
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    return " ".join(w for _, w in sorted(pos))


def harvest_openalex(roster, inst, mailto, since, full_career, include_unrostered=True):
    """City Tech-affiliated works for roster faculty (+ optionally City Tech authors who are
    not on the roster yet, e.g. departments whose directory hasn't been added)."""
    records, unmatched = [], defaultdict(lambda: {"works": 0, "orcid": "", "openalex_id": ""})
    flt = f"institutions.id:{inst}"
    if since:
        flt += f",from_publication_date:{since}-01-01"
    log("OpenAlex: fetching all City Tech-affiliated works ...")
    n = 0
    id_counts = defaultdict(lambda: defaultdict(int))     # author id -> person name -> count
    unrostered = {}
    people_by_name = {}
    for w in openalex_paged("works", flt, mailto, WORK_FIELDS):
        n += 1
        done = set()
        for a in w.get("authorships", []):
            insts = [i.get("id", "").split("/")[-1] for i in a.get("institutions", [])]
            if inst not in insts:
                continue
            au = a.get("author") or {}
            aid = (au.get("id") or "").split("/")[-1]
            person, how = roster.match(au.get("display_name"), au.get("orcid"), aid)
            if not person:
                u = unmatched[au.get("display_name") or "?"]
                u["works"] += 1
                u["orcid"] = norm_orcid(au.get("orcid")) or u["orcid"]
                u["openalex_id"] = aid or u["openalex_id"]
                if not include_unrostered:
                    continue
                # one person per (last name, first initial): merges "Yu-Wen Chen" / "Yuwen Chen"
                k = name_key(re.sub(r"[\u2010-\u2015-]", "", au.get("display_name") or "?")) or aid
                person = unrostered.setdefault(k, {
                    "name": au.get("display_name") or "?", "department": "",
                    "orcid": norm_orcid(au.get("orcid")), "openalex_id": aid, "not_on_roster": True})
                how = "citytech_affiliation"
            if person["name"] in done:
                continue
            done.add(person["name"])
            records.append(openalex_record(w, person, how, True))
            if aid and not person.get("not_on_roster"):
                id_counts[aid][person["name"]] += 1
                people_by_name[person["name"]] = person
        if n % 1000 == 0:
            log(f"  {n} works scanned")
    log(f"  {n} works scanned, {len(records)} author-publication links")
    CITYTECH_WORKS_SEEN["n"] = n

    # each OpenAlex author id belongs to the roster person it matched most often
    matched_author_ids = {aid: people_by_name[max(c, key=c.get)] for aid, c in id_counts.items()}
    for oid, person in roster.by_openalex.items():
        matched_author_ids.setdefault(oid, person)

    if full_career and matched_author_ids:
        # Pre-City Tech / non-affiliated work. OpenAlex sometimes merges different people who
        # share a name, so these papers are marked unverified unless the paper itself lists
        # City Tech for this author.
        log(f"OpenAlex: fetching full history for {len(matched_author_ids)} author profiles ...")
        ids = list(matched_author_ids)
        for i in range(0, len(ids), 50):
            grp = ids[i:i + 50]
            f2 = "authorships.author.id:" + "|".join(grp)
            if since:
                f2 += f",from_publication_date:{since}-01-01"
            for w in openalex_paged("works", f2, mailto, WORK_FIELDS):
                done = set()
                for a in w.get("authorships", []):
                    aid = ((a.get("author") or {}).get("id") or "").split("/")[-1]
                    if aid not in grp or aid in done:
                        continue
                    done.add(aid)
                    ct = inst in [x.get("id", "").split("/")[-1] for x in a.get("institutions", [])]
                    if ct:
                        continue                      # already collected above
                    records.append(openalex_record(w, matched_author_ids[aid], "openalex_profile", False))
    return records, unmatched


def suggest_roster(inst, mailto, out):
    """Starter roster: authors OpenAlex currently places at City Tech. Needs human review."""
    log("Building candidate roster from OpenAlex (last known institution = City Tech) ...")
    rows = []
    for a in openalex_paged("authors", f"last_known_institutions.id:{inst}", mailto,
                            "id,display_name,orcid,works_count,topics"):
        topics = ", ".join(t.get("display_name", "") for t in (a.get("topics") or [])[:3])
        rows.append({"name": a["display_name"], "department": "",
                     "orcid": norm_orcid(a.get("orcid")),
                     "openalex_id": a["id"].split("/")[-1],
                     "works_count": a.get("works_count", 0), "top_topics": topics})
    rows.sort(key=lambda r: -r["works_count"])
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"])
        w.writeheader()
        w.writerows(rows)
    log(f"Wrote {len(rows)} candidates to {out}. Fill in departments, delete non-faculty, "
        f"and cross-check against the official full-time faculty list.")


# ----------------------------------------------------------------------------- ORCID

def harvest_orcid(roster, since):
    recs = []
    people = [p for p in roster.people if p["orcid"]]
    log(f"ORCID: {len(people)} faculty with ORCID iDs ...")
    for p in people:
        data = get(f"{ORCID_API}/{p['orcid']}/works")
        if not data:
            continue
        for g in data.get("group", []):
            s = (g.get("work-summary") or [{}])[0]
            title = (((s.get("title") or {}).get("title") or {}).get("value")) or ""
            pd = s.get("publication-date") or {}
            y = ((pd.get("year") or {}).get("value")) or ""
            m = ((pd.get("month") or {}).get("value")) or ""
            d = ((pd.get("day") or {}).get("value")) or ""
            if since and y and int(y) < since:
                continue
            doi = ""
            for eid in ((s.get("external-ids") or {}).get("external-id") or []):
                if eid.get("external-id-type") == "doi":
                    doi = norm_doi(eid.get("external-id-value"))
            recs.append({
                "faculty_name": p["name"], "department": p["department"], "title": title,
                "publication_date": "-".join(x for x in (y, m, d) if x), "year": y,
                "type": (s.get("type") or "").replace("-", " "),
                "venue": ((s.get("journal-title") or {}).get("value")) or "",
                "doi": doi, "url": f"https://doi.org/{doi}" if doi else f"https://orcid.org/{p['orcid']}",
                "citations": "", "source": "ORCID", "match_method": "orcid",
                "citytech_affiliation_on_paper": "",
            })
        time.sleep(0.1)
    log(f"  {len(recs)} records")
    return recs


# ----------------------------------------------------------------------------- Crossref

def harvest_crossref(roster, mailto, since):
    recs = []
    people = [p for p in roster.people if p["orcid"]]
    log(f"Crossref: querying by ORCID for {len(people)} faculty ...")
    for p in people:
        flt = f"orcid:{p['orcid']}"
        if since:
            flt += f",from-pub-date:{since}"
        data = get(f"{CROSSREF}/works", {"filter": flt, "rows": 1000, "mailto": mailto})
        for it in ((data or {}).get("message") or {}).get("items", []):
            parts = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
            parts = [str(x).zfill(2) if i else str(x) for i, x in enumerate(parts) if x]
            recs.append({
                "faculty_name": p["name"], "department": p["department"],
                "title": (it.get("title") or [""])[0],
                "publication_date": "-".join(parts), "year": parts[0] if parts else "",
                "type": (it.get("type") or "").replace("-", " "),
                "venue": (it.get("container-title") or [""])[0],
                "doi": norm_doi(it.get("DOI")), "url": f"https://doi.org/{it.get('DOI')}",
                "citations": it.get("is-referenced-by-count", ""), "source": "Crossref",
                "match_method": "orcid", "citytech_affiliation_on_paper": "",
            })
        time.sleep(0.1)
    log(f"  {len(recs)} records")
    return recs


# ----------------------------------------------------------------------------- CUNY Academic Works

OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/",
          "dc": "http://purl.org/dc/elements/1.1/",
          "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}


def oai_iter(verb, **params):
    params = {"verb": verb, **params}
    while True:
        text = get(ACADEMIC_WORKS_OAI, params, accept_json=False)
        if not text:
            return
        root = ET.fromstring(text.encode("utf-8"))
        yield root
        tok = root.find(".//oai:resumptionToken", OAI_NS)
        if tok is None or not (tok.text or "").strip():
            return
        params = {"verb": verb, "resumptionToken": tok.text.strip()}
        time.sleep(0.5)


def harvest_academic_works(roster, since):
    log("CUNY Academic Works: discovering City Tech collections ...")
    sets = []
    for root in oai_iter("ListSets"):
        for s in root.findall(".//oai:set", OAI_NS):
            spec = s.findtext("oai:setSpec", "", OAI_NS)
            name = s.findtext("oai:setName", "", OAI_NS)
            coll = spec.split(":")[-1]
            if coll.startswith(CITYTECH_AW_PREFIX):
                sets.append((spec, name))
    log(f"  {len(sets)} City Tech collections")
    recs = []
    for spec, name in sets:
        params = {"metadataPrefix": "oai_dc", "set": spec}
        if since:
            params["from"] = f"{since}-01-01"
        for root in oai_iter("ListRecords", **params):
            for rec in root.findall(".//oai:record", OAI_NS):
                md = rec.find(".//oai_dc:dc", OAI_NS)
                if md is None:
                    continue
                title = md.findtext("dc:title", "", OAI_NS)
                date = md.findtext("dc:date", "", OAI_NS)[:10]
                ids = [e.text or "" for e in md.findall("dc:identifier", OAI_NS)]
                url = next((i for i in ids if i.startswith("http")), "")
                doi = next((norm_doi(i) for i in ids if "doi" in i.lower()), "")
                for creator in md.findall("dc:creator", OAI_NS):
                    person, how = roster.match(creator.text)
                    if not person:
                        continue
                    recs.append({
                        "faculty_name": person["name"], "department": person["department"],
                        "title": title, "publication_date": date, "year": date[:4],
                        "type": md.findtext("dc:type", "", OAI_NS), "venue": name,
                        "doi": doi, "url": url, "citations": "",
                        "source": "CUNY Academic Works", "match_method": how,
                        "citytech_affiliation_on_paper": True,
                    })
    log(f"  {len(recs)} records")
    return recs


# ----------------------------------------------------------------------------- merge

SOURCE_RANK = {"OpenAlex": 0, "Crossref": 1, "ORCID": 2, "CUNY Academic Works": 3}


def merge(records, since=None):
    """One row per (faculty, publication). DOI first, then normalized title + year."""
    groups = {}
    for r in records:
        if not r["title"]:
            continue
        if since and str(r["year"]).isdigit() and int(r["year"]) < since:
            continue
        who = r["faculty_name"]
        key = (who, "doi", r["doi"]) if r["doi"] else (who, "t", norm_title(r["title"])[:120])
        # second key so a DOI-less ORCID record merges with its DOI'd twin
        tkey = (who, "t", norm_title(r["title"])[:120])
        g = groups.get(key) or groups.get(tkey)
        if g is None:
            g = {"best": r, "sources": set()}
        else:
            if SOURCE_RANK[r["source"]] < SOURCE_RANK[g["best"]["source"]]:
                keep = g["best"]
                g["best"] = {**r, **{k: v for k, v in keep.items()
                                     if v and not r.get(k) and k != "source"}}
            for k, v in r.items():
                if v and not g["best"].get(k):
                    g["best"][k] = v
            if r.get("citytech_affiliation_on_paper") is True:
                g["best"]["citytech_affiliation_on_paper"] = True
        g["sources"].add(r["source"])
        groups[key] = g
        groups[tkey] = g
    out, seen = [], set()
    for g in groups.values():
        if id(g) in seen:
            continue
        seen.add(id(g))
        row = dict(g["best"])
        row["found_in"] = "; ".join(sorted(g["sources"], key=SOURCE_RANK.get))
        row["n_sources"] = len(g["sources"])
        row.pop("source", None)
        out.append(row)
    out.sort(key=lambda r: (r["department"], r["faculty_name"], str(r["publication_date"])), reverse=False)
    return out


# ----------------------------------------------------------------------------- AI expertise
#
# Calibrated against real City Tech data (Oct 2026). Lessons baked in:
#  * OpenAlex files some non-AI topics under its "Artificial Intelligence" subfield
#    (quantum information, cryptography, logic/type systems, security), so topics only
#    count when the topic NAME itself is about AI.
#  * OpenAlex auto-keywords are noisy, and one passing mention in an abstract proves little
#    ("artificial intelligence" in an essay about Star Wars), so those are weak evidence.
#  * "CNN" is also a news network and "deep learning" is also a teaching philosophy.

AI_TOPIC_RE = re.compile(
    r"\b(neural net|machine learning|deep learning|natural language|language model|topic model|"
    r"text (and document )?classif|text mining|sentiment|speech recogn|speech and dialogue|"
    r"computer vision|image (recogn|classif|segment|retriev)|object detect|face recogn|"
    r"pose and action|action recogn|video surveillance|reinforcement learning|robotic path planning|"
    r"sensor-based localization|social robot|artificial intelligence|explainable|fuzzy|"
    r"evolutionary algorithm|genetic algorithm|swarm|metaheuristic|bayesian (network|model)|"
    r"knowledge (graph|represent)|semantic web|ontologies|data stream mining|data mining|anomaly detect|"
    r"recommender|domain adaptation|few-shot|generative (ai|model|adversarial)|adversarial robustness|"
    r"intelligent tutoring|multi-agent|ai-based|problem solving and planning|cognitive computing|"
    r"machine translation|question answering|chatbot|data classification|radiomics)", re.I)
# Whole-word matching matters: "Neurodegenerative" contains "generative", "Paleontology" and
# "Gerontology" contain "ontology". Robotics counts only where it's about learning, planning or
# perception; robot hardware, mechanics and control are engineering, not AI.
NOT_AI_TOPIC_RE = re.compile(r"quantum|cryptograph|coding theory|error[- ]correct|chaos|"
                             r"cellular automat|psychiatry|security and verification|educational robotics|"
                             r"distributed control|stability and synchronization", re.I)

AI_TERMS = {
    "Machine learning": r"machine[- ]learning|supervised learning|unsupervised learning|"
                        r"random forests?|support vector|gradient boost|xgboost|federated learning",
    "Deep learning / neural networks": r"deep[- ]learning|neural networks?|convolutional neural|\blstm\b|"
                                       r"recurrent neural|transformer models?|autoencoders?|"
                                       r"generative adversarial",
    "Generative AI / LLMs": r"large language models?|\bllms?\b|chatgpt|\bgpt-?\d|generative ai|"
                            r"generative artificial|prompt engineering|foundation models?|diffusion models?",
    "Natural language processing": r"natural language processing|\bnlp\b|sentiment analysis|"
                                   r"text mining|text classification|named entity|speech recognition",
    "Computer vision": r"computer vision|image recognition|object detection|image segmentation|"
                       r"facial recognition|face recognition|image classification|\byolo",
    "Robotics & autonomous systems": r"autonomous (vehicles?|robots?|systems?|driving)|robot learning|"
                                     r"reinforcement learning|\bslam\b|path planning",
    "AI (general)": r"artificial intelligence|intelligent agents?|multi-agent|knowledge graphs?|"
                    r"expert systems?|fuzzy logic|genetic algorithms?|evolutionary algorithms?|"
                    r"data mining|predictive model|pattern recognition",
    "AI in education & ethics": r"ai literacy|ai ethics|responsible ai|algorithmic bias|"
                                r"explainable ai|\bxai\b|ai[- ](assisted|powered|driven|based|aided|enabled)",
}
AI_RE = {k: re.compile(v, re.I) for k, v in AI_TERMS.items()}
AI_ACRONYM = re.compile(r"\bA\.?I\b")            # "AI" in capitals only (not "aid", "Ai Weiwei"...)
EDU_RE = re.compile(r"student|pedagog|classroom|teaching|curricul|educat|learner|high[- ]impact", re.I)

TOPIC_THEME = [(re.compile(p, re.I), t) for p, t in [
    (r"language|text|sentiment|speech|dialogue|translation|question", "Natural language processing"),
    (r"vision|image|object|face|pose|video", "Computer vision"),
    (r"robot|reinforcement|autonomous|planning", "Robotics & autonomous systems"),
    (r"generative|adversarial|language model", "Generative AI / LLMs"),
    (r"neural|deep", "Deep learning / neural networks"),
    (r"machine learning|classification|anomaly|recommender|stream mining|few-shot|domain adapt",
     "Machine learning"),
    (r"explainable|ethic|tutoring", "AI in education & ethics"),
]]

# Expertise tiers, counted on VERIFIED AI papers only ("recent" = within RECENT_YEARS of today).
# Verified = the paper lists City Tech for this person, or it is on their own ORCID record /
# City Tech's repository. Unverified = it only sits on the same OpenAlex author profile.
RECENT_YEARS = 3
TIERS = [  # (name, min verified AI pubs, min recent verified AI pubs)
    ("Core AI expert", 5, 1),
    ("Active in AI", 2, 1),
    ("Some AI work", 1, 0),
]
REVIEW_TIER = "Needs review"     # no verified AI papers, but 2+ unverified ones
UNROSTERED_MIN_PUBS = 4          # not-on-roster authors need this many City Tech papers to show
UNROSTERED_MAX_GAP = 6           # ...and a City Tech paper within this many years


def _theme_of_topic(name):
    return next((t for rx, t in TOPIC_THEME if rx.search(name)), "AI (general)")


def classify_ai(row):
    """Return (is_ai, themes, evidence). Strong evidence alone qualifies; weak needs two."""
    title = row.get("title", "") or ""
    abstract = row.get("abstract", "") or ""
    keywords = row.get("keywords", "") or ""
    strong, weak, themes = [], [], set()
    for t in row.get("topics") or []:
        nm = t.get("name", "")
        if (t.get("score") or 0) >= 0.3 and AI_TOPIC_RE.search(nm) and not NOT_AI_TOPIC_RE.search(nm):
            strong.append(f"OpenAlex topic: {nm}")
            themes.add(_theme_of_topic(nm))
    abs_terms = {}
    for theme, rx in AI_RE.items():
        m = rx.search(title)
        if m:
            strong.append(f"title: {m.group(0).lower()}")
            themes.add(theme)
        m = rx.search(keywords)
        if m and not rx.search(title):
            weak.append(f"keyword: {m.group(0).lower()}")
            themes.add(theme)
        for m in rx.finditer(abstract):
            abs_terms.setdefault(m.group(0).lower(), theme)
    if AI_ACRONYM.search(title):
        strong.append("title: AI")
        themes.add("AI (general)")
    if len(abs_terms) >= 2:
        strong.append("abstract: " + ", ".join(list(abs_terms)[:3]))
        themes.update(abs_terms.values())
    elif abs_terms:
        weak.append("abstract: " + next(iter(abs_terms)))
    evidence = strong + weak
    weak_terms = {w.split(": ", 1)[1] for w in weak}      # same phrase in keywords + abstract = one signal
    is_ai = bool(strong) or len(weak_terms) >= 2
    # "deep learning" as a teaching philosophy, not neural networks
    if is_ai and all("deep learning" in e or "deep-learning" in e for e in evidence) \
            and EDU_RE.search(title + " " + abstract):
        is_ai = False
    if not is_ai:
        return False, [], ""
    themes.discard("")
    return True, sorted(themes), "; ".join(dict.fromkeys(evidence))[:300]


def is_verified(row):
    found = row.get("found_in", "") or row.get("source", "")
    return (row.get("reviewer_verified") is True
            or row.get("citytech_affiliation_on_paper") is True
            or "ORCID" in found or "CUNY Academic Works" in found)


def build_talent_pool(rows, roster):
    """One entry per person with any AI paper. Returns (pool rows for CSV, site people list)."""
    this_year = time.localtime().tm_year
    by_person = defaultdict(list)
    for r in rows:
        by_person[r["faculty_name"]].append(r)
    info = {p["name"]: p for p in roster.people}
    pool, site = [], []
    rank = {t: i for i, (t, _, _) in enumerate(TIERS)}
    rank[REVIEW_TIER] = len(TIERS)
    for name, pubs in by_person.items():
        ai = [p for p in pubs if p["is_ai"]]
        if not ai:
            continue
        ver = [p for p in ai if is_verified(p)]
        unver = [p for p in ai if not is_verified(p)]
        years = [int(p["year"]) for p in ver if str(p["year"]).isdigit()]
        recent = sum(1 for y in years if y >= this_year - RECENT_YEARS + 1)
        tier = next((t for t, n, rc in TIERS if len(ver) >= n and recent >= rc), "")
        if not tier and len(unver) >= 2:
            tier = REVIEW_TIER
        if not tier:
            continue
        p0 = pubs[0]
        if p0.get("not_on_roster"):
            # City Tech authors missing from the roster: keep likely faculty, not one-off student
            # co-authors or people who left long ago.
            ct_years = [int(p["year"]) for p in pubs if str(p["year"]).isdigit()]
            if len(pubs) < UNROSTERED_MIN_PUBS or (ct_years and max(ct_years) < this_year - UNROSTERED_MAX_GAP):
                continue
        theme_counts = defaultdict(int)
        for p in (ver or unver):
            for t in p["ai_themes"].split("; "):
                if t:
                    theme_counts[t] += 1
        areas = [t for t, _ in sorted(theme_counts.items(), key=lambda kv: -kv[1])]
        p0 = pubs[0]
        person = info.get(name, {})
        not_on_roster = bool(p0.get("not_on_roster"))
        all_years = [int(p["year"]) for p in pubs if str(p["year"]).isdigit()]
        ct_pubs = [p for p in pubs if is_verified(p)]
        entry = {
            "faculty_name": name, "department": person.get("department") or p0.get("department", ""),
            "on_roster": not not_on_roster, "expertise_tier": tier,
            "verified_ai_publications": len(ver), f"verified_ai_last_{RECENT_YEARS}_years": recent,
            "unverified_ai_publications": len(unver),
            "citytech_publications": len(ct_pubs), "total_publications": len(pubs),
            "first_ai_year": min(years) if years else "", "latest_ai_year": max(years) if years else "",
            "ai_citations": sum(int(p["citations"]) for p in ver if str(p["citations"]).isdigit()),
            "main_ai_areas": ", ".join(areas[:3]),
            "recent_ai_titles": " | ".join(p["title"] for p in sorted(
                ver or unver, key=lambda p: str(p["publication_date"]), reverse=True)[:3]),
        }
        pool.append(entry)
        site.append({
            "name": name, "department": entry["department"], "title": person.get("title", ""),
            "email": person.get("email", ""), "orcid": person.get("orcid", ""),
            "on_roster": entry["on_roster"], "tier": tier, "verified": len(ver), "recent": recent,
            "unverified": len(unver), "citytech_pubs": len(ct_pubs), "total_pubs": len(pubs),
            "first_year": min(all_years) if all_years else None,
            "last_year": max(all_years) if all_years else None,
            "ai_citations": entry["ai_citations"], "areas": areas[:4],
            "openalex_id": p0.get("openalex_author_id") or person.get("openalex_id", ""),
            "works": [{
                "title": p["title"], "year": p["year"], "date": p["publication_date"],
                "venue": p["venue"], "type": p["type"], "url": p["url"] or "",
                "citations": p["citations"], "verified": is_verified(p),
                "themes": [t for t in p["ai_themes"].split("; ") if t],
                "evidence": p["ai_evidence"],
            } for p in sorted(ai, key=lambda p: (not is_verified(p), -int(p["year"] or 0)))],
        })
    pool.sort(key=lambda p: (rank.get(p["expertise_tier"], 9), -p["verified_ai_publications"]))
    site.sort(key=lambda p: (rank.get(p["tier"], 9), -p["verified"], -p["unverified"]))
    return pool, site


def site_payload(site_people, rows, roster, citytech_works=None):
    roster_names = {p["name"] for p in roster.people}
    matched = {r["faculty_name"] for r in rows if r["faculty_name"] in roster_names}
    return {
        "generated": time.strftime("%Y-%m-%d"),
        "recent_years": RECENT_YEARS,
        "tiers": [t for t, _, _ in TIERS] + [REVIEW_TIER],
        "stats": {
            "roster_faculty": len(roster.people),
            "faculty_with_publications": len(matched),
            "citytech_works": citytech_works,
            "ai_publications": sum(1 for r in rows if r.get("is_ai") and is_verified(r)),
            "people": len(site_people),
        },
        "people": site_people,
    }


COLUMNS = ["faculty_name", "department", "title", "publication_date", "year", "is_ai",
           "ai_themes", "ai_evidence", "type", "venue", "doi", "url", "citations",
           "found_in", "n_sources", "citytech_affiliation_on_paper", "match_method"]


# ----------------------------------------------------------------------------- human review decisions
#
# overrides.csv records decisions a person made while reviewing the site, so they survive every
# monthly rebuild. One decision per row. See MAINTAINING.md for examples.
#
#   action          person            paper                      value
#   not_ai          Ari Maller        W4387..., DOI or title      -         paper isn't AI
#   is_ai           Ari Maller        W4387..., DOI or title      -         paper is AI
#   not_theirs      Lin Zhou          W4387..., DOI or title      -         someone else's paper
#   not_theirs      Lin Zhou          *unverified*                -         drop ALL unverified papers
#   confirm_theirs  Viviana Acquaviva W4387..., DOI or title      -         unverified paper is theirs
#   department      Fangyang Shen     -                           Computer Systems Technology
#   hide            Some Student      -                           reason (e.g. "student", "left 2023")

OVERRIDE_ACTIONS = {"not_ai", "is_ai", "not_theirs", "confirm_theirs", "department", "hide"}


def load_overrides(path):
    if not path or not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(f)]
    good = []
    for i, r in enumerate(rows, start=2):
        if not r.get("action") or r["action"].startswith("#"):
            continue
        if r["action"] not in OVERRIDE_ACTIONS:
            log(f"  ! overrides.csv line {i}: unknown action '{r['action']}' (ignored)")
            continue
        r["_line"], r["_used"] = i, 0
        good.append(r)
    log(f"Overrides: {len(good)} review decisions loaded")
    return good


def _paper_matches(row, key):
    key = key.strip()
    if not key:
        return False
    if key.lower() == "*unverified*":
        return not is_verified(row)
    if re.fullmatch(r"W\d+", key, re.I):
        return row.get("openalex_work_id", "").upper() == key.upper()
    if norm_doi(key) and "/" in key and norm_doi(key) == row.get("doi"):
        return True
    return norm_title(key) == norm_title(row.get("title", ""))


def apply_overrides(rows, overrides):
    """Apply after AI classification. Returns the rows to keep."""
    def same_person(o, r):
        return o.get("person", "").lower() in ("*", "", r["faculty_name"].lower())
    keep = []
    for r in rows:
        drop = False
        for o in overrides:
            a = o["action"]
            if a in ("department", "hide") or not same_person(o, r) or not _paper_matches(r, o.get("paper", "")):
                continue
            o["_used"] += 1
            if a == "not_theirs":
                drop = True
            elif a == "not_ai":
                r["is_ai"], r["ai_themes"], r["ai_evidence"] = False, "", ""
            elif a == "is_ai":
                r["is_ai"] = True
                r["ai_themes"] = r.get("ai_themes") or "AI (general)"
                r["ai_evidence"] = ("confirmed by reviewer; " + (r.get("ai_evidence") or "")).strip("; ")
            elif a == "confirm_theirs":
                r["reviewer_verified"] = True
        if not drop:
            keep.append(r)
    return keep


def apply_person_overrides(site_people, pool, overrides):
    hide = {o["person"].lower(): o for o in overrides if o["action"] == "hide"}
    dept = {o["person"].lower(): o for o in overrides if o["action"] == "department"}
    for o in list(hide.values()) + list(dept.values()):
        o["_used"] += sum(1 for p in site_people if p["name"].lower() == o["person"].lower())
    site_people[:] = [p for p in site_people if p["name"].lower() not in hide]
    pool[:] = [p for p in pool if p["faculty_name"].lower() not in hide]
    for p in site_people:
        o = dept.get(p["name"].lower())
        if o:
            p["department"] = o.get("value", "")
    for p in pool:
        o = dept.get(p["faculty_name"].lower())
        if o:
            p["department"] = o.get("value", "")


# ----------------------------------------------------------------------------- safety checks + report

# A run is refused (nothing overwritten) if it looks broken compared with last month's data.
GUARD_MIN_WORKS_RATIO = 0.7     # City Tech papers found must be >= 70% of last month's
GUARD_MIN_PEOPLE_RATIO = 0.6    # people in the talent pool must be >= 60% of last month's


def check_and_report(payload, previous, rows, roster, overrides, force=False):
    """Compare with last month. Returns (ok, report dict)."""
    stats = payload["stats"]
    warnings, problems = [], []
    if not stats.get("citytech_works"):
        problems.append("OpenAlex returned no City Tech papers. The API may be down or the key/quota exhausted.")
    if previous:
        pw, pp = previous["stats"].get("citytech_works") or 0, len(previous.get("people", []))
        if pw and (stats.get("citytech_works") or 0) < GUARD_MIN_WORKS_RATIO * pw:
            problems.append(f"City Tech papers dropped from {pw} to {stats.get('citytech_works')} "
                            f"(more than {100 - int(GUARD_MIN_WORKS_RATIO * 100)}%).")
        if pp and len(payload["people"]) < GUARD_MIN_PEOPLE_RATIO * pp:
            problems.append(f"Talent pool shrank from {pp} to {len(payload['people'])} people.")
    for host, n in sorted(REQUEST_FAILURES.items()):
        warnings.append(f"{n} failed requests to {host}.")
    stale = [o for o in overrides if not o["_used"]]
    for o in stale:
        warnings.append(f"overrides.csv line {o['_line']} ({o['action']} / {o.get('person')} / "
                        f"{o.get('paper') or o.get('value')}) matched nothing this month.")

    before = {p["name"]: p for p in (previous or {}).get("people", [])}
    after = {p["name"]: p for p in payload["people"]}
    new_people = [p for n, p in after.items() if n not in before]
    gone = [p for n, p in before.items() if n not in after]
    moved = [(before[n]["tier"], p) for n, p in after.items() if n in before and before[n]["tier"] != p["tier"]]
    tiers = defaultdict(int)
    for p in payload["people"]:
        tiers[p["tier"]] += 1
    needs_review = [p for p in payload["people"] if p["tier"] == REVIEW_TIER]
    new_unrostered = [p for p in new_people if not p["on_roster"]]
    by_source = defaultdict(int)
    for r in rows:
        for s_ in (r.get("found_in") or "").split("; "):
            if s_:
                by_source[s_] += 1
    no_pubs = sorted({p["name"] for p in roster.people} - {r["faculty_name"] for r in rows})

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "status": "REFUSED" if problems and not force else "OK",
        "problems": problems, "warnings": warnings,
        "stats": stats, "tiers": dict(tiers), "records_by_source": dict(by_source),
        "new_people": [(p["name"], p["tier"], p["on_roster"]) for p in new_people],
        "removed_people": [(p["name"], p["tier"]) for p in gone],
        "tier_changes": [(p["name"], old, p["tier"]) for old, p in moved],
        "needs_review": [p["name"] for p in needs_review],
        "new_not_on_roster": [p["name"] for p in new_unrostered],
        "roster_without_publications": no_pubs,
        "attention": bool(problems or new_people or gone or moved or stale or warnings),
    }
    return (not problems or force), report


def report_markdown(rep):
    L = [f"# Talent pool update — {rep['date']}", "", f"**Status: {rep['status']}**", ""]
    if rep["problems"]:
        L += ["## Problems (nothing was overwritten)", *[f"- {x}" for x in rep["problems"]],
              "", "If the drop is real (for example, a big roster change), rerun with `--force`.", ""]
    s = rep["stats"]
    L += ["## Numbers", f"- Roster faculty: {s.get('roster_faculty')}",
          f"- City Tech papers scanned: {s.get('citytech_works')}",
          f"- Verified AI papers: {s.get('ai_publications')}",
          f"- People in the talent pool: {s.get('people')}",
          "- By tier: " + ", ".join(f"{k} {v}" for k, v in rep["tiers"].items()),
          "- Records by source: " + ", ".join(f"{k} {v}" for k, v in rep["records_by_source"].items()), ""]
    def section(title, items, fmt=str):
        if items:
            L.extend([f"## {title}", *[f"- {fmt(x)}" for x in items], ""])
    section("New in the talent pool", rep["new_people"],
            lambda x: f"{x[0]} — {x[1]}" + ("" if x[2] else " (not on roster: confirm department and status)"))
    section("Tier changes", rep["tier_changes"], lambda x: f"{x[0]}: {x[1]} → {x[2]}")
    section("No longer listed", rep["removed_people"], lambda x: f"{x[0]} (was {x[1]})")
    section("Needs review (check their unverified papers)", rep["needs_review"])
    section("Warnings", rep["warnings"])
    if rep["roster_without_publications"]:
        L += [f"## Roster faculty with no publications found ({len(rep['roster_without_publications'])})",
              "Usually normal (teaching-focused faculty). If someone known to publish is here, add their "
              "ORCID iD or an `aka` name in roster.csv.", ""]
    L += ["How to act on any of this: see MAINTAINING.md → *Monthly review*."]
    return "\n".join(L)


def write_outputs(rows, roster, unmatched, outdir, overrides=(), force=False):
    outdir.mkdir(parents=True, exist_ok=True)
    overrides = list(overrides)
    for r in rows:
        is_ai, themes, ev = classify_ai(r)
        r["is_ai"], r["ai_themes"], r["ai_evidence"] = is_ai, "; ".join(themes), ev
    rows = apply_overrides(rows, overrides)
    pool, site_people = build_talent_pool(rows, roster)
    apply_person_overrides(site_people, pool, overrides)
    payload = site_payload(site_people, rows, roster, CITYTECH_WORKS_SEEN.get("n"))
    payload["stats"]["people"] = len(site_people)

    previous = None
    if SITE_DATA_PATH and Path(SITE_DATA_PATH).exists():
        try:
            previous = json.loads(Path(SITE_DATA_PATH).read_text(encoding="utf-8"))
        except ValueError:
            previous = None
    ok, report = check_and_report(payload, previous, rows, roster, overrides, force)
    md = report_markdown(report)
    (outdir / "run_report.md").write_text(md, encoding="utf-8")
    (outdir / "run_report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    log("\n" + md + "\n")
    if not ok:
        log("REFUSED: this run looks broken compared with last month, so nothing was overwritten.")
        sys.exit(2)

    (outdir / "talent_pool.json").write_text(json.dumps(payload, ensure_ascii=False, default=str),
                                             encoding="utf-8")
    if SITE_DATA_PATH:
        Path(SITE_DATA_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(SITE_DATA_PATH).write_text(json.dumps(payload, ensure_ascii=False, default=str),
                                        encoding="utf-8")
    with open(outdir / "ai_talent_pool.csv", "w", newline="", encoding="utf-8") as f:
        if pool:
            w = csv.DictWriter(f, fieldnames=list(pool[0].keys()))
            w.writeheader()
            w.writerows(pool)
    with open(outdir / "publications.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    cov = {p["name"]: {"faculty_name": p["name"], "department": p["department"],
                       "orcid": p["orcid"], "total": 0, "OpenAlex": 0, "ORCID": 0,
                       "Crossref": 0, "CUNY Academic Works": 0, "latest_year": ""}
           for p in roster.people}
    for r in rows:
        c = cov.get(r["faculty_name"])
        if not c:
            continue
        c["total"] += 1
        for s in r["found_in"].split("; "):
            c[s] += 1
        if str(r["year"]) > str(c["latest_year"]):
            c["latest_year"] = r["year"]
    cov_rows = sorted(cov.values(), key=lambda c: (c["total"], c["faculty_name"]))
    with open(outdir / "faculty_coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(next(iter(cov.values())).keys()) if cov else ["faculty_name"])
        w.writeheader()
        w.writerows(cov_rows)

    with open(outdir / "unmatched_authors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "citytech_works", "orcid", "openalex_id"])
        for name, u in sorted(unmatched.items(), key=lambda kv: -kv[1]["works"]):
            w.writerow([name, u["works"], u["orcid"], u["openalex_id"]])

    try:
        import pandas as pd
        with pd.ExcelWriter(outdir / "publications.xlsx") as xw:
            pd.DataFrame(pool).to_excel(xw, sheet_name="AI talent pool", index=False)
            pd.DataFrame([r for r in rows if r["is_ai"]], columns=COLUMNS).to_excel(
                xw, sheet_name="AI publications", index=False)
            pd.DataFrame(rows, columns=COLUMNS).to_excel(xw, sheet_name="Publications", index=False)
            pd.DataFrame(cov_rows).to_excel(xw, sheet_name="Faculty coverage", index=False)
    except Exception as e:
        log(f"(skipped .xlsx: {e})")

    write_dashboard(rows, cov_rows, pool, outdir / "dashboard.html")
    log(f"\nDone. {len(rows)} publications for "
        f"{sum(1 for c in cov_rows if c['total'])}/{len(cov_rows)} faculty; "
        f"{sum(r['is_ai'] for r in rows)} AI publications; {len(pool)} faculty in AI talent pool "
        f"-> {outdir}/")


def write_dashboard(rows, cov_rows, pool, path):
    slim = [{k: r.get(k, "") for k in ("faculty_name", "department", "title", "publication_date",
                                       "year", "type", "venue", "url", "found_in", "is_ai",
                                       "ai_themes", "ai_evidence")} for r in rows]
    payload = json.dumps({"pubs": slim, "cov": cov_rows, "pool": pool,
                          "recent": RECENT_YEARS}, default=str).replace("</", "<\\/")
    path.write_text(DASHBOARD_TEMPLATE.replace("__DATA__", payload), encoding="utf-8")


DASHBOARD_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>City Tech Faculty Publications</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e3e3e0;--acc:#1f5fbf;--warn:#b5462b}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--ink:#ececee;--mute:#9a9aa2;--line:#2e2e33;--acc:#79a7f2;--warn:#f08a6c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}p.sub{color:var(--mute);margin:0 0 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.kpi b{display:block;font-size:24px}.kpi span{color:var(--mute);font-size:12px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}@media(max-width:760px){.row{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow:hidden}.card h2{font-size:14px;margin:0 0 10px}
.bar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;cursor:pointer}.bar .l{width:38%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .t{flex:1;background:var(--line);border-radius:3px;height:10px}.bar .f{background:var(--acc);height:10px;border-radius:3px}.bar .n{width:42px;text-align:right;color:var(--mute)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit}
input{flex:1;min-width:200px}.tbl{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mute);font-weight:600;cursor:pointer;white-space:nowrap}
a{color:var(--acc);text-decoration:none}.zero{color:var(--warn)}small{color:var(--mute)}
</style></head><body><main>
<h1>City Tech Faculty Publications</h1>
<p class="sub">Full-time faculty · merged from OpenAlex, ORCID, Crossref and CUNY Academic Works</p>
<div class="kpis" id="kpis"></div>
<div class="card" style="margin-bottom:20px"><h2>AI talent pool <small>ranked by AI publication record · click a name to see their AI papers</small></h2>
<div class="tbl"><table><thead><tr><th>Faculty</th><th>Department</th><th>Tier</th><th>AI pubs</th><th id="rh">Recent</th><th>Main AI areas</th><th>Latest</th></tr></thead><tbody id="pool"></tbody></table></div></div>
<div class="row"><div class="card"><h2>Publications by department</h2><div id="depts"></div></div>
<div class="card"><h2>Publications by year</h2><div id="years"></div></div></div>
<div class="card" style="margin-bottom:20px"><h2>Faculty with no publications found <small>(check these profiles first)</small></h2><div id="gaps"></div></div>
<div class="card"><div class="filters"><input id="q" placeholder="Search title, faculty, venue…">
<select id="fd"><option value="">All departments</option></select><select id="fy"><option value="">All years</option></select>
<label style="display:flex;align-items:center;gap:6px"><input type="checkbox" id="fa" style="flex:none;min-width:0">AI only</label></div>
<div class="tbl"><table><thead><tr><th data-k="faculty_name">Faculty</th><th data-k="department">Department</th><th data-k="title">Title</th><th data-k="publication_date">Date</th><th data-k="found_in">Sources</th></tr></thead><tbody id="tb"></tbody></table></div>
<p id="cnt"><small></small></p></div>
</main><script>
const D=__DATA__,P=D.pubs,C=D.cov;let sk="publication_date",sd=-1;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const count=(a,f)=>a.reduce((m,x)=>(m[f(x)]=(m[f(x)]||0)+1,m),{});
function bars(el,obj,sortByKey,onClick){const e=Object.entries(obj).sort(sortByKey?(a,b)=>b[0].localeCompare(a[0]):(a,b)=>b[1]-a[1]).slice(0,25),mx=Math.max(1,...e.map(x=>x[1]));
document.getElementById(el).innerHTML=e.map(([k,v])=>`<div class="bar" data-v="${esc(k)}"><span class="l">${esc(k||"(none)")}</span><span class="t"><span class="f" style="display:block;width:${v/mx*100}%"></span></span><span class="n">${v}</span></div>`).join("");
document.querySelectorAll(`#${el} .bar`).forEach(b=>b.onclick=()=>onClick(b.dataset.v));}
const withPubs=C.filter(c=>c.total>0).length,depts=[...new Set(C.map(c=>c.department).concat(P.map(p=>p.department)))].filter(Boolean).sort();
const POOL=D.pool||[],rk="ai_pubs_last_"+D.recent+"_years";document.getElementById("rh").textContent="Last "+D.recent+" yrs";
document.getElementById("pool").innerHTML=POOL.length?POOL.map(p=>`<tr><td><a href="#" data-n="${esc(p.faculty_name)}">${esc(p.faculty_name)}</a></td><td>${esc(p.department)}</td><td><b>${esc(p.expertise_tier)}</b></td><td>${p.ai_publications}</td><td>${p[rk]}</td><td><small>${esc(p.main_ai_areas)}</small></td><td>${esc(p.latest_ai_year)}</td></tr>`).join(""):"<tr><td colspan=7><small>No AI publications found.</small></td></tr>";
document.querySelectorAll("#pool a").forEach(a=>a.onclick=e=>{e.preventDefault();q.value=a.dataset.n;fa.checked=true;render();document.getElementById("tb").scrollIntoView({behavior:"smooth"})});
document.getElementById("kpis").innerHTML=[[POOL.filter(p=>p.expertise_tier==="Core AI expert").length,"core AI experts"],[POOL.length,"faculty with AI work"],[P.filter(p=>p.is_ai).length,"AI publications"],[P.length,"publications"],[C.length,"faculty on roster"],[withPubs,"faculty with ≥1 publication"],[depts.length,"departments"],[P.filter(p=>p.found_in.includes(";")).length,"confirmed by 2+ sources"]].map(([n,l])=>`<div class="kpi"><b>${n.toLocaleString()}</b><span>${l}</span></div>`).join("");
bars("depts",count(P,p=>p.department),false,v=>{fd.value=v;render()});
bars("years",count(P,p=>String(p.year||"")),true,v=>{fy.value=v;render()});
const gaps=C.filter(c=>!c.total);document.getElementById("gaps").innerHTML=gaps.length?gaps.map(c=>`<span class="zero">${esc(c.faculty_name)}</span> <small>${esc(c.department)}</small>`).join(" · "):"<small>None — every roster member has at least one publication.</small>";
const fd=document.getElementById("fd"),fy=document.getElementById("fy"),q=document.getElementById("q"),fa=document.getElementById("fa");
depts.forEach(d=>fd.add(new Option(d,d)));[...new Set(P.map(p=>String(p.year||"")))].filter(Boolean).sort().reverse().forEach(y=>fy.add(new Option(y,y)));
function render(){const t=q.value.toLowerCase();let r=P.filter(p=>(!fa.checked||p.is_ai)&&(!fd.value||p.department===fd.value)&&(!fy.value||String(p.year)===fy.value)&&(!t||(p.title+" "+p.faculty_name+" "+p.venue).toLowerCase().includes(t)));
r.sort((a,b)=>String(a[sk]).localeCompare(String(b[sk]))*sd);
document.getElementById("tb").innerHTML=r.slice(0,1000).map(p=>`<tr><td>${esc(p.faculty_name)}</td><td>${esc(p.department)}</td><td>${p.url?`<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>`:esc(p.title)}<br><small>${esc(p.venue)}${p.is_ai?` · <b style="color:var(--acc)">AI</b> <span title="${esc(p.ai_evidence)}">${esc(p.ai_themes)}</span>`:""}</small></td><td>${esc(p.publication_date)}</td><td><small>${esc(p.found_in)}</small></td></tr>`).join("");
document.querySelector("#cnt small").textContent=`${r.length.toLocaleString()} shown${r.length>1000?" (first 1,000 rendered — narrow the filters)":""}`;}
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{sd=sk===th.dataset.k?-sd:1;sk=th.dataset.k;render()});
[q,fd,fy,fa].forEach(e=>e.oninput=render);render();
</script></body></html>"""


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default="roster.csv", help="CSV of full-time faculty")
    ap.add_argument("--email", default="", help="your email (gets faster 'polite pool' API access)")
    ap.add_argument("--since", type=int, help="only publications from this year onward")
    ap.add_argument("--full-career", action="store_true",
                    help="also pull each person's pubs from before/outside City Tech (OpenAlex)")
    ap.add_argument("--skip", nargs="*", default=[], choices=["openalex", "orcid", "crossref", "academicworks"])
    ap.add_argument("--out", default="output")
    ap.add_argument("--site-data", default="", help="also write the website's data file here "
                    "(e.g. docs/data/talent_pool.json)")
    ap.add_argument("--roster-only", action="store_true",
                    help="leave out City Tech authors who are not on the roster")
    ap.add_argument("--overrides", default="overrides.csv",
                    help="review decisions to apply every run (see MAINTAINING.md)")
    ap.add_argument("--force", action="store_true",
                    help="publish even if the safety checks think the run looks broken")
    ap.add_argument("--include-all", action="store_true",
                    help="keep adjuncts/part-time rows when the roster has a status column")
    ap.add_argument("--suggest-roster", action="store_true",
                    help="write roster_candidates.csv from OpenAlex and exit")
    a = ap.parse_args()
    global SITE_DATA_PATH
    SITE_DATA_PATH = a.site_data

    if a.email:
        SESSION.headers["User-Agent"] = f"CityTechFacultyPubs/1.0 (mailto:{a.email})"

    inst = None
    if a.suggest_roster or "openalex" not in a.skip:
        inst = openalex_institution_id(a.email)
    if a.suggest_roster:
        suggest_roster(inst, a.email, "roster_candidates.csv")
        return

    roster = Roster.load(a.roster, a.include_all)
    log(f"Roster: {len(roster.people)} faculty, {len(roster.by_orcid)} with ORCID")

    records, unmatched = [], {}
    if "openalex" not in a.skip:
        r, unmatched = harvest_openalex(roster, inst, a.email, a.since, a.full_career,
                                        include_unrostered=not a.roster_only)
        records += r
    if "orcid" not in a.skip:
        records += harvest_orcid(roster, a.since)
    if "crossref" not in a.skip:
        records += harvest_crossref(roster, a.email, a.since)
    if "academicworks" not in a.skip:
        records += harvest_academic_works(roster, a.since)

    write_outputs(merge(records, a.since), roster, unmatched, Path(a.out),
                  load_overrides(a.overrides), a.force)


if __name__ == "__main__":
    main()
