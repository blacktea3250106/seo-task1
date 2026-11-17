"""每個 run 的獨立 Hermes home。必須在 import Hermes 之前設定，否則 Hermes 會建立 ~/.hermes。"""
from __future__ import annotations

from pathlib import Path

from . import ROOT

# 訂閱登入（SEO_MODEL_AUTH=oauth，決策 #62）：使用者只在這裡登入一次（指令見 README；先建 config.yaml 再登入，
# 登入時才會套用 adopt_external_logins: false）
# 每個 run 的 home 放在 .hermes-auth/profiles/<run_id>：Hermes 的 profile 模式會讀上層的 auth.json，
# 加鎖並把換新的 token 寫回上層，所以不用自己複製登入檔。
AUTH_HOME = ROOT / ".hermes-auth"

# tool_search off：專案工具直接提供給模型（不藏在搜尋工具後面）
# adopt_external_logins false：不借用本機 ~/.claude、~/.codex 的登入（避免輪替 token 把開發用 CLI 登出）
CONFIG_YAML = """\
tools:
  tool_search:
    enabled: "off"
auth:
  adopt_external_logins: false
"""


def prepare_run_home(run_home: Path) -> Path:
    run_home.mkdir(parents=True, exist_ok=True)
    (run_home / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    return run_home


def run_home_parent(auth: str, auth_home: Path = AUTH_HOME) -> Path:
    """api_key：.hermes-runs/<run_id>（每輪全新）；oauth：<auth_home>/profiles/<run_id>（共用上層登入）。"""
    if auth != "oauth":
        return ROOT / ".hermes-runs"
    prepare_run_home(auth_home)  # 上層也要有 config.yaml，Hermes 才認得它是 home（登入前請先建，見 README）
    return auth_home / "profiles"


if __name__ == "__main__":  # 登入前先建上層 config.yaml：uv run python -m seo_agent.hermes_home
    run_home_parent("oauth")
    print(f"已建立 {AUTH_HOME / 'config.yaml'}；接著執行 HERMES_HOME=.hermes-auth uv run hermes auth add anthropic")
