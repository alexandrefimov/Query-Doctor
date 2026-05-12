"""Ollama client helpers shared by report and optimizer workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import subprocess
import sys
import time
from typing import Any
import urllib.request

from query_doctor.report.contract import REPORT_SYSTEM_PROMPT


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b-a3b-q8_0")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0")
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
