"""Where items come from. Each harvester returns a list of items (see items.py).

  OpenAlex            every paper listing City Tech + the earlier career of matched authors
  CUNY Academic Works City Tech's repository (posters, presentations, OER, deposited papers)
  ORCID               works on a faculty member's own ORCID record (when we know their iD)
  NSF, NIH            grants awarded to City Tech, with PI / co-PI
  Dept bio            publication / grant lists faculty wrote in their directory bio
  Uploaded workbooks  anything added by hand (e.g. Google Scholar collections), see inbox.py

All free, no keys required (an OpenAlex key just raises the daily quota).
"""
import html as htmllib
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from html.parser import HTMLParser

from .common import (get, post_json, log, norm_doi, norm_orcid, name_key, read_csv,
                     REQUEST_FAILURES)
from .items import new_item, type_from_openalex, type_from_text

OPENALEX = "https://api.openalex.org"
CITYTECH_ROR = "021a7pw18"
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "")
WORK_FIELDS = ("id,doi,display_name,publication_date,publication_year,type,primary_location,"
               "best_oa_location,open_access,authorships,cited_by_count,topics,keywords,"
               "abstract_inverted_index")
STATS = defaultdict(int)          # numbers for the Sources sheet and the run report


# ----------------------------------------------------------------------------- OpenAlex

def openalex_paged(endpoint, flt, mailto, select=None):
    """page= paging (cursor paging needs an API key since 2026); max 10,000 results/query."""
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
        res = data.get("results", [])
        yield from res
        seen += len(res)
        if not res or seen >= data.get("meta", {}).get("count", 0) or seen >= 10000:
            return
        page += 1


def openalex_institution(mailto):
    d = get(f"{OPENALEX}/institutions/ror:{CITYTECH_ROR}", {"mailto": mailto})
    return d["id"].split("/")[-1] if d else None


def _abstract(inv):
    if not inv:
        return ""
    return " ".join(w for _, w in sorted((i, w) for w, idxs in inv.items() for i in idxs))


def _openalex_item(w, person_key, verified):
    src = (w.get("primary_location") or {}).get("source") or {}
    t = type_from_openalex(w.get("type"), src.get("type"), src.get("display_name"))
    oa = w.get("best_oa_location") or {}
    pdf = oa.get("pdf_url") or ""
    it = new_item(
        person_key, "OpenAlex",
        item_type=t or "", title=w.get("display_name") or "", year=w.get("publication_year") or "",
        date=w.get("publication_date") or "", venue=src.get("display_name") or "",
        authors="; ".join((a.get("author") or {}).get("display_name", "") for a in w.get("authorships", [])),
        doi=w.get("doi") or "", url=w.get("doi") or w.get("id") or "", verified=verified,
        citations=w.get("cited_by_count", ""), abstract=_abstract(w.get("abstract_inverted_index")),
        fulltext_url=pdf or oa.get("landing_page_url") or "",
        fulltext_type="Open-access PDF (via OpenAlex)" if pdf else ("Open-access page (via OpenAlex)" if oa else "Not found"),
        oa_status=(w.get("open_access") or {}).get("oa_status", ""),
        openalex_id=(w.get("id") or "").split("/")[-1],
        topics=[{"name": x.get("display_name", ""), "subfield": (x.get("subfield") or {}).get("display_name", ""),
                 "score": x.get("score", 0)} for x in (w.get("topics") or [])],
        keywords="; ".join(k.get("display_name", "") for k in (w.get("keywords") or []) if (k.get("score") or 0) >= 0.5),
    )
    if it["abstract"]:
        it["abstract_source"] = "OpenAlex"
    if t is None:
        it["item_type"] = "Other"
        it["excluded_reason"] = f"Not a research item (OpenAlex type: {w.get('type')})"
    return it


