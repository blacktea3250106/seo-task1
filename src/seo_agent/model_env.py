"""讀 .env 的模型設定。金鑰只在記憶體與子程序 env 中，不寫入任何紀錄。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import MODEL_ID, ROOT


@dataclass(frozen=True)
class ModelSettings:
    base_url: str  # 給 Anthropic SDK：不含 /v1（SDK 會自己加 /v1/messages）
    api_key: str
    model: str = MODEL_ID
    auth: str = "api_key"  # api_key＝.env 金鑰；oauth＝Hermes 自己的訂閱登入（.hermes-auth/，決策 #62）

    def __repr__(self) -> str:  # 避免金鑰出現在 log／traceback
        return f"ModelSettings(base_url={self.base_url!r}, api_key=<hidden>, model={self.model!r}, auth={self.auth!r})"


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sdk_base_url(url: str) -> str:
    """.env 的 SEO_MODEL_BASE_URL 已含 /v1；交給 SDK 前去掉，否則變成 /v1/v1/messages（404）。"""
    url = url.strip().rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def load_model_settings(env: dict[str, str] | None = None) -> ModelSettings:
    merged = {**read_dotenv(ROOT / ".env"), **(os.environ if env is None else env)}
    auth = merged.get("SEO_MODEL_AUTH") or "api_key"
    if auth not in ("api_key", "oauth"):
        raise RuntimeError(f"SEO_MODEL_AUTH 只能是 api_key 或 oauth，收到 {auth!r}")
    key = merged.get("SEO_MODEL_API_KEY", "") if auth == "api_key" else ""
    if auth == "api_key" and not key:
        raise RuntimeError("缺少 SEO_MODEL_API_KEY（放在專案 .env）；改用訂閱登入請設 SEO_MODEL_AUTH=oauth")
    return ModelSettings(base_url=sdk_base_url(merged.get("SEO_MODEL_BASE_URL", "https://api.anthropic.com")),
                         api_key=key, model=merged.get("SEO_MODEL_ID") or MODEL_ID, auth=auth)
