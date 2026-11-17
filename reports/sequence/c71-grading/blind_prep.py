"""C 方案成績表評分前置：報告遮名、打亂，複製到 grading/<代號>/。
Harness 帶 report.md＋evidence.jsonl＋raw/；One Shot 帶 report.md＋transcript.jsonl。對照表存 key.json，核對者看不到。
用法：python blind_prep.py <批次名> <arm=路徑> ...（路徑相對 reports/sequence/）"""
import json, random, re, shutil, sys
from pathlib import Path

O = Path(__file__).parent
SEQ = O.parent
batch, pairs = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
G = O / batch / "grading"
shutil.rmtree(G, ignore_errors=True)
codes = [f"R{n:02d}" for n in range(1, len(pairs) + 1)]
random.Random(f"c71-{batch}").shuffle(codes)
MASK = re.compile(r"(?im)^.*(sonnet|opus|fable|模型|model|run_id|版本|simulated|模擬|one.?shot|harness).*$\n?")
key = {}
for (arm, rel), c in zip(pairs, codes):
    d, g = SEQ / rel, G / c
    g.mkdir(parents=True)
    t = (d / "report.md").read_text(encoding="utf-8")
    head, sep, body = t.partition("\n## 1.")
    (g / "report.md").write_text(MASK.sub("", head) + sep + body, encoding="utf-8")
    for f in ("evidence.jsonl", "transcript.jsonl"):
        if (d / f).exists():
            shutil.copy(d / f, g / f)
    if (d / "raw").exists():
        shutil.copytree(d / "raw", g / "raw")
    key[c] = {"arm": arm, "dir": rel}
(O / batch / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2))
print(sorted(key))
