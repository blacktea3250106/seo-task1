"""用統一技術總表（normalized.json）重算各版本的可信 SEO 技術數、Token、秒。不叫模型、不連網。
用法：python3 docs/research/credible-rescore/rescore.py
"""
import collections, itertools, json, os
D = os.path.dirname(os.path.abspath(__file__))
N = json.load(open(f"{D}/normalized.json", encoding="utf-8"))
key = json.load(open(f"{D}/key72.json", encoding="utf-8"))
labels = json.load(open(f"{D}/labels72.json", encoding="utf-8"))
tax = {t["id"]: t["type"] for t in N["taxonomy"]}

def label(d):
    hits = [(s, n) for s, n in labels if s in d]
    return max(hits, key=lambda x: len(x[0]))[1] if hits else "?"

g = collections.defaultdict(list)
for k, v in key.items():
    r = N["reports"].get(k, {})
    if r.get("excluded") or v["dir"].endswith("/merged"):
        continue
    mm = (v["model"] or "") + v["dir"]
    m = "opus" if "opus" in mm else ("fable" if "fable" in mm else "sonnet")
    it = set(r.get("items", []))
    g[(m, label(v["dir"]))].append(dict(run=v["dir"], items=it, tok=v["tokens"], sec=v["secs"],
                                         status=v["status"], untrusted=v["untrusted"]))

def avg(xs):
    xs = [x for x in xs if x]
    return sum(xs) / len(xs) if xs else None

print("模型\t版本\t份數\t單份平均可信技術數\t其中手法\t任 2 份聯集\t平均 Token\t平均秒")
for (m, lab), v in sorted(g.items(), key=lambda x: (x[0][0], -avg([len(y["items"]) for y in x[1]]))):
    ok = [x for x in v if not x["untrusted"]]
    pairs = list(itertools.combinations(ok, 2))
    u2 = sum(len(a["items"] | b["items"]) for a, b in pairs) / len(pairs) if pairs else None
    tok, sec = avg([x["tok"] for x in ok]), avg([x["sec"] for x in ok])
    print(f"{m}\t{lab}\t{len(ok)}\t{avg([len(x['items']) for x in ok]) or 0:.1f}\t"
          f"{avg([sum(tax[i] == '手法' for i in x['items']) for x in ok]) or 0:.1f}\t"
          f"{'' if u2 is None else f'{u2:.1f}'}\t{'' if tok is None else f'{tok/1e3:.0f}k'}\t{'' if sec is None else f'{sec:.0f}'}")
