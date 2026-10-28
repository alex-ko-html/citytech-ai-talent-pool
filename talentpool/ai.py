"""Decides whether an item is about AI (rules only, no AI model), and ranks people into tiers.
Calibrated against real City Tech data; see DECISIONS.md before changing anything here."""
import re
import time
from collections import defaultdict

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


def tag_items(items):
    for it in items:
        row = {"title": it["title"], "abstract": it["abstract"], "keywords": it["keywords"], "topics": it["topics"]}
        it["is_ai"], themes, it["ai_evidence"] = classify_ai(row)
        it["ai_themes"] = "; ".join(themes)


def tier_people(people, items, confirmed):
    """Expertise tier per person, counted on confirmed items only (High/Medium confidence).
    Unconfirmed same-name items can only produce "Needs review"."""
    this_year = time.localtime().tm_year
    by_person = defaultdict(list)
    for it in items:
        if it["is_ai"] and not it["excluded_reason"]:
            by_person[it["person"]].append(it)
    out = {}
    for p in people:
        ai = by_person.get(p["key"], [])
        ver = [i for i in ai if confirmed(i)]
        unver = [i for i in ai if not confirmed(i)]
        years = [int(i["year"]) for i in ver if str(i["year"]).isdigit()]
        recent = sum(1 for y in years if y >= this_year - RECENT_YEARS + 1)
        tier = next((t for t, n, rc in TIERS if len(ver) >= n and recent >= rc), "")
        if not tier and len(unver) >= 2:
            tier = REVIEW_TIER
        counts = defaultdict(int)
        for i in (ver or unver):
            for t in i["ai_themes"].split("; "):
                if t:
                    counts[t] += 1
        out[p["key"]] = {"tier": tier, "ai_confirmed": len(ver), "ai_recent": recent, "ai_unconfirmed": len(unver),
                         "ai_areas": [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:4]}
    return out
