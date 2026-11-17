"""新舊拆題法離線測試（G-33；決策 #29；補充三 ⑧）。

- 同一份資料卡（網站底稿產生的 data_card.md）交給模型，只做 ③ 拆題，不給 Tool、不上網。
- 舊法（骨架先）：先照 5 面各列 1 題，再自加題。新法（差異先）：先從資料卡列對不上的地方，再補手法清單與盲點，
  最後用 5 面當覆蓋檢查表補缺的面。
- 各跑 3 次（預設），輸出存檔給人工逐題對照「涵蓋幾項評分、有沒有想到網域歷史方向、白問的題數」。
- 評分表不給 AI 看：送出的內容只有任務、資料卡與拆題說明；送出前程式核對不含評分表任何一項的文字。
- 這是驗證 #29 的設計選擇，不是需求 2.3 的「比初始版本好」評估。模型用專案預設模型。

用法：
  uv run python -m seo_agent.decompose --card reports/runs/<run>/data_card.md          # 實跑（叫模型 6 次）
  uv run python -m seo_agent.decompose --card <data_card.md> --fake                    # 離線（假模型）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

from . import ROOT
from .grader import load_rubric

TASK = ("你在研究競品網站 {site} 的 SEO，目標關鍵字是 {keywords}。這一步只做「拆題」：列出接下來要研究的問題，"
        "不要回答、不要規劃怎麼查。下面是程式事先抓好的資料卡（只把各來源的數字並排，沒有標哪裡對不上）。\n\n{card}\n\n")
FACES = ("①網站身分與兩個關鍵字的關係　②兩個關鍵字各由哪些頁承接（On-page）　③網站規模、內容怎麼產生、哪部分值得查"
         "　④Off-page 訊號（含拿不到的）　⑤我方優先行動與排序理由")
METHODS = {
    "old": ("舊法（骨架先）：先照下面 5 面各寫 1 題，再視需要自加題。\n" + FACES + "\n"
            "每題一行：題目｜屬於哪一面｜答案會改變哪條建議。"),
    "new": ("新法（差異先）：\n"
            "1. 先從資料卡找出對不上的地方（例如選單有、sitemap 沒有；各分區日期範圍和網域註冊日對不上），每個寫成一題。\n"
            "2. 補盲點：用你自己的知識＋Google 官方垃圾內容政策名稱（例如過期網域濫用、量產內容、站點聲譽濫用）列手法清單，"
            "每項標已有線索／可用免費資料查／查不到。\n"
            "3. 最後用下面 5 面當覆蓋檢查表，缺哪一面就補一題。\n" + FACES + "\n"
            "每題一行：題目｜類型（差異／手法清單／一般判斷）｜屬於哪一面｜答案會改變哪條建議。"),
}
ModelFn = Callable[[str], dict]


def build_prompt(method: str, card: str, *, site: str = "https://2030.tw", keywords: str = "[娛樂城]、[3A娛樂城]") -> str:
    return TASK.format(site=site, keywords=keywords, card=card) + METHODS[method]


def leaked_rubric(prompt: str, rubric: dict | None = None) -> list[str]:
    """送出的內容不能含評分表的任何一項文字（point 全文）。"""
    rubric = rubric or load_rubric()
    return [i["id"] for i in rubric["items"] if i["point"] and i["point"] in prompt]


def anthropic_model() -> ModelFn:
    import anthropic

    from .model_env import load_model_settings
    m = load_model_settings()
    client = anthropic.Anthropic(api_key=m.api_key, base_url=m.base_url, timeout=600, max_retries=2)

    def call(prompt: str) -> dict:
        with client.messages.stream(model=m.model, max_tokens=8000, thinking={"type": "adaptive"},
                                    messages=[{"role": "user", "content": prompt}]) as s:
            msg = s.get_final_message()
        return {"text": "\n".join(b.text for b in msg.content if b.type == "text"), "model": m.model,
                "tokens": {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}}
    return call


def fake_model(prompt: str) -> dict:
    method = "new" if "差異先" in prompt else "old"
    return {"text": f"（假模型）{method}：Q1｜…｜…", "model": "fake", "tokens": {"input": 0, "output": 0}}


def run_compare(card_path: Path, out_dir: Path, *, model: ModelFn, repeats: int = 3) -> dict:
    card = Path(card_path).read_text(encoding="utf-8")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = {m: build_prompt(m, card) for m in METHODS}
    for m, p in prompts.items():
        if leaked := leaked_rubric(p):
            raise ValueError(f"{m} 的送出內容含評分表文字：{leaked}")
    runs = []
    for i in range(1, repeats + 1):
        for m in METHODS:  # 舊、新交錯跑，避免時段差異都落在同一法
            out = model(prompts[m])
            name = f"{m}-{i}.md"
            (out_dir / name).write_text(out["text"], encoding="utf-8")
            runs.append({"method": m, "n": i, "file": name, "model": out.get("model"), "tokens": out.get("tokens")})
    summary = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "card": str(card_path), "repeats": repeats,
               "prompts": prompts, "runs": runs,
               "manual_check": "人工逐題對照：涵蓋幾項評分、有沒有想到網域歷史方向、白問的題數（評分表不給 AI 看）"}
    (out_dir / "decompose.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--card", type=Path, required=True, help="資料卡 data_card.md")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--fake", action="store_true", help="離線假模型")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    out = a.out or ROOT / "reports" / "decompose" / time.strftime("%Y%m%d-%H%M%S")
    s = run_compare(a.card, out, model=fake_model if a.fake else anthropic_model(), repeats=a.repeats)
    print(json.dumps({"out": str(out), "runs": len(s["runs"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
