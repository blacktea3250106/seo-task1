"""第 1 步骨架的離線測試（不呼叫模型）。"""
import json
import subprocess
import sys

import pytest

from seo_agent import ROOT
from seo_agent.hermes_home import prepare_run_home, run_home_parent
from seo_agent.model_env import load_model_settings, read_dotenv, sdk_base_url


def test_base_url_drops_v1_once():
    assert sdk_base_url("https://api.anthropic.com/v1") == "https://api.anthropic.com"
    assert sdk_base_url("https://api.anthropic.com/v1/") == "https://api.anthropic.com"
    assert sdk_base_url("https://api.anthropic.com") == "https://api.anthropic.com"


def test_settings_hide_key():
    s = load_model_settings({"SEO_MODEL_API_KEY": "sk-secret-123", "SEO_MODEL_BASE_URL": "https://api.anthropic.com/v1"})
    assert "sk-secret-123" not in repr(s) and s.model == "claude-opus-5-5"


def test_dotenv_parse(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# c\nA=1\nB=\"two\"\n\nbad line\n", encoding="utf-8")
    assert read_dotenv(p) == {"A": "1", "B": "two"}


def test_env_file_is_gitignored():
    out = subprocess.run(["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0


def test_run_home_config_and_hermes_reads_it(tmp_path):
    """子程序 import Hermes 前設 HERMES_HOME：Hermes 讀到 tool_search off、不借外部登入，且不建 ~/.hermes。"""
    home = prepare_run_home(tmp_path / "home")
    code = (
        "import json, hermes_constants\n"
        "from hermes_cli.config import load_config\n"
        "from agent.credential_sources import adopt_external_logins_enabled\n"
        "cfg = load_config()\n"
        "print(json.dumps({'home': str(hermes_constants.get_hermes_home()),"
        " 'tool_search': cfg['tools']['tool_search']['enabled'],"
        " 'adopt': adopt_external_logins_enabled()}))\n"
    )
    env = {"HERMES_HOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "fakehome")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert data == {"home": str(home), "tool_search": "off", "adopt": False}
    assert not (tmp_path / "fakehome" / ".hermes").exists()



def test_oauth_mode_needs_no_key_and_api_key_mode_still_does():
    """決策 #62：SEO_MODEL_AUTH=oauth 不要金鑰（就算 .env 有也不帶）；沒設時照舊要金鑰；其他值拒絕。"""
    s = load_model_settings({"SEO_MODEL_AUTH": "oauth", "SEO_MODEL_API_KEY": "sk-should-not-pass"})
    assert s.auth == "oauth" and s.api_key == "" and s.base_url == "https://api.anthropic.com"
    with pytest.raises(RuntimeError, match="SEO_MODEL_API_KEY"):
        load_model_settings({"SEO_MODEL_AUTH": "api_key", "SEO_MODEL_API_KEY": ""})
    with pytest.raises(RuntimeError, match="SEO_MODEL_AUTH"):
        load_model_settings({"SEO_MODEL_AUTH": "codex"})


def test_auth_home_is_gitignored():
    out = subprocess.run(["git", "check-ignore", ".hermes-auth/auth.json"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0


def test_oauth_run_home_reads_shared_login_without_borrowing(tmp_path):
    """oauth：run home 是 <auth_home>/profiles/<run_id>；Hermes 認得上層、讀得到上層登入、不借外部登入、不建 ~/.hermes。"""
    auth_home = tmp_path / "auth"
    assert run_home_parent("api_key", auth_home) == ROOT / ".hermes-runs" and not auth_home.exists()
    home = prepare_run_home(run_home_parent("oauth", auth_home) / "r1")
    assert (auth_home / "config.yaml").is_file()
    (auth_home / "auth.json").write_text(json.dumps({"version": 1, "credential_pool": {"anthropic": [
        {"id": "x1", "label": "test", "auth_type": "oauth", "priority": 0, "source": "manual:hermes_pkce",
         "access_token": "fake-token"}]}}), encoding="utf-8")
    code = (
        "import json, hermes_constants\n"
        "from hermes_cli.auth import read_credential_pool\n"
        "from agent.credential_sources import adopt_external_logins_enabled\n"
        "print(json.dumps({'root': str(hermes_constants.get_default_hermes_root()),"
        " 'adopt': adopt_external_logins_enabled(),"
        " 'pool': [e.get('id') for e in read_credential_pool('anthropic')]}))\n"
    )
    env = {"HERMES_HOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "fakehome")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"root": str(auth_home), "adopt": False, "pool": ["x1"]}
    assert not (tmp_path / "fakehome" / ".hermes").exists()



def test_oauth_expired_token_is_refreshed_and_written_back_to_auth_home(tmp_path):
    """審查 blocker：過期的 access token 要先換新（不連網，換新函式用假的），新 token 寫回上層，不留在 run home。"""
    auth_home = tmp_path / "auth"
    home = prepare_run_home(run_home_parent("oauth", auth_home) / "r1")
    (auth_home / "auth.json").write_text(json.dumps({"version": 1, "credential_pool": {"anthropic": [
        {"id": "x1", "label": "test", "auth_type": "oauth", "priority": 0, "source": "manual:hermes_pkce",
         "access_token": "old-token", "refresh_token": "old-refresh", "expires_at_ms": 1000}]}}), encoding="utf-8")
    code = (
        "import json, time, agent.anthropic_credentials as ac\n"
        "calls = []\n"
        "def fake(refresh_token, use_json=False):\n"
        "    calls.append(refresh_token)\n"
        "    return {'access_token': 'new-token', 'refresh_token': 'new-refresh',"
        " 'expires_at_ms': int(time.time() * 1000) + 3600000}\n"
        "ac.refresh_anthropic_oauth_pure = fake\n"
        "from seo_agent.hermes_bridge import oauth_credentials\n"
        "key, pool = oauth_credentials('claude-opus-5-5')\n"
        "print(json.dumps({'key': key, 'calls': calls, 'pool': pool is not None}))\n"
    )
    env = {"HERMES_HOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "fakehome"),
           "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"key": "new-token", "calls": ["old-refresh"], "pool": True}
    assert "new-refresh" in (auth_home / "auth.json").read_text(encoding="utf-8")
    assert not (home / "auth.json").exists() or "new-refresh" not in (home / "auth.json").read_text(encoding="utf-8")


@pytest.mark.live
def test_live_smoke_hermes_calls_opus_and_tool():
    from seo_agent.runner import new_run_id, run_isolated

    result = run_isolated("smoke", new_run_id("smoke-test"), {"budget_seconds": 120}, timeout_s=300)
    assert result["status"] == "passed", result.get("checks")
    assert result["hermes_home_matches_run"]
