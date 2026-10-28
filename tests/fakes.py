"""Offline stand-ins for every outside service, shaped like the real responses (Oct 2026)."""
import json
import re

INST = "I76513827"
MENDOZA_BIO = """<h4><strong>Education:</strong></h4><ul><li>Ph.D., Computer Science, 2008</li></ul>
<h4><strong>Publications:</strong></h4><p><strong>Journal Papers</strong></p><ul>
<li><strong>Benito Mendoza</strong>, Afroza Aktar, Lili Ma. (2025)&nbsp;Towards AI-Driven Academic Advising: Lessons from a
Domain-Specific Chatbot. Journal of Computing Sciences in Colleges, 41(3), 230-245. DOI: 10.5555/3801163.3801223</li>
<li>Laura Zavala and <strong>Benito Mendoza</strong> (2023) &quot;An LOD-based Approach to Generating Programming Problems.&quot;
Journal of Computing Sciences in Colleges. 39, 3, 295-305.</li></ul>
<p><strong>Conference Presentations</strong></p><ul><li>B. Mendoza (2024). Teaching robotics with ROS 2. Invited talk, CUNY IT Conference, 2024.</li></ul>
<h4>Grants:</h4><ul><li>PSC-CUNY Research Award, PI, "Chatbots for advising" (2024), $6,000</li></ul>"""

STAFF = [
    # dept 30 = Computer Engineering Technology
    dict(Dept_ID=30, First_name="Benito", Last_name="Mendoza", Middle_initial="", Title="Associate Professor",
         Email="BMendoza@citytech.cuny.edu", Room_number="V-626", Bio=MENDOZA_BIO, Phone="718-000-0000"),
    dict(Dept_ID=30, First_name="Sunghoon", Last_name="Jang", Title="Chair", Email="SJang@citytech.cuny.edu",
         Room_number="V-635", Bio=None, CellPhone="917-000-0000"),
    dict(Dept_ID=30, First_name="Adam", Last_name="Adjunct", Title="Adjunct Lecturer", Email="aadj@citytech.cuny.edu"),
    dict(Dept_ID=30, First_name="Olive", Last_name="Office", Title="CUNY Office Assistant", Email="oo@citytech.cuny.edu"),
    # dept 76 = Physics
    dict(Dept_ID=76, First_name="Viviana", Last_name="Acquaviva", Title="Professor", Email="VAcquaviva@citytech.cuny.edu",
         Room_number="N-828", Bio="<h4>Research Interests:</h4><ul><li>machine learning and AI for climate</li></ul>"),
    # dept 59 = Mathematics
    dict(Dept_ID=59, First_name="Lin", Last_name="Zhou", Title="Professor", Email="lzhou@citytech.cuny.edu"),
]
DEPT_IDS = {"computer-engineering": 30, "physics": 76, "mathematics": 59}


def author(name, aid, citytech=True):
    return {"author": {"id": f"https://openalex.org/{aid}", "display_name": name, "orcid": None},
            "institutions": [{"id": f"https://openalex.org/{INST if citytech else 'I999'}"}]}


def work(i, title, year, authors, wtype="article", stype="journal", venue="Journal X", abstract="", topics=()):
    return {"id": f"https://openalex.org/W{i}", "doi": f"https://doi.org/10.1/{i}" if i != 5 else "https://doi.org/10.5555/3801163.3801223",
            "display_name": title, "publication_date": f"{year}-03-01", "publication_year": year, "type": wtype,
            "primary_location": {"source": {"display_name": venue, "type": stype}},
            "best_oa_location": {"pdf_url": f"https://example.org/{i}.pdf"} if i % 2 else None,
            "open_access": {"oa_status": "gold" if i % 2 else "closed"}, "cited_by_count": 4,
            "authorships": authors, "topics": [{"display_name": t, "subfield": {"display_name": s}, "score": sc} for t, s, sc in topics],
            "keywords": [], "abstract_inverted_index": {w: [k] for k, w in enumerate(abstract.split())} if abstract else None}


