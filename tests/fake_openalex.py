"""A tiny fake OpenAlex so tests run offline. Shapes match real API responses."""
INST = "I76513827"


def author(name, aid, at_citytech=True, orcid=None):
    inst = f"https://openalex.org/{INST}" if at_citytech else "https://openalex.org/I999"
    return {"author": {"id": f"https://openalex.org/{aid}", "display_name": name, "orcid": orcid},
            "institutions": [{"id": inst}]}


def work(i, title, year, authors, topics=(), abstract=""):
    return {"id": f"https://openalex.org/W{i}", "doi": f"https://doi.org/10.1/{i}",
            "display_name": title, "publication_date": f"{year}-03-01", "publication_year": year,
            "type": "article", "primary_location": {"source": {"display_name": "Journal X"}},
            "cited_by_count": 3, "authorships": authors,
            "topics": [{"display_name": t, "subfield": {"display_name": s}, "score": sc} for t, s, sc in topics],
            "keywords": [],
            "abstract_inverted_index": {w: [k] for k, w in enumerate(abstract.split())} if abstract else None}


def default_works():
    citytech = [
        work(1, "Machine learning for galaxy spectra", 2025, [author("Viviana Acquaviva", "A1")]),
        work(2, "Deep learning for ocean carbon", 2024, [author("V. Acquaviva", "A1")]),
        work(3, "Neural network emulators", 2023, [author("Viviana Acquaviva", "A1")]),
        work(4, "Random forests in cosmology", 2022, [author("Viviana Acquaviva", "A1")]),
        work(5, "AI ethics in climate science", 2025, [author("Viviana Acquaviva", "A1")]),
        work(6, "Quantum entanglement of qubits", 2020, [author("Oleg Berman", "A2")],
             [("Quantum Information and Cryptography", "Artificial Intelligence", .9)]),
        work(7, "Place-Based Learning as a High Impact Educational Practice", 2020,
             [author("Sean P. Macdonald", "A3")], abstract="deep learning for students in classrooms"),
        *[work(10 + k, f"Federated learning study {k}", 2025, [author("Yuwen Chen", "A9")]) for k in range(3)],
        work(20, "Edge computing survey", 2024, [author("Yu-Wen Chen", "A10")]),
        work(21, "Student poster on image classification", 2025, [author("Some Student", "A11")]),
        work(32, "Graph theory note", 2022, [author("Lin Zhou", "A5")]),
    ]
    elsewhere = [
        work(30, "Deep learning for flood forecasting in Florida", 2021, [author("Lin Zhou", "A5", False)]),
        work(31, "YOLO bridge inspection", 2023, [author("Lin Zhou", "A5", False)]),
    ]
    return citytech, elsewhere


def make_fake_get(citytech, elsewhere):
    def fake_get(url, params=None, accept_json=True, tries=4):
        if "/institutions/" in url:
            return {"id": f"https://openalex.org/{INST}", "display_name": "City Tech", "works_count": len(citytech)}
        f = (params or {}).get("filter", "")
        if f.startswith("institutions.id"):
            res = citytech
        else:
            ids = set(f.split(":", 1)[1].split(",")[0].split("|"))
            res = [w for w in citytech + elsewhere
                   if any(a["author"]["id"].split("/")[-1] in ids for a in w["authorships"])]
        page = params.get("page", 1)
        return {"meta": {"count": len(res)}, "results": res[(page - 1) * 200: page * 200]}
    return fake_get
