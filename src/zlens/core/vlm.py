"""Minimal OpenAI-compatible VLM caller for screenshot price extraction.

The endpoint/model/key come from settings; keys live in the environment or the
gitignored config file, never in code. Errors are typed so routers can degrade
cleanly (unconfigured → guide to settings; call failure → readable 502).
"""

import httpx

from zlens.core.config import Settings

# 20 秒快速失败:超时的模型让用户马上看到错误并换模型,而不是对着转圈等三分钟。
_VLM_TIMEOUT = 20.0


class VlmUnconfigured(Exception):
    """The VLM section of settings is empty."""


class VlmCallFailed(Exception):
    """The upstream chat/completions call could not be completed."""


def chat(
    settings: Settings,
    *,
    text: str | None = None,
    image_base64: str | None = None,
) -> str:
    """Send one user turn (text and/or inline image) and return the reply text."""
    if not (settings.vlm_api_key and settings.vlm_base_url and settings.vlm_model):
        raise VlmUnconfigured("VLM 未配置：请到 设置 → VLM 识别 填写模型、Base URL 与 API Key")

    content: list[dict] = []
    if text:
        content.append({"type": "text", "text": text})
    if image_base64:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
            }
        )

    url = settings.vlm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.vlm_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
    }
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.vlm_api_key}"},
            json=payload,
            timeout=_VLM_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as exc:
        raise VlmCallFailed(f"VLM 调用失败：{exc}") from exc
