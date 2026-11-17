"""文件檢查（G-39、G-41–G-44、G-55；README A 段「形成假設」說明）。"""
from seo_agent import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")
ARCH = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
LAYER4 = ("polite_fetch（禮貌抓網頁）", "sitemap_tree（sitemap 目錄樹）", "inspect_page（看單頁）", "text_match（文字比對）",
          "domain_info（WHOIS 等網域資料）", "wayback（舊網址存檔）", "web_search（網路搜尋）")


def test_architecture_tools_match_layer4():  # G-39、G-44
    for t in LAYER4:
        assert t in ARCH, t
    for w in ("人工把關", "評估", "Board", "網站底稿", "Reviewer Agent", "Grader Agent", "使用中", "已下架", "5 段報告", "sections_not_yet_read", "why"):
        assert w in ARCH, w
    for old in ("候選／正式／停用", "7 段報告", "研究日誌", "歷史存檔", "research_log", "4 種收尾", "C 方案"):
        assert old not in ARCH, old


def test_readme_assumption_and_decisions():  # 「假設」、G-42
    section_a = README.split("### A. Autonomous Research Agent", 1)[1].split("\n### ", 1)[0]
    row = next(line for line in section_a.splitlines() if "形成假設" in line)
    for w in ("`why`", "inference", "另一種方法確認"):
        assert w in row, w
    head = README.split("## Harness 實驗結果", 1)[0]
    for w in ("5 段", "使用中、已下架", "寫入審核", "reject", "experience.overturned", "Reviewer Agent", "不另加 Judge AI", "另類的 Judge AI"):
        assert w in head, w
    assert "7 段" not in head and "候選、正式、停用" not in head and "research_log 寫" not in head


def test_readme_limits_and_plan():  # G-41、G-43、G-55
    limits = README.split("## 目前限制", 1)[1].split("\n## ", 1)[0]
    for w in ("可能是運氣", "多塞引用", "表面功夫", "沒用到不會下架", "--refresh"):
        assert w in limits, w
    plan = README.split("## 若再有 4 週", 1)[1].split("\n## ", 1)[0]
    for n in range(1, 6):
        assert f"### 優先 {n}：" in plan, n
    for w in ("原型已提前做", "長期被擋", "sitemap index", "連續 3 個動作"):
        assert w in plan, w


def test_readme_example_commands_use_out():
    for line in README.splitlines():
        if "uv run" in line and ("seo_agent.sequence" in line or "seo_agent.decompose" in line or "seo_agent.cli run" in line):
            assert "--out" in line, line
