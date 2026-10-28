"""Shared helpers: HTTP with retries, name/title/DOI normalization, logging."""
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



def post_json(url, body, tries=4):
    for attempt in range(tries):
        try:
            r = SESSION.post(url, json=body, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == tries - 1:
                log(f"  ! request failed: {url} ({e})")
    REQUEST_FAILURES[re.sub(r"^https?://([^/]+).*", r"\1", url)] += 1
    return None


def title_tokens(t):
    return {w for w in norm_title(t).split() if len(w) > 2}


def similar_titles(a, b, threshold=0.8):
    """Fuzzy title match for citations typed by hand (bios, uploads)."""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    if len(ta) < 4 or len(tb) < 4:
        return norm_title(a) == norm_title(b)
    return len(ta & tb) / min(len(ta), len(tb)) >= threshold


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
                for r in csv.DictReader(f)]


def write_csv(path, rows, fields):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
