import sys,glob,os,csv,re,difflib,collections; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from parse_dir import *
U=(sys.argv[1] if len(sys.argv)>1 else "pdfs").rstrip("/")+"/"
PROGRAM={"theatre.pdf":"Theatre","world_languages.pdf":"World Languages","Department_Directory_communication.pdf":"Communication"}

def nice(n):
    n=re.sub(r"\s*-\s*","-",n.strip()); out=[]
    for w in n.split():
        if re.fullmatch(r"[A-Z]\.?",w): out.append(w if w.endswith(".") or len(w)>1 else w+"."); continue
        if w in ("JR.","JR"): out.append("Jr."); continue
        if w in ("II","III","IV"): out.append(w); continue
        def cap(p):
            p=p.capitalize()
            p=re.sub(r"^Mc([a-z])",lambda m:"Mc"+m.group(1).upper(),p)
            p=re.sub(r"^O'([a-z])",lambda m:"O'"+m.group(1).upper(),p)
            return p
        out.append("-".join(cap(p) for p in w.split("-")))
    return " ".join(out)

LIG=["fi","fl","ff","ffi","ffl"]
def repair(name,email):
    """Ligatures (fi, fl, ffi) were dropped from some emails in the PDFs. Rebuild them from the name."""
    if not email: return email,False
    loc,dom=email.split("@"); digits=re.search(r"\d*$",loc).group(0); base=loc[:len(loc)-len(digits)]
    t=toks(name)
    if len(t)<2: return email,False
    cands={f"{t[0]}.{t[-1]}", t[0][0]+t[-1], t[0][0]+"".join(t[1:]), f"{t[0]}.{''.join(t[1:])}", "".join(t[0][0]+''.join(t[1:-1]))+t[-1]}
    if base in cands: return email,False
    best=max(cands,key=lambda c:difflib.SequenceMatcher(None,base,c).ratio())
    r=difflib.SequenceMatcher(None,base,best).ratio()
    if any(l in best for l in LIG) and r>=0.7 and abs(len(best)-len(base))<=3:
        return f"{best}{digits}@{dom}",True
    return email,False

rows=[]
for f in sorted(glob.glob(U+"*.pdf")):
    ppl=parse(f); ems=[e for e in file_emails(f) if not re.match(r"^\d",e)]
    assign_emails(ppl,ems)
    adj="adjunct" in f.lower()
    for p in ppl:
        title=p["title"].title().replace(" Of "," of ").replace("Sub ","Substitute ")
        if adj or p["title"].startswith("ADJUNCT"):
            status="Adjunct (lab staff)" if "LAB TECH" in p["title"] else "Adjunct"
        else:
            status="Full-time (substitute)" if p["title"].startswith("SUB") else "Full-time"
        email,fixed=repair(p["raw_name"],p["email"])
        rows.append(dict(name=nice(p["raw_name"]),department=p["department"],program=PROGRAM.get(p["file"],""),
                         status=status,title=title,email=email,orcid="",openalex_id="",
                         source_file=p["file"],note="email rebuilt from name (PDF dropped letters)" if fixed else ("no email in PDF" if not email else "")))
FIX={"Reneta D. Lansiquot-Panagiotakis":("rlansiquot@citytech.cuny.edu","email matched by hand",""),
     "Duval Bodden Jr.":("dbodden@citytech.cuny.edu","email matched by hand",""),
     "Denise Scannell-Guida":("dscannell@citytech.cuny.edu","email matched by hand",""),
     "Marta Effinger-Crichlow":("marta.effinger-crichlow45@citytech.cuny.edu","email rebuilt from name (PDF dropped letters)",""),
     "Urmi Duttagupta":("ughosh-dastidar@citytech.cuny.edu","email suggests she also publishes as Urmi Ghosh-Dastidar; added as alias","Urmi Ghosh-Dastidar")}
for r in rows:
    r.setdefault("aka","")
    if r["name"] in FIX: r["email"],r["note"],r["aka"]=FIX[r["name"]]
# de-duplicate (same person on two pages / lists)
seen={}; final=[]
for r in rows:
    k=(r["email"] or r["name"].lower(), r["department"])
    if k in seen:
        if seen[k]["status"]!="Full-time" and r["status"]=="Full-time": seen[k].update(r)
        continue
    seen[k]=r; final.append(r)
order={"Full-time":0,"Full-time (substitute)":1,"Adjunct":2,"Adjunct (lab staff)":3}
final.sort(key=lambda r:(order[r["status"]],r["department"],r["name"].split()[-1]))
cols=["name","aka","department","program","status","title","email","orcid","openalex_id","source_file","note"]
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","roster.csv"),"w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(final)
print(len(rows),"parsed ->",len(final),"unique")
print(collections.Counter(r["status"] for r in final))
print(collections.Counter((r["department"],r["status"].split()[0]) for r in final))
for r in final:
    if r["note"]: print("  ",r["name"],"|",r["email"],"|",r["note"])
