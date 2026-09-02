"""HTTP behavior of zlens.core.vlm.chat (fake transport, offline)."""

import json

import httpx
import pytest

from zlens.core import vlm as vlm_mod
from zlens.core.config import Settings
from zlens.core.vlm import VlmCallFailed, chat

_SETTINGS = Settings(vlm_base_url="http://vlm.test/v1", vlm_model="m", vlm_api_key="sk-x")
_OK = {"choices": [{"message": {"content": "ok"}}]}


def _fake_post(calls, responses):
    def post(url, *, headers=None, json=None, timeout=None):
        calls.append(json)
        response = responses.pop(0)
        response.request = httpx.Request("POST", url)
        return response

    return post


def test_chat_sends_enable_thinking_false(monkeypatch):
    calls = []
    monkeypatch.setattr(vlm_mod.httpx, "post", _fake_post(calls, [httpx.Response(200, json=_OK)]))
    assert chat(_SETTINGS, text="hi") == "ok"
    assert calls[0]["enable_thinking"] is False


def test_chat_retries_plain_when_thinking_knob_rejected(monkeypatch):
    calls = []
    monkeypatch.setattr(
        vlm_mod.httpx,
        "post",
        _fake_post(
            calls,
            [
                httpx.Response(400, text='{"error":"Unsupported parameter: enable_thinking"}'),
                httpx.Response(200, json=_OK),
            ],
        ),
    )
    assert chat(_SETTINGS, text="hi") == "ok"
    assert len(calls) == 2
    assert "enable_thinking" not in calls[1]


def test_chat_unrelated_400_fails_without_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(
        vlm_mod.httpx,
        "post",
        _fake_post(calls, [httpx.Response(400, text='{"error":"model not found"}')]),
    )
    with pytest.raises(VlmCallFailed):
        chat(_SETTINGS, text="hi")
    assert len(calls) == 1


def test_chat_read_timeout_surfaces_as_call_failed(monkeypatch):
    def post(url, *, headers=None, json=None, timeout=None):
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(vlm_mod.httpx, "post", post)
    with pytest.raises(VlmCallFailed, match="timed out"):
        chat(_SETTINGS, text="hi")


def test_chat_payload_shape(monkeypatch):
    calls = []
    monkeypatch.setattr(vlm_mod.httpx, "post", _fake_post(calls, [httpx.Response(200, json=_OK)]))
    chat(_SETTINGS, text="hi", image_base64="AAAA")
    content = calls[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "hi"}
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert json.dumps(calls[0])  # payload is JSON-serializable
