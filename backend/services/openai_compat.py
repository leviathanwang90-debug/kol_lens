from __future__ import annotations

import os
from typing import Iterable


def first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def build_openai_client(*, api_key_envs: Iterable[str] = (), base_url_envs: Iterable[str] = ()):
    from openai import OpenAI

    api_key = first_env_value(*list(api_key_envs), "OPENAI_API_KEY")
    base_url = first_env_value(*list(base_url_envs), "OPENAI_BASE_URL")
    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