def harvest_openalex(roster, mailto, full_career=True):
    inst = openalex_institution(mailto)
    if not inst:
        raise SystemExit("Could not reach OpenAlex (City Tech institution lookup failed).")
    items, unmatched = [], defaultdict(lambda: {"works": 0, "orcid": "", "openalex_id": ""})
    id_counts = defaultdict(lambda: defaultdict(int))
    n = 0
    for w in openalex_paged("works", f"institutions.id:{inst}", mailto, WORK_FIELDS):
        n += 1
        done = set()
        for a in w.get("authorships", []):
            if inst not in [i.get("id", "").split("/")[-1] for i in a.get("institutions", [])]:
                continue
            au = a.get("author") or {}
            aid = (au.get("id") or "").split("/")[-1]
            p, _ = roster.match(au.get("display_name"), au.get("orcid"), aid)
            if not p:
                u = unmatched[au.get("display_name") or "?"]
                u["works"] += 1
                u["orcid"] = norm_orcid(au.get("orcid")) or u["orcid"]
                u["openalex_id"] = aid or u["openalex_id"]
                continue
            if p["key"] in done:
                continue
            done.add(p["key"])
            items.append(_openalex_item(w, p["key"], True))
            if aid:
                id_counts[aid][p["key"]] += 1
    STATS["openalex_citytech_works"] = n
    log(f"OpenAlex: {n} City Tech works, {len(items)} faculty-item links")
    profiles = {aid: max(c, key=c.get) for aid, c in id_counts.items()}
    for oid, p in roster.by_openalex.items():
        profiles.setdefault(oid, p["key"])
    for aid, key in profiles.items():
        roster.by_key[key].setdefault("openalex_id", aid)
    if full_career and profiles:
        ids = list(profiles)
        for i in range(0, len(ids), 50):
            grp = ids[i:i + 50]
            for w in openalex_paged("works", "authorships.author.id:" + "|".join(grp), mailto, WORK_FIELDS):
                done = set()
                for a in w.get("authorships", []):
                    aid = ((a.get("author") or {}).get("id") or "").split("/")[-1]
                    if aid not in grp or aid in done:
                        continue
                    done.add(aid)
                    if inst in [x.get("id", "").split("/")[-1] for x in a.get("institutions", [])]:
                        continue                  # already collected as verified
                    items.append(_openalex_item(w, profiles[aid], False))
    STATS["openalex_items"] = len(items)
    return items, unmatched


# ----------------------------------------------------------------------------- CUNY Academic Works

AW_OAI = "https://academicworks.cuny.edu/do/oai/"
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "dc": "http://purl.org/dc/elements/1.1/",
      "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"}


def _oai(verb, **params):
    params = {"verb": verb, **params}
    while True:
        text = get(AW_OAI, params, accept_json=False)
        if not text:
            return
        root = ET.fromstring(text.encode("utf-8"))
        yield root
        tok = root.find(".//oai:resumptionToken", NS)
        if tok is None or not (tok.text or "").strip():
            return
        params = {"verb": verb, "resumptionToken": tok.text.strip()}
        time.sleep(0.5)


def harvest_academic_works(roster):
    sets = []
    for root in _oai("ListSets"):
        for s in root.findall(".//oai:set", NS):
            spec = s.findtext("oai:setSpec", "", NS)
            if spec.split(":")[-1].startswith("ny_"):
                sets.append((spec, s.findtext("oai:setName", "", NS)))
    items, records = [], 0
    for spec, set_name in sets:
        for root in _oai("ListRecords", metadataPrefix="oai_dc", set=spec):
            for rec in root.findall(".//oai:record", NS):
                md = rec.find(".//oai_dc:dc", NS)
                if md is None:
                    continue
                records += 1
                ids = [e.text or "" for e in md.findall("dc:identifier", NS)]
                url = next((i for i in ids if i.startswith("http") and "viewcontent" not in i), "")
                pdf = next((i for i in ids if "viewcontent" in i or i.lower().endswith(".pdf")), "")
                doi = next((norm_doi(i) for i in ids if "doi" in i.lower()), "")
                dctype = md.findtext("dc:type", "", NS)
                for c in md.findall("dc:creator", NS):
                    p, _ = roster.match(c.text)
                    if not p:
                        continue
                    it = new_item(p["key"], "CUNY Academic Works",
                                  item_type=type_from_text(dctype, spec, set_name),
                                  title=md.findtext("dc:title", "", NS), year=md.findtext("dc:date", "", NS)[:4],
                                  date=md.findtext("dc:date", "", NS)[:10],
                                  venue=md.findtext("dc:source", "", NS) or set_name,
                                  authors="; ".join(x.text or "" for x in md.findall("dc:creator", NS)),
                                  doi=doi, url=url, verified=True,
                                  abstract=htmllib.unescape(re.sub(r"<[^>]+>", " ", md.findtext("dc:description", "", NS))).strip(),
                                  fulltext_url=pdf, fulltext_type="PDF in CUNY Academic Works" if pdf else "")
                    if it["abstract"]:
                        it["abstract_source"] = "CUNY Academic Works"
                    if it["item_type"] == "Paper (venue type unclear)" and "Article" in dctype:
                        it["item_type"] = "Journal article"
                    items.append(it)
    STATS["academic_works_records"] = records
    STATS["academic_works_items"] = len(items)
    log(f"CUNY Academic Works: {records} City Tech records, {len(items)} faculty items")
    return items


