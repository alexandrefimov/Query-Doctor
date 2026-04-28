#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from datetime import datetime


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

# На первом этапе лучше ограничить размер каждого файла,
# иначе можно случайно засунуть в модель мегабайты мусора.
MAX_FILE_CHARS = int(os.getenv("QD_MAX_FILE_CHARS", "180000"))

EXPECTED_FILES = [
    ("SQL query", "sql.sql"),
    ("EXPLAIN plan", "explain.txt"),
    ("Query profile", "profile.txt"),
    ("Table stats / metadata", "table_stats.json"),
    ("Additional notes", "notes.md"),
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[FAILED TO READ FILE: {path.name}: {e}]"

    return truncate_middle(text, MAX_FILE_CHARS)


def truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]

    return (
        head
        + "\n\n[... TRUNCATED MIDDLE PART: "
        + str(len(text) - max_chars)
        + " chars omitted ...]\n\n"
        + tail
    )


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

Твоя задача — сделать инженерный разбор производительности запроса.

Важные правила:
1. Не выдумывай факты. Если данных недостаточно — так и пиши.
2. Всегда отделяй доказанные наблюдения от гипотез.
3. Ссылайся на конкретные признаки из SQL / EXPLAIN / profile.
4. Не давай опасные советы без проверки.
5. Приоритизируй рекомендации: сначала самые вероятные и полезные.
6. Пиши по-русски, но технические термины можешь оставлять на английском.
7. Если это Impala profile — ищи признаки:
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
8. Если это Spark — ищи признаки:
   - shuffle explosion
   - skew
   - too many small files
   - bad partitioning
   - AQE не помог
   - завышенные/заниженные executor resources
   - spill to disk
   - long GC
   - straggler tasks

Формат ответа строго такой:

# Query Doctor Report

## 1. Краткий диагноз

Коротко: что, скорее всего, не так.

## 2. Уровень уверенности

Оцени уверенность: low / medium / high.
Объясни почему.

## 3. Доказанные наблюдения

Список фактов, которые прямо видны из предоставленных данных.

## 4. Основные гипотезы

Для каждой гипотезы:
- гипотеза
- признаки
- что проверить
- насколько вероятно

## 5. Что тормозит запрос

Разбери по категориям:
- чтение данных
- join/shuffle
- stats/cardinality estimates
- memory/admission
- skew
- small files / layout
- metastore/catalog
- network / remote reads

Если по категории нет данных — напиши "нет данных".

## 6. Рекомендации

Раздели на:
### Быстрые проверки
### Безопасные изменения
### Более серьёзные изменения
### Что не стоит делать без проверки

## 7. Что запросить дополнительно

Какие файлы/метрики/профили нужны для более точного вывода.

## 8. Итог для инженера

5–10 коротких bullets: что делать дальше.

Вот входные данные кейса:

{case_context}
""".strip()


def call_ollama(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise BigData performance engineering assistant. Do not hallucinate.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            # Если модель/железо не тянут большой контекст — уменьши.
            # Если хочешь попробовать больше — выстави QD_NUM_CTX env и пробрось сюда.
            "num_ctx": int(os.getenv("QD_NUM_CTX", "32768")),
        },
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"Failed to call Ollama at {OLLAMA_URL}: {e}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Ollama returned non-JSON response:\n{raw[:2000]}")

    if "message" not in parsed or "content" not in parsed["message"]:
        raise RuntimeError(f"Unexpected Ollama response:\n{json.dumps(parsed, indent=2)[:2000]}")

    return parsed["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Local BigData Query Doctor")
    parser.add_argument("case_dir", help="Path to case directory")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output markdown file. Default: <case_dir>/diagnosis.md",
    )

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

    print(f"[Query Doctor] case: {case_dir}", file=sys.stderr)
    print(f"[Query Doctor] model: {args.model}", file=sys.stderr)
    print(f"[Query Doctor] context chars: {len(case_context)}", file=sys.stderr)
    print(f"[Query Doctor] output: {output_path}", file=sys.stderr)

    report = call_ollama(args.model, prompt)

    header = f"""<!--
Generated by Query Doctor
Date: {datetime.now().isoformat(timespec="seconds")}
Model: {args.model}
Case: {case_dir}
-->

"""

    output_path.write_text(header + report + "\n", encoding="utf-8")

    print(f"[Query Doctor] done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