def default_works():
    ct = [
        work(1, "Machine learning for galaxy spectra", 2025, [author("Viviana Acquaviva", "A1")]),
        work(2, "Deep learning for ocean carbon", 2024, [author("V. Acquaviva", "A1")]),
        work(3, "Neural network emulators of radiative transfer", 2023, [author("Viviana Acquaviva", "A1")]),
        work(4, "Random forests in cosmology", 2022, [author("Viviana Acquaviva", "A1")]),
        work(6, "Large language models for data analysis", 2025, [author("Viviana Acquaviva", "A1")], stype="conference",
             venue="Proceedings of the AAAI Conference"),
        work(5, "Towards AI-Driven Academic Advising: Lessons from a Domain-Specific Chatbot", 2025,
             [author("Benito Mendoza", "A2"), author("Lili Ma", "A7")]),
        work(7, "An IoT-enabled smart elderly living environment", 2020, [author("Sunghoon Jang", "A3")]),
        work(8, "Erratum to: An IoT-enabled environment", 2020, [author("Sunghoon Jang", "A3")], wtype="erratum"),
        work(9, "Graph theory note", 2022, [author("Lin Zhou", "A5")]),
        work(10, "A poster by a student", 2025, [author("Some Student", "A11")]),
    ]
    other = [work(30, "Deep learning for flood forecasting in Florida", 2021, [author("Lin Zhou", "A5", False)]),
             work(31, "YOLO bridge inspection with computer vision", 2023, [author("Lin Zhou", "A5", False)])]
    return ct, other


NSF = [{"id": "2519918", "title": "Machine learning for ocean carbon", "piFirstName": "Viviana", "piLastName": "Acquaviva",
        "piEmail": "vacquaviva@citytech.cuny.edu", "coPDPI": ["Benito Mendoza bmendoza@citytech.cuny.edu"],
        "startDate": "10/01/2025", "estimatedTotalAmt": "350000", "fundProgramName": "EPIIC",
        "abstractText": "We use machine learning and neural networks to reconstruct ocean carbon."}]
NIH = [{"appl_id": 111, "core_project_num": "R16AI000001", "project_title": "Smart sensors for elders", "fiscal_year": 2024,
        "principal_investigators": [{"full_name": "Sunghoon  Jang", "is_contact_pi": True}], "award_amount": 100000,
        "project_start_date": "2024-07-01T00:00:00", "agency_ic_admin": {"abbreviation": "NIA"}, "abstract_text": ""},
       {"appl_id": 112, "core_project_num": "R16AI000001", "project_title": "Smart sensors for elders", "fiscal_year": 2025,
        "principal_investigators": [{"full_name": "Sunghoon  Jang", "is_contact_pi": True}], "award_amount": 110000,
        "project_start_date": "", "agency_ic_admin": {"abbreviation": "NIA"}, "abstract_text": ""}]
AW_EMPTY = '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListSets></ListSets></OAI-PMH>'


class Resp:
    def __init__(self, status=200, text="", data=None):
        self.status_code, self.text, self._data = status, text, data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    headers = {}

    def __init__(self, staff=None, directory_up=True):
        self.staff, self.up = staff if staff is not None else STAFF, directory_up

    def get(self, url, params=None, timeout=None, headers=None):
        if not self.up:
            raise ConnectionError("directory down")
        m = re.search(r"citytech\.cuny\.edu/([a-z-]+)/directory\.aspx", url)
        if m:
            d = DEPT_IDS.get(m.group(1), 900 + len(m.group(1)))      # other departments: nobody listed
            return Resp(200, f"<script>var Dept_IDs = [{d}];</script>")
        if "faculty.aspx" in url:
            return Resp(404)
        if "/dashboard/odata/Employees" in url:
            did = int(params["$filter"].split()[-1])
            return Resp(200, data={"value": [dict(s) for s in self.staff if s["Dept_ID"] == did]})
        return Resp(404)


def make_get(ct, other, nsf=NSF):
    def get(url, params=None, accept_json=True, tries=4):
        if "/institutions/" in url:
            return {"id": f"https://openalex.org/{INST}", "display_name": "City Tech"}
        if "api.openalex.org/works" in url:
            f = params["filter"]
            if f.startswith("institutions.id"):
                res = ct
            else:
                ids = set(f.split(":", 1)[1].split("|"))
                res = [w for w in ct + other if any(a["author"]["id"].split("/")[-1] in ids for a in w["authorships"])]
            page = params.get("page", 1)
            return {"meta": {"count": len(res)}, "results": res[(page - 1) * 200: page * 200]}
        if "api.nsf.gov" in url:
            return {"response": {"award": nsf if params.get("offset", 1) == 1 else []}}
        if "academicworks" in url:
            return AW_EMPTY
        return None
    return get


def post_json(url, body, tries=4):
    return {"meta": {"total": len(NIH)}, "results": NIH if body.get("offset", 0) == 0 else []}