# ----------------------------------------------------------------------------- ORCID

def harvest_orcid(roster):
    items = []
    for p in [p for p in roster.people if p.get("orcid")]:
        data = get(f"https://pub.orcid.org/v3.0/{p['orcid']}/works")
        for g in (data or {}).get("group", []):
            s = (g.get("work-summary") or [{}])[0]
            pd = s.get("publication-date") or {}
            doi = next((e.get("external-id-value") for e in ((s.get("external-ids") or {}).get("external-id") or [])
                        if e.get("external-id-type") == "doi"), "")
            raw = (s.get("type") or "").replace("-", " ")
            items.append(new_item(
                p["key"], "ORCID", title=(((s.get("title") or {}).get("title") or {}).get("value")) or "",
                item_type=type_from_text(raw) if raw not in ("journal article",) else "Journal article",
                year=((pd.get("year") or {}).get("value")) or "",
                venue=((s.get("journal-title") or {}).get("value")) or "", doi=doi,
                url=f"https://doi.org/{norm_doi(doi)}" if doi else f"https://orcid.org/{p['orcid']}",
                verified=True))
        time.sleep(0.1)
    STATS["orcid_items"] = len(items)
    return items


# ----------------------------------------------------------------------------- grants

NSF_API = "https://api.nsf.gov/services/v1/awards.json"
NIH_API = "https://api.reporter.nih.gov/v2/projects/search"


def _split_copi(s):
    m = re.match(r"(.*?)\s+(\S+@\S+)$", s.strip())
    return (m.group(1), m.group(2)) if m else (s.strip(), "")


def harvest_nsf(roster):
    awards, offset = [], 1
    fields = ("id,title,piFirstName,piLastName,piEmail,coPDPI,startDate,expDate,estimatedTotalAmt,"
              "fundProgramName,abstractText,awardeeName")
    while True:
        d = get(NSF_API, {"awardeeName": '"New York City College of Technology"', "printFields": fields,
                          "rpp": 25, "offset": offset})
        batch = ((d or {}).get("response") or {}).get("award") or []
        awards += batch
        if len(batch) < 25 or offset > 3000:
            break
        offset += 25
    items = []
    for a in awards:
        pi = f"{a.get('piFirstName', '')} {a.get('piLastName', '')}".strip()
        people = [(pi, a.get("piEmail", ""), "PI")] + [(*_split_copi(c), "Co-PI") for c in a.get("coPDPI") or []]
        investigators = "; ".join(n for n, _, _ in people)
        start = a.get("startDate", "")
        for name, email, role in people:
            p, _ = roster.match(name, email=email)
            if not p:
                continue
            it = new_item(p["key"], "NSF", item_type="Grant", title=a.get("title", ""),
                          year=start[-4:], date=start, venue=f"NSF: {a.get('fundProgramName', '')}".rstrip(": "),
                          authors=investigators, role=role, amount=a.get("estimatedTotalAmt", ""),
                          award_id=a.get("id", ""), verified=True,
                          url=f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={a.get('id', '')}",
                          abstract=a.get("abstractText", ""), abstract_source="NSF" if a.get("abstractText") else "")
            items.append(it)
    STATS["nsf_awards"], STATS["nsf_items"] = len(awards), len(items)
    log(f"NSF: {len(awards)} City Tech awards, {len(items)} faculty items")
    return items


