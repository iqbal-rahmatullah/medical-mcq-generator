import io
import urllib.request

from app.generation.llm_client import LLMClient


def test_openai_compatible_request_sends_waf_safe_headers(monkeypatch):
    captured_headers = {}

    def fake_urlopen(request, **_kwargs):
        captured_headers["accept"] = request.get_header("Accept")
        captured_headers["user_agent"] = request.get_header("User-agent")
        return io.BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = LLMClient(
        api_key="test-key",
        api_base="https://example.test/v1/chat/completions",
        model="test-model",
        provider="openai_compatible",
        fallback_targets_json="[]",
    )

    assert client.generate_text("hello") == "OK"
    assert captured_headers == {
        "accept": "application/json",
        "user_agent": "AQG/0.1",
    }
