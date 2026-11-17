"""評分器先驗證會拒絕錯誤，再拿來比較（需求 3；CLAUDE.md「先驗證評估器會拒絕錯誤」）。"""
import json

import pytest

from seo_agent import ROOT
from seo_agent.grader import dimensions, grade, load_rubric

CAL = ROOT / "eval" / "calibration"
RUBRIC = load_rubric()


@pytest.mark.parametrize("name", list(RUBRIC["calibration"]["files"]))
def test_matches_manual_comparison(name):
    got = grade((CAL / name).read_text(encoding="utf-8"))["marks"]
    assert got == RUBRIC["calibration"]["files"][name]


def test_old_a_scores_low():
    r = grade((CAL / "A-v2-harness.md").read_text(encoding="utf-8"))
    assert r["total"] <= RUBRIC["calibration"]["A-v2-harness.md"]["expect_total_at_most"]


def test_b_sitemap_mistake_is_caught():
    r = grade((CAL / "B-opus-direct.md").read_text(encoding="utf-8"))
    assert "T10" in r["wrong"]
    quote = next(i["quote"] for i in r["items"] if i["id"] == "T10")
    assert "沒有 sitemap" in quote or "不在任何 sitemap" in quote


def test_rejects_wrong_and_hedged_statements():
    assert grade("娛樂城區沒有 sitemap。")["wrong"] == ["T10"]
    assert grade("/wordcup/ 不在任何 sitemap 裡。")["wrong"] == ["T10"]
    hedged = grade("這些數字不證明 /wordcup/ 沒有其他 sitemap。")
    assert hedged["wrong"] == [] and hedged["items"][9]["mark"] == "p"
    assert grade("/wordcup/sitemap.xml 有 2,503 筆")["items"][9]["mark"] == "y"
    assert grade("")["total"] == 0


def test_unknown_and_failed_check_lines_do_not_score():
    md = ("# 報告\n## 對方策略\n- 網域在 2026-04-15 重新註冊\n## 未知與限制\n- 未確認 iftomm2015.tw 是否 301 導入\n"
          "### 細項\n- /wordcup/ 約 2,503 頁（未查）\n## 我方建議\n- [未知] 論壇只有 1 位會員\n- [檢查未通過] 舊網址被重建\n")
    r = grade(md)
    assert r["marks"][5] == "y" and r["total"] == 1


def test_deterministic():
    text = (CAL / "gemini.md").read_text(encoding="utf-8")
    assert grade(text) == grade(text)


def test_dimensions_on_structured_run(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "E1.html").write_text("x")
    (tmp_path / "evidence.jsonl").write_text(json.dumps({"id": "E1", "file": "raw/E1.html"}) + "\n"
                                             + json.dumps({"id": "E2", "file": "raw/missing.html"}) + "\n")
    rep = {"strategy": [{"id": "S1", "kind": "fact", "text": "網域在 2026-04-15 重新註冊", "evidence_ids": ["E1"]}],
           "evidence": [{"id": "V1", "kind": "fact", "text": "選單沒有壞連結", "evidence_ids": ["E2"]},
                        {"id": "V2", "kind": "inference", "text": "可能買了舊網域", "evidence_ids": ["E1"]}],
           "unknowns": [], "actions": [{"action": "a", "based_on": ["S1"]}, {"action": "b", "based_on": ["X9"]}]}
    (tmp_path / "report.json").write_text(json.dumps({"meta": {"unresolved_issues": ["x"]}, "report": rep}))
    (tmp_path / "report.md").write_text("網域在 2026-04-15 重新註冊")
    d = dimensions(tmp_path)
    assert d["完整度"]["score"] == 1
    assert d["可追溯"]["claims_with_existing_evidence"] == {"ok": 2, "of": 3, "rate": 0.667}
    assert d["誠實度"]["absolute_scoped_2ev"]["ok"] == 0 and d["誠實度"]["inference_with_limits"]["ok"] == 0
    assert d["建議有根據"]["actions_based_on_valid_claims"]["ok"] == 1
    assert d["新發現"]["claims_outside_14"] == 2
    assert d["正確度"]["check_issues_left"] == ["x"]