def harvest_nih(roster):
    rows, offset = [], 0
    while True:
        d = post_json(NIH_API, {"criteria": {"org_names": ["NEW YORK CITY COLLEGE OF TECHNOLOGY"]},
                                "include_fields": ["ApplId", "CoreProjectNum", "ProjectTitle", "FiscalYear",
                                                   "PrincipalInvestigators", "AwardAmount", "ProjectStartDate",
                                                   "AgencyIcAdmin", "AbstractText"],
                                "offset": offset, "limit": 500})
        batch = (d or {}).get("results") or []
        rows += batch
        if len(batch) < 500:
            break
        offset += 500
    projects = defaultdict(list)
    for r in rows:
        projects[r.get("core_project_num") or r.get("appl_id")].append(r)
    items = []
    for core, yrs in projects.items():
        yrs.sort(key=lambda r: r.get("fiscal_year") or 0)
        last = yrs[-1]
        pis = {}
        for r in yrs:
            for p in r.get("principal_investigators") or []:
                pis[p.get("full_name", "")] = p.get("is_contact_pi")
        ic = ((last.get("agency_ic_admin") or {}).get("abbreviation")) or ""
        for name, contact in pis.items():
            p, _ = roster.match(re.sub(r"\s+", " ", name))
            if not p:
                continue
            items.append(new_item(
                p["key"], "NIH", item_type="Grant", title=last.get("project_title", ""),
                year=yrs[0].get("fiscal_year", ""), date=(yrs[0].get("project_start_date") or "")[:10],
                venue=f"NIH: {ic}".rstrip(": "), authors="; ".join(re.sub(r"\s+", " ", n) for n in pis),
                role="PI" if contact else "Co-PI", amount=sum(r.get("award_amount") or 0 for r in yrs),
                award_id=core, verified=True, url=f"https://reporter.nih.gov/project-details/{last.get('appl_id')}",
                abstract=last.get("abstract_text") or "", abstract_source="NIH" if last.get("abstract_text") else ""))
    STATS["nih_projects"], STATS["nih_items"] = len(projects), len(items)
    log(f"NIH: {len(projects)} City Tech projects, {len(items)} faculty items")
    return items


# ----------------------------------------------------------------------------- faculty bios

SECTION_RE = re.compile(r"publication|grant|patent|presentation|paper|book|chapter|proceeding|talk|"
                        r"poster|report|award|funding|research project", re.I)
STOP_RE = re.compile(r"education|courses? taught|membership|areas? of (interest|expertise)|research interest|"
                     r"honors?|teaching|service|biography|contact|office hours|degrees?", re.I)


