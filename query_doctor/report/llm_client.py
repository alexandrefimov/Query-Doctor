"""LLM client helpers shared by report and optimizer workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

from query_doctor.report.contract import REPORT_SYSTEM_PROMPT


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b-a3b-q8_0")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0")
LLM_PROVIDER_OLLAMA = "ollama"
LLM_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
LLM_PROVIDER_CHOICES = (LLM_PROVIDER_OLLAMA, LLM_PROVIDER_OPENAI_COMPATIBLE)
DEFAULT_LLM_PROVIDER = os.getenv("QD_LLM_PROVIDER", LLM_PROVIDER_OLLAMA)
DEFAULT_LLM_API_BASE_URL = os.getenv("QD_LLM_API_BASE_URL", "")
DEFAULT_LLM_API_KEY_ENV = "QD_LLM_API_KEY"
OPENAI_COMPATIBLE_CHAT_PATHS = ("/v1/chat/completions", "/api/v1/chat/completions")
NUM_CTX = int(os.getenv("QD_NUM_CTX", "16384"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "1800"))
PROGRESS_PREFIX = "[Query Doctor report]"


@dataclass(frozen=True)
class StreamedLLMResponse:
    text: str
    done_reason: str
    eval_count: int | None
    prompt_eval_count: int | None


def ollama_chat_url(base_url: str) -> str:
    return ollama_api_url(base_url, "/api/chat")


def ollama_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    for suffix in ("/api/chat", "/api/generate", "/api/ps"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def ollama_api_url(base_url: str, endpoint: str) -> str:
    return ollama_base_url(base_url) + endpoint


def normalize_llm_provider(value: str | None) -> str:
    normalized = (value or LLM_PROVIDER_OLLAMA).strip().lower().replace("-", "_")
    if normalized in {"openai", "openai_compatible", "remote"}:
        return LLM_PROVIDER_OPENAI_COMPATIBLE
    if normalized == LLM_PROVIDER_OLLAMA:
        return LLM_PROVIDER_OLLAMA
    raise ValueError(
        "LLM provider must be one of: "
        + ", ".join((LLM_PROVIDER_OLLAMA, LLM_PROVIDER_OPENAI_COMPATIBLE))
    )


def openai_compatible_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    for suffix in (
        "/api/v1/chat/completions",
        "/v1/chat/completions",
        "/chat/completions",
        "/api/v1",
        "/v1",
    ):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def openai_compatible_chat_endpoints(base_url: str, preferred_path: str | None = None) -> list[str]:
    base = openai_compatible_base_url(base_url).rstrip("/")
    if not base:
        return []
    endpoints: list[str] = []
    if preferred_path:
        path = preferred_path.strip()
        if path.startswith("http://") or path.startswith("https://"):
            return [path.rstrip("/")]
        if not path.startswith("/"):
            path = f"/{path}"
        endpoints.append(f"{base}{path}")
    for path in OPENAI_COMPATIBLE_CHAT_PATHS:
        candidate = f"{base}{path}"
        if candidate not in endpoints:
            endpoints.append(candidate)
    return endpoints


def parse_ollama_ps_models(output: str) -> list[str] | None:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split()
    if not header or header[0].upper() != "NAME":
        return None

    models: list[str] = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        models.append(parts[0])
    return models


def stop_other_ollama_models(
    *,
    target_model: str,
    run_func: Any = subprocess.run,
) -> list[str]:
    try:
        ps = run_func(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"{PROGRESS_PREFIX} warning: failed to run ollama ps: {exc}", file=sys.stderr)
        return []

    if ps.returncode != 0:
        err = (ps.stderr or ps.stdout or "").strip()
        print(f"{PROGRESS_PREFIX} warning: ollama ps failed: {err}", file=sys.stderr)
        return []

    loaded_models = parse_ollama_ps_models(ps.stdout)
    if loaded_models is None:
        print(
            f"{PROGRESS_PREFIX} warning: could not parse ollama ps output; continuing",
            file=sys.stderr,
        )
        return []

    stopped: list[str] = []
    for model_name in loaded_models:
        if model_name == target_model:
            continue
        stop = run_func(
            ["ollama", "stop", model_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if stop.returncode != 0:
            err = (stop.stderr or stop.stdout or "").strip()
            print(
                f"{PROGRESS_PREFIX} warning: ollama stop {model_name!r} failed: {err}",
                file=sys.stderr,
            )
            continue
        stopped.append(model_name)
    return stopped


def stream_ollama_report(
    *,
    prompt: str,
    model: str,
    ollama_url: str,
    temperature: float,
    keep_alive: str,
    system_prompt: str = REPORT_SYSTEM_PROMPT,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> str:
    return stream_ollama_report_with_meta(
        prompt=prompt,
        model=model,
        ollama_url=ollama_url,
        temperature=temperature,
        keep_alive=keep_alive,
        system_prompt=system_prompt,
        num_ctx=num_ctx,
        num_predict=num_predict,
    ).text


def stream_llm_report(
    *,
    provider: str,
    prompt: str,
    model: str,
    base_url: str,
    temperature: float,
    keep_alive: str,
    system_prompt: str = REPORT_SYSTEM_PROMPT,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    api_key_env: str = DEFAULT_LLM_API_KEY_ENV,
    chat_path: str | None = None,
) -> str:
    return stream_llm_report_with_meta(
        provider=provider,
        prompt=prompt,
        model=model,
        base_url=base_url,
        temperature=temperature,
        keep_alive=keep_alive,
        system_prompt=system_prompt,
        num_ctx=num_ctx,
        num_predict=num_predict,
        api_key_env=api_key_env,
        chat_path=chat_path,
    ).text


def stream_llm_report_with_meta(
    *,
    provider: str,
    prompt: str,
    model: str,
    base_url: str,
    temperature: float,
    keep_alive: str,
    system_prompt: str = REPORT_SYSTEM_PROMPT,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    api_key_env: str = DEFAULT_LLM_API_KEY_ENV,
    chat_path: str | None = None,
) -> StreamedLLMResponse:
    normalized_provider = normalize_llm_provider(provider)
    if normalized_provider == LLM_PROVIDER_OLLAMA:
        return stream_ollama_report_with_meta(
            prompt=prompt,
            model=model,
            ollama_url=base_url or DEFAULT_OLLAMA_URL,
            temperature=temperature,
            keep_alive=keep_alive,
            system_prompt=system_prompt,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
    return stream_openai_compatible_report_with_meta(
        prompt=prompt,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        temperature=temperature,
        system_prompt=system_prompt,
        num_predict=num_predict,
        chat_path=chat_path,
    )


def stream_ollama_report_with_meta(
    *,
    prompt: str,
    model: str,
    ollama_url: str,
    temperature: float,
    keep_alive: str,
    system_prompt: str = REPORT_SYSTEM_PROMPT,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> StreamedLLMResponse:
    requested_num_ctx = NUM_CTX if num_ctx is None else num_ctx
    requested_num_predict = NUM_PREDICT if num_predict is None else num_predict
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": requested_num_ctx,
            "num_predict": requested_num_predict,
        },
    }
    if keep_alive:
        payload["keep_alive"] = keep_alive

    req = urllib.request.Request(
        ollama_chat_url(ollama_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()
    received = 0
    chunks: list[str] = []
    final_event: dict[str, Any] = {}
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"{PROGRESS_PREFIX} warning: bad Ollama JSON line omitted", file=sys.stderr)
                continue

            if "error" in event:
                raise RuntimeError(event["error"])

            content = event.get("message", {}).get("content", "")
            if content:
                chunks.append(content)
                received += len(content)
                if received % 1200 < len(content):
                    elapsed = int(time.time() - started)
                    print(
                        f"{PROGRESS_PREFIX} generated chars: {received}, elapsed: {elapsed}s",
                        file=sys.stderr,
                        flush=True,
                    )

            if event.get("done"):
                final_event = event
                break

    done_reason = str(final_event.get("done_reason") or "").strip()
    eval_count = final_event.get("eval_count")
    prompt_eval_count = final_event.get("prompt_eval_count")
    return StreamedLLMResponse(
        text="".join(chunks),
        done_reason=done_reason,
        eval_count=eval_count if isinstance(eval_count, int) else None,
        prompt_eval_count=prompt_eval_count if isinstance(prompt_eval_count, int) else None,
    )


def stream_openai_compatible_report_with_meta(
    *,
    prompt: str,
    model: str,
    base_url: str,
    api_key_env: str,
    temperature: float,
    system_prompt: str = REPORT_SYSTEM_PROMPT,
    num_predict: int | None = None,
    chat_path: str | None = None,
) -> StreamedLLMResponse:
    if not base_url:
        raise RuntimeError("LLM API base URL is not configured.")
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key and api_key_env != DEFAULT_LLM_API_KEY_ENV:
        api_key = os.environ.get(DEFAULT_LLM_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"LLM API key is not configured in {api_key_env}.")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if num_predict is not None:
        payload["max_tokens"] = num_predict

    last_error = "no compatible chat endpoint configured"
    for endpoint in openai_compatible_chat_endpoints(base_url, chat_path):
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                response = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last_error = f"LLM API HTTP {exc.code}"
            if exc.code in {404, 405, 410}:
                continue
            raise RuntimeError(last_error) from exc
        except (OSError, json.JSONDecodeError) as exc:
            last_error = f"LLM API request failed: {exc}"
            continue

        if not isinstance(response, dict):
            last_error = "LLM API returned an unexpected response type."
            continue
        if "error" in response:
            message = response["error"]
            if isinstance(message, dict):
                message = message.get("message", "unknown error")
            raise RuntimeError(f"LLM API error: {message}")
        content, finish_reason = _openai_compatible_choice_text(response)
        if content is None:
            last_error = "LLM API returned an unexpected response shape."
            continue
        usage = response.get("usage")
        eval_count = None
        prompt_eval_count = None
        if isinstance(usage, dict):
            completion_tokens = usage.get("completion_tokens")
            prompt_tokens = usage.get("prompt_tokens")
            eval_count = completion_tokens if isinstance(completion_tokens, int) else None
            prompt_eval_count = prompt_tokens if isinstance(prompt_tokens, int) else None
        return StreamedLLMResponse(
            text=content,
            done_reason=finish_reason or "",
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
        )
    raise RuntimeError(last_error)


def _openai_compatible_choice_text(response: dict[str, Any]) -> tuple[str | None, str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, None
    finish_reason = choice.get("finish_reason")
    message = choice.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"]), str(finish_reason or "")
    text = choice.get("text")
    if text:
        return str(text), str(finish_reason or "")
    return None, None
