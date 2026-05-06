from query_doctor.report import llm_client


def test_ollama_url_helpers_normalize_api_endpoints():
    assert llm_client.ollama_base_url("http://localhost:11434/api/chat") == "http://localhost:11434"
    assert llm_client.ollama_chat_url("http://localhost:11434/") == "http://localhost:11434/api/chat"
    assert llm_client.ollama_api_url("http://localhost:11434/api/ps", "/api/chat") == "http://localhost:11434/api/chat"


def test_parse_ollama_ps_models_handles_empty_and_loaded_models():
    assert llm_client.parse_ollama_ps_models("") == []
    assert llm_client.parse_ollama_ps_models("unexpected\n") is None
    assert llm_client.parse_ollama_ps_models("NAME ID SIZE\nmodel-a abc 1 GB\nmodel-b def 2 GB\n") == [
        "model-a",
        "model-b",
    ]
