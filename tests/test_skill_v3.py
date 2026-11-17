"""Skill v5 文字測試（決策 #71：研究方式自己決定；⑥ 審查、⑧ 經驗保留）＋洩題檢查。"""
import re

from seo_agent.grader import load_rubric
from seo_agent.research import SKILL_PATH, TASK

SKILL = SKILL_PATH.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return SKILL.split(start, 1)[1].split(end, 1)[0]
def test_banned_words_absent():
    for w in ("猜測", "候選", "正式", "disable", "差點判斷錯", "hypothesis", "research_log", "疑點", "question_id"):
        assert w not in SKILL, w
    assert "猜測" not in TASK and "submit_report" in TASK and "research_log" not in TASK


def test_research_section_gives_facts_not_procedure():
    s = _section("## 研究", "## 經驗筆記")
    for w in ("由你決定", "120 分鐘", "time_used", "20 分鐘", "連續 5 次", "sections_not_yet_read", "`why`",
              "Evidence ID", "fact", "inference", "limits", "unknowns", "另一種方法", "Tool 錯誤回傳不算確認", "外部說法"):
        assert w in s, w


def test_experience_notes_rules():  # 照走／別走、why 登記、報告推翻
    s = _section("## 經驗筆記", "## 交報告")
    for w in ("照走", "重新取證", "別走（查不到）", "輕試 1 次", "別走（會誤導）", "不重試", "`why`", "EXP-001",
              "experience.overturned", "不能自己下架"):
        assert w in s, w


def test_report_and_independent_review():  # ⑥ 一次審查＋修一次
    s = _section("## 交報告", "## 報告被接受後")
    for key in ("summary", "onpage", "offpage", "actions", "unknowns", "experience"):
        assert f"`{key}`" in s, key
    for w in ("5 段", "獨立的審查 Agent", "待修清單", "修一次", "不會有第二次審查", "補查", "重抓即時資料", "格式檢查"):
        assert w in s, w


def test_route_template_kept():  # ⑧ 經驗格式
    s8 = SKILL.split("## 報告被接受後", 1)[1]
    for w in ("照走", "別走", "查不到", "會誤導", "paired_id", "evidence_ids", "不能下架",
              "<Tool 名稱>：<做什麼>，因為 <為什麼>", "2–4 步", "一步一行", "90 字", "退回重寫"):
        assert w in s8, w




def test_no_rubric_leak():
    text = SKILL + TASK
    for item in load_rubric()["items"]:
        assert item["point"] not in text, item["id"]
        for k in ("full", "partial", "wrong"):
            for frag in (item.get(k) or []) if isinstance(item.get(k), list) else [item.get(k) or ""]:
                if len(frag) >= 8:
                    assert frag not in text, (item["id"], frag)
    assert not re.search(r"\bT(0[1-9]|1[0-4])\b", text)
