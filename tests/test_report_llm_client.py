import json

from query_doctor.report import llm_client


def test_ollama_url_helpers_normalize_api_endpoints():
    assert llm_client.ollama_base_url("http://localhost:11434/api/chat") == "http://localhost:11434"
    assert (
        llm_client.ollama_chat_url("http://localhost:11434/") == "http://localhost:11434/api/chat"
    )
    assert (
        llm_client.ollama_api_url("http://localhost:11434/api/ps", "/api/chat")
        == "http://localhost:11434/api/chat"
    )


def test_openai_compatible_url_helpers_normalize_api_endpoints():
    assert (
        llm_client.openai_compatible_base_url("https://llm.example.com/v1/chat/completions")
        == "https://llm.example.com"
    )
    assert (
        llm_client.openai_compatible_base_url("https://llm.example.com/v1")
        == "https://llm.example.com"
    )
    assert llm_client.openai_compatible_chat_endpoints("https://llm.example.com") == [
        "https://llm.example.com/v1/chat/completions",
        "https://llm.example.com/api/v1/chat/completions",
    ]


def test_parse_ollama_ps_models_handles_empty_and_loaded_models():
    assert llm_client.parse_ollama_ps_models("") == []
    assert llm_client.parse_ollama_ps_models("unexpected\n") is None
    assert llm_client.parse_ollama_ps_models(
        "NAME ID SIZE\nmodel-a abc 1 GB\nmodel-b def 2 GB\n"
    ) == [
        "model-a",
        "model-b",
    ]


def test_openai_compatible_stream_uses_generic_api_key_env(monkeypatch):
    seen: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {"content": "trusted report text"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        seen["auth"] = req.headers["Authorization"]
        seen["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("QD_LLM_API_KEY", "test-token")
    monkeypatch.delenv("QD_REPORT_LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    response = llm_client.stream_openai_compatible_report_with_meta(
        prompt="facts",
        model="report-model",
        base_url="https://llm.example.com",
        api_key_env="QD_REPORT_LLM_API_KEY",
        temperature=0.1,
    )

    assert response.text == "trusted report text"
    assert response.done_reason == "stop"
    assert response.eval_count == 5
    assert response.prompt_eval_count == 3
    assert seen["url"] == "https://llm.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-token"
    assert seen["payload"]["model"] == "report-model"
