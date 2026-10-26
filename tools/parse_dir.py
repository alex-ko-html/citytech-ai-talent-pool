import pymupdf, re, sys, csv, glob, os, collections
TITLE_RE = re.compile(r"PROFESSOR|LECTURER|CHAIR|INSTRUCTOR|TECH|DIRECTOR|COORDINATOR|DEAN|SUBSTITUTE|VISITING|EMERIT|FELLOW|ASSISTANT|ASSOCIATE|ADJUNCT", re.I)
NAV = {"FULL-TIME FACULTY","ADJUNCT FACULTY","STAFF","PART-TIME FACULTY","CONTACT US","MEET THE CHAIR","APPLY NOW"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._\-]+@citytech\.cuny\.edu", re.I)

def spans(pg):
    out=[]
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines",[]):
            for s in l["spans"]:
                t=s["text"].strip()
                if t: out.append(dict(x=s["bbox"][0],y=s["bbox"][1],size=round(s["size"],1),bold="Bold" in s["font"],font=s["font"],t=t))
    return out

def dept_of(doc):
    for pg in doc:
        for s in spans(pg):
            if s["size"]>=18 and s["t"].isupper() and s["t"]!="DEPARTMENT DIRECTORY": return s["t"].title()
    for pg in doc:
        m=re.search(r"Departments \(/saas/departments\.aspx\) / ([^(]+) \(", pg.get_text())
        if m: return m.group(1).strip()
    return ""

def is_name(s):
    return s["bold"] and s["size"]>=8.5 and s["x"]>150 and s["t"].isupper() and s["t"] not in NAV \
        and not s["t"].startswith("(") and "@" not in s["t"] and not re.search(r"\d", s["t"]) and len(s["t"])>1

def parse(path):
    doc=pymupdf.open(path); dept=dept_of(doc); people=[]; pending=[]
    fname=re.sub(r"^[0-9a-f]{8}-","",os.path.basename(path))
    for pno,pg in enumerate(doc):
        S=spans(pg)
        titles=[s for s in S if not s["bold"] and 6<=s["size"]<=7.5 and "Roboto" in s["font"] and s["t"].isupper() and TITLE_RE.search(s["t"])]
        names=[s for s in S if is_name(s)]
        used=set(); claimed=set()
        def full_title(ti):
            title=ti["t"]; y=ti["y"]
            while True:
                nx=[s for s in S if not s["bold"] and abs(s["x"]-ti["x"])<3 and 0<s["y"]-y<12 and s["size"]==ti["size"] and s["t"].isupper()]
                if not nx: return title
                used.add(id(nx[0])); title+=" "+nx[0]["t"]; y=nx[0]["y"]
        def name_chain(nm):
            parts=[nm]
            while True:
                up=[s for s in names if abs(s["x"]-parts[0]["x"])<3 and 0<parts[0]["y"]-s["y"]<=16 and s["size"]==parts[0]["size"]]
                if not up: break
                parts.insert(0,up[0])
            for p in parts: claimed.add(id(p))
            return " ".join(p["t"] for p in parts)
        for ti in sorted(titles,key=lambda s:(s["y"],s["x"])):
            if id(ti) in used: continue
            above=[s for s in names if abs(s["x"]-ti["x"])<3 and 0<ti["y"]-s["y"]<22]
            title=full_title(ti)
            em=sorted([s for s in S if s["bold"] and 10<s["x"]-ti["x"]<20 and 0<s["y"]-ti["y"]<95 and s["size"]<=7.5],key=lambda s:s["y"])
            blob=re.sub(r"\s+","","".join(s["t"] for s in em))
            mm=EMAIL_RE.search(blob.split("(mailto")[0]) or EMAIL_RE.search(blob)
            pos=mm.group(0).lower() if mm else ""
            if above:
                people.append(dict(raw_name=name_chain(max(above,key=lambda s:s["y"])),title=title,department=dept,file=fname,page=pno+1,pos_email=pos))
            elif ti["y"]<260:   # card split across pages: name at bottom of previous page
                m=[p for p in pending if abs(p[0]-ti["x"])<3]
                if m:
                    pending.remove(m[0])
                    people.append(dict(raw_name=m[0][1],title=title,department=dept,file=fname,page=pno,pos_email=pos))
        pending=[]
        for nm in sorted(names,key=lambda s:-s["y"]):
            if id(nm) in claimed or nm["y"]<550: continue
            pending.append((nm["x"],name_chain(nm)))
    return people

if __name__=="__main__":
    allp=[]
    for f in sorted(glob.glob(sys.argv[1]+"/*.pdf")):
        p=parse(f); allp+=p
        print(f"{len(p):4d}  {p[0]['department'] if p else '?':28s} {re.sub(r"^[0-9a-f]{8}-","",os.path.basename(f))}")
    with open("raw_people.csv","w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=list(allp[0].keys())); w.writeheader(); w.writerows(allp)
    print("total",len(allp))

import unicodedata
def toks(s):
    s="".join(c for c in unicodedata.normalize("NFKD",s) if not unicodedata.combining(c)).lower()
    return [t for t in re.split(r"[^a-z]+",s) if t]
def file_emails(path):
    flat=re.sub(r"\s+","","".join(pg.get_text() for pg in pymupdf.open(path)))
    return sorted({e.lower() for e in re.findall(r"([A-Za-z0-9._\-]+@citytech\.cuny\.edu)",flat)})
def email_for(name, emails):
    t=toks(name)
    if len(t)<2: return ""
    first,last=t[0],t[-1]; allj="".join(t)
    best,score="",0
    for e in emails:
        loc=re.sub(r"\d+","",e.split("@")[0]); parts=[p for p in re.split(r"[.\-_]",loc) if p]; j="".join(parts)
        s=0
        if loc==f"{first}.{last}" or j==first+last: s=5
        elif j==first[0]+last or j==first[0]+"".join(t[1:]): s=4
        elif parts and parts[0]==first and last in j: s=4
        elif j and (j in allj or allj.startswith(j)) and len(j)>4: s=3
        elif last in j and j.startswith(first[0]): s=2
        if s>score: best,score=e,s
    return best

import difflib
def score_email(name,e):
    t=toks(name)
    if len(t)<2: return 0
    first,last=t[0],t[-1]; allj="".join(t)
    loc=re.sub(r"\d+","",e.split("@")[0]); parts=[p for p in re.split(r"[.\-_]",loc) if p]; j="".join(parts)
    if loc==f"{first}.{last}" or j==first+last: return 5
    if j==first[0]+last or j==first[0]+"".join(t[1:]): return 4
    if parts and parts[0]==first and last in j: return 4
    if j and len(j)>4 and (j in allj or allj.startswith(j)): return 3
    if last in j and j.startswith(first[0]): return 2
    r=max(difflib.SequenceMatcher(None,j,c).ratio() for c in (first+last,first[0]+last,allj))
    return 1 if r>=0.75 else 0

def assign_emails(ppl, ems):
    taken=set()
    for p in ppl:
        if p.get("pos_email") and score_email(p["raw_name"],p["pos_email"])>=1:
            p["email"]=p["pos_email"]; taken.add(p["email"])
    for p in ppl:
        if p.get("email"): continue
        c=sorted(((score_email(p["raw_name"],e),e) for e in ems if e not in taken),reverse=True)
        p["email"]=c[0][1] if c and c[0][0]>=1 else ""
        if p["email"]: taken.add(p["email"])
    for p in ppl: p.pop("pos_email",None)