class _BioParser(HTMLParser):
    """Turns bio HTML into ('heading', text) and ('entry', text, links) events."""

    def __init__(self):
        super().__init__()
        self.events, self.buf, self.links, self.stack, self.strong = [], [], [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("li", "p", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.stack.append(tag)
        if tag in ("strong", "b"):
            self.strong.append(len("".join(self.buf)))
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag == "br" and self.stack and self.stack[-1] == "p":
            self._flush(keep_tag=True)

    def handle_endtag(self, tag):
        if tag in ("li", "p", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()

    def handle_data(self, d):
        self.buf.append(d)

    def _flush(self, keep_tag=False):
        text = re.sub(r"\s+", " ", htmllib.unescape("".join(self.buf))).strip()
        tag = self.stack[-1] if self.stack else "p"
        if text:
            short = len(text) < 90 and not re.search(r"(19|20)\d\d.*\.", text)
            if tag.startswith("h") or (tag == "p" and short):
                self.events.append(("heading", text.rstrip(":")))
            else:
                self.events.append(("entry", text, list(self.links)))
        self.buf, self.links, self.strong = [], [], []
        if not keep_tag and self.stack:
            self.stack.pop()


AUTHORISH = re.compile(r"^(?:[A-Z][\w'\-]+,?\s+(?:[A-Z]\.\s*){1,3},?\s*(?:and\s+|&\s+)?)+$|"
                       r"^(?:[A-Z]\.\s*){1,3}[A-Z][\w'\-]+(?:,\s*(?:[A-Z]\.\s*){1,3}[A-Z][\w'\-]+)*$")
NOT_TITLE = re.compile(r"^(?:\[|\(|panelists?:|pp\.|vol\.|doi|https?:|in:|retrieved|available)", re.I)


def good_title(t):
    """A usable title has real words, isn't a page range or an author list."""
    t = (t or "").strip(" .,;:")
    words = re.findall(r"[A-Za-z]{2,}", t)
    if len(words) < 3 or sum(len(w) for w in words) < 12:
        return False
    if NOT_TITLE.search(t) or AUTHORISH.match(t) or re.match(r"^(?:and|in|at|of|the end)\b", t):
        return False
    if len(re.findall(r"\d", t)) > len(t) * 0.3:
        return False
    return True


LEAD_AUTHORS = re.compile(
    r"^(?:(?:[A-Z][\w'\-]+,?\s+[A-Z]{1,3}\b\.?,?\s*(?:and\s+|&\s+)?)+"                 # Hatzi K, Jiang Y,
    r"|(?:(?:[A-Z]\.\s*){1,3}[A-Z][\w'\-]+(?:,\s*|\s+and\s+|\s*&\s*))+)")                # C. Calinescu, M. Penn and


def _strip_authors(t):
    t = re.sub(r"^\s*\[\d+\]\s*", "", t)
    m = LEAD_AUTHORS.match(t)
    return t[m.end():].lstrip(" ,.:") if m and m.end() < len(t) - 10 else t


def parse_citation(text, links):
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    this_year = time.localtime().tm_year
    years = [y for y in re.findall(r"\b(19[5-9]\d|20\d\d)\b", text) if int(y) <= this_year + 1]
    paren = re.search(r"\((19[5-9]\d|20\d\d)[a-z]?\)", text)
    year = paren.group(1) if paren else (years[0] if years else "")
    doi = re.search(r"\b10\.\d{4,9}/[^\s\"<>]+", text + " " + " ".join(links))
    url = next((l for l in links if l.startswith("http")), "")
    candidates = []
    q = re.search(r"[\"\u201c\u201d]([^\"\u201c\u201d]{12,}?)[,.]?[\"\u201c\u201d]", text)
    if q:
        candidates.append(q.group(1))
    if paren:
        candidates.append(re.split(r"(?<=[a-z0-9\)\?])\.\s", text[paren.end():].lstrip(" .,:"), maxsplit=1)[0])
    segments = [x.strip() for x in re.split(r"(?<=[a-z0-9\)\?\u201d\"])\.\s+", text) if x.strip()]
    candidates += sorted(segments[:4], key=lambda x: -len(re.findall(r"[a-z]{3,}", x)))
    candidates = [_strip_authors(c) for c in candidates]
    title = next((c for c in candidates if good_title(c)), "")
    clean = bool(title)
    if not title:
        title = text[:200]
    authors = text[:paren.start()].strip(" ,.") if paren else ""
    amount = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|K|M|million)?", text)
    amt = ""
    if amount:
        v = float(amount.group(1).replace(",", ""))
        amt = int(v * {"k": 1e3, "K": 1e3, "M": 1e6, "million": 1e6}.get(amount.group(2) or "", 1))
    role = "Co-PI" if re.search(r"\bco-?PI\b|co-principal", text, re.I) else (
        "PI" if re.search(r"\bPI\b|principal investigator", text) else "")
    return {"year": year, "doi": doi.group(0).rstrip(".,;)") if doi else "", "url": url,
            "title": title.strip(" .,\"\u201c\u201d")[:400], "authors": authors[:500], "amount": amt,
            "role": role, "clean": clean}


GRANT_WORDS = re.compile(r"\bgrants?\b|\bNSF\b|\bNIH\b|PSC[- ]?CUNY|research award|funded|funding|"
                         r"foundation award|fellowship|\$\s?\d", re.I)
HONOR_WORDS = re.compile(r"\bprize\b|finalist|\bhonou?r|winner|nominat|recognition|best paper|award for",
                         re.I)


def harvest_bios(roster):
    items = []
    for p in roster.people:
        bio = p.get("bio") or ""
        if len(bio) < 80 or not SECTION_RE.search(bio):
            continue
        parser = _BioParser()
        parser.feed(bio)
        parser._flush()
        section, sub = None, None
        for ev in parser.events:
            if ev[0] == "heading":
                if STOP_RE.search(ev[1]) and not SECTION_RE.search(ev[1]):
                    section, sub = None, None
                elif SECTION_RE.search(ev[1]):
                    if section is None or re.search(r"publication|grant|patent|presentation", ev[1], re.I):
                        section, sub = ev[1], None
                    else:
                        sub = ev[1]
                continue
            if not section:
                continue
            text, links = ev[1], ev[2]
            if len(text) < 25:
                continue
            try:
                c = parse_citation(text, links)
            except Exception as e:  # noqa: BLE001  one odd entry must never stop the run
                log(f"  ! could not read a bio entry for {p['full_name']}: {e}")
                continue
            kind = type_from_text(sub or "", section) if (sub or not re.search(r"^publications?$", section, re.I)) \
                else type_from_text(text)
            if kind == "Grant" and (HONOR_WORDS.search(text) or not GRANT_WORDS.search(text + " " + section)):
                kind = "Other"                    # prizes and honors listed under "Awards" aren't grants
            if kind == "Paper (venue type unclear)" and re.search(r"journal|vol\.|\d+\(\d+\)", text, re.I):
                kind = "Journal article"
            items.append(new_item(p["key"], "Dept bio", item_type=kind, title=c["title"], year=c["year"],
                                  authors=c["authors"], doi=c["doi"], url=c["url"] or (f"https://doi.org/{c['doi']}" if c["doi"] else ""),
                                  amount=c["amount"] if kind == "Grant" else "", role=c["role"] if kind == "Grant" else "",
                                  citation_as_listed=text[:1500], verified=c["clean"],
                                  confidence="Medium (self-reported in faculty bio)" if c["clean"] else
                                  "Low (bio entry could not be read cleanly; see CitationAsListed)"))
    STATS["bio_items"] = len(items)
    log(f"Faculty bios: {len(items)} self-reported items")
    return items


# ----------------------------------------------------------------------------- uploaded / manual items

IMPORT_FIELDS = ["person", "ItemType", "ItemTitle", "Year", "Venue / Funder", "Authors / Investigators", "Role",
                 "Amount (USD)", "AwardID / PatentNo", "DOI", "URL", "Sources", "Confidence", "ScholarCitations",
                 "CitationAsListed", "Abstract", "AbstractSource", "FullTextURL", "FullTextType",
                 "OpenAccessStatus", "added_by", "added_on"]


def load_imported(path, roster):
    """data/imported_items.csv: items added through uploads (see inbox.py)."""
    items = []
    for r in read_csv(path):
        if r["person"] not in roster.by_key:
            continue
        srcs = [s.strip() for s in re.split(r"[;,]", r.get("Sources") or "") if s.strip()] or ["Manual"]
        known = [s for s in srcs if s in ("Google Scholar", "Dept bio", "Crossref", "ORCID", "NSF", "NIH",
                                          "CUNY Academic Works", "OpenAlex")]
        first = "Google Scholar" if "Google Scholar" in srcs else (known[0] if known else "Manual")
        conf = r.get("Confidence", "")
        it = new_item(r["person"], first, item_type=r.get("ItemType") or type_from_text(r.get("Venue / Funder", "")),
                      title=r.get("ItemTitle", ""), year=r.get("Year", ""), venue=r.get("Venue / Funder", ""),
                      authors=r.get("Authors / Investigators", ""), role=r.get("Role", ""),
                      amount=r.get("Amount (USD)", ""), award_id=r.get("AwardID / PatentNo", ""), doi=r.get("DOI", ""),
                      url=r.get("URL", ""), confidence=conf, scholar_citations=r.get("ScholarCitations", ""),
                      citation_as_listed=r.get("CitationAsListed", ""), abstract=r.get("Abstract", ""),
                      abstract_source=r.get("AbstractSource", ""), fulltext_url=r.get("FullTextURL", ""),
                      fulltext_type=r.get("FullTextType", ""), oa_status=r.get("OpenAccessStatus", ""),
                      verified=conf.startswith(("High", "Medium")) or not conf)
        it["sources"] = [first] + [s for s in srcs if s != first]
        items.append(it)
    STATS["imported_items"] = len(items)
    return items
