#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

MAX_FILE_CHARS = int(os.getenv("QD_MAX_FILE_CHARS", "60000"))
NUM_CTX = int(os.getenv("QD_NUM_CTX", "16384"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "4096"))

EXPECTED_FILES = [
    ("SQL query", "sql.sql"),
    ("EXPLAIN plan", "explain.txt"),
    ("Impala profile summary", "profile_summary.txt"),
    ("Table stats / metadata", "table_stats.json"),
    ("Additional notes", "notes.md"),
]


def truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    head_len = max_chars // 2
    tail_len = max_chars - head_len

    return (
        text[:head_len]
        + f"\n\n[... TRUNCATED MIDDLE PART: {len(text) - max_chars} chars omitted ...]\n\n"
        + text[-tail_len:]
    )


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[FAILED TO READ FILE: {path.name}: {e}]"

    return truncate_middle(text, MAX_FILE_CHARS)


def build_case_context(case_dir: Path) -> str:
    parts = []

    for title, filename in EXPECTED_FILES:
        content = read_text(case_dir / filename)
        if not content.strip():
            continue

        parts.append(
            f"""
==================== {title}: {filename} ====================

{content}
""".strip()
        )

    if not parts:
        raise RuntimeError(
            f"No input files found in {case_dir}. "
            f"Expected at least sql.sql, explain.txt or profile.txt"
        )

    return "\n\n".join(parts)


def build_prompt(case_context: str) -> str:
    return f"""
Ты — опытный BigData performance engineer.
Ты анализируешь SQL-запросы, Impala/Spark/Hive execution plans, query profiles, метрики выполнения и layout данных.

КРИТИЧЕСКИ ВАЖНО:
- Ответ должен быть только на русском языке.
- Не используй английский язык, кроме технических терминов: HDFS, Impala, Spark, EXPLAIN, profile, scan, join, skew.
- Не делай общий summary trace.
- Не пиши "this is a detailed execution trace".
- Не делай вывод, что запрос работает эффективно, если это не доказано.
- Если видишь только часть профиля — пиши, что вывод предварительный.
- Строго соблюдай заданный markdown-формат.

Задача: сделать инженерный разбор производительности запроса.

Правила:
1. Не выдумывай факты.
2. Если данных недостаточно — прямо так и пиши.
3. Отделяй факты от гипотез.
4. Ссылайся на признаки из SQL / EXPLAIN / profile.
5. Не выводи блок <think>.
6. Не расписывай внутренние рассуждения.
7. Пиши по-русски.
8. Будь конкретным и инженерным.

Особенно ищи:
- full scan
- отсутствие partition pruning
- отсутствие table/column stats
- плохой join order
- broadcast/shuffle/hash join issues
- memory pressure
- admission control wait
- skew между fragment instances
- remote reads / network bottleneck
- small files
- metadata/catalog overhead
- spill to disk
- long GC
- straggler tasks

Формат ответа:

# Query Doctor Report

## 1. Краткий диагноз

## 2. Уровень уверенности

low / medium / high + почему.

## 3. Доказанные наблюдения

## 4. Основные гипотезы

Для каждой:
- гипотеза
- признаки
- что проверить
- вероятность

## 5. Что тормозит запрос

Разбери:
- чтение данных
- join/shuffle
- stats/cardinality estimates
- memory/admission
- skew
- small files / layout
- metastore/catalog
- network / remote reads

## 6. Рекомендации

### Быстрые проверки
### Безопасные изменения
### Более серьёзные изменения
### Что не стоит делать без проверки

## 7. Что запросить дополнительно

## 8. Итог для инженера

5–10 коротких bullets.

Входные данные:

{case_context}
""".strip()


def stream_ollama_to_file(model: str, prompt: str, output_path: Path) -> None:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты — строгий русскоязычный BigData performance engineer. "
                    "Всегда отвечай только на русском языке. "
                    "Не пересказывай входные данные общими словами. "
                    "Делай инженерную диагностику: факты, гипотезы, проверки, рекомендации. "
                    "Не выдумывай факты. Если данных недостаточно — прямо пиши, что данных недостаточно. "
                    "Не раскрывай внутренние рассуждения."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": True,
        "options": {
            "temperature": 0,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()
    received_chars = 0

    with urllib.request.urlopen(req, timeout=1800) as resp:
        with output_path.open("a", encoding="utf-8") as out:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"\n[Query Doctor] bad JSON line: {line[:200]}", file=sys.stderr)
                    continue

                if "error" in event:
                    raise RuntimeError(event["error"])

                content = event.get("message", {}).get("content", "")
                if content:
                    out.write(content)
                    out.flush()

                    print(content, end="", flush=True)

                    received_chars += len(content)

                    if received_chars % 1000 < len(content):
                        elapsed = int(time.time() - started)
                        print(
                            f"\r[Query Doctor] generated chars: {received_chars}, elapsed: {elapsed}s",
                            end="",
                            file=sys.stderr,
                            flush=True,
                        )

                if event.get("done"):
                    break

    print(file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local BigData Query Doctor")
    parser.add_argument("case_dir", help="Path to case directory")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists():
        print(f"Case directory does not exist: {case_dir}", file=sys.stderr)
        return 1

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else case_dir / "diagnosis.md"
    )

    case_context = build_case_context(case_dir)
    prompt = build_prompt(case_context)

    header = f"""<!--
Generated by Query Doctor
Date: {datetime.now().isoformat(timespec="seconds")}
Model: {args.model}
Case: {case_dir}
Context chars: {len(case_context)}
QD_NUM_CTX: {NUM_CTX}
QD_MAX_FILE_CHARS: {MAX_FILE_CHARS}
QD_NUM_PREDICT: {NUM_PREDICT}
-->

"""

    output_path.write_text(header, encoding="utf-8")

    print(f"[Query Doctor] case: {case_dir}", file=sys.stderr)
    print(f"[Query Doctor] model: {args.model}", file=sys.stderr)
    print(f"[Query Doctor] context chars: {len(case_context)}", file=sys.stderr)
    print(f"[Query Doctor] num_ctx: {NUM_CTX}", file=sys.stderr)
    print(f"[Query Doctor] num_predict: {NUM_PREDICT}", file=sys.stderr)
    print(f"[Query Doctor] output: {output_path}", file=sys.stderr)
    print("[Query Doctor] streaming started...", file=sys.stderr)

    stream_ollama_to_file(args.model, prompt, output_path)

    print(f"[Query Doctor] done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
