#!/usr/bin/env python3
"""
query_doctor_v2.py

Strict local Query Doctor for Impala profile digest.

This version intentionally reads only:
  - profile_digest.md
  - notes.md optional

It does NOT read raw profile.txt or profile_summary.txt.
The goal is to prevent the LLM from being distracted by low-level per-instance counters.

Usage:
  cd ~/query-doctor
  ./query_doctor_v2.py cases/cm-e64c9c961cd19841_c81c5ec900000000 --model qwen3-coder:30b

Env:
  OLLAMA_URL=http://localhost:11434/api/chat
  QD_NUM_CTX=8192
  QD_NUM_PREDICT=1800
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
NUM_CTX = int(os.getenv("QD_NUM_CTX", "8192"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "1800"))
MAX_DIGEST_CHARS = int(os.getenv("QD_MAX_DIGEST_CHARS", "45000"))


def read_text(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n\n[... truncated ...]\n"
    return text


def extract_block(text: str, heading: str) -> str:
    pattern = rf"(?is)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)"
    m = re.search(pattern, text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_exec_rows(digest: str) -> list[str]:
    block = extract_block(digest, "ExecSummary: important operator rows")
    m = re.search(r"```text\s*(.*?)```", block, flags=re.S | re.I)
    if m:
        block = m.group(1)

    rows = []
    for line in block.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if re.match(r"^\s*(?:F\d+|\d+):", line):
            rows.append(line)
    return rows


def extract_key_signals(digest: str) -> str:
    rows = extract_exec_rows(digest)

    high_value_rows = []
    cardinality_rows = []
    memory_rows = []
    join_sort_rows = []

    for row in rows:
        upper = row.upper()

        if any(token in upper for token in ["HASH JOIN", "SORT", "ANALYTIC", "AGGREG", "EXCHANGE"]):
            join_sort_rows.append(row)

        # Rows where actual rows are millions while estimate is about 10.55K / 4.30K etc.
        if re.search(r"\b\d+\.\d+M\b", row) and re.search(r"\b\d+\.\d+K\b", row):
            cardinality_rows.append(row)

        if re.search(r"\b(?:\d+\.\d+|\d+)\s+GB\b", row, flags=re.I):
            memory_rows.append(row)

        # Keep visibly expensive operators.
        if re.search(r"\b\d+s\d+ms\b|\b[2-9]\d+s\d+ms\b|\b\d+m\b", row, flags=re.I):
            high_value_rows.append(row)

    lines = []
    lines.append("AUTO-EXTRACTED SIGNALS FROM DIGEST")
    lines.append("")
    lines.append("Most relevant operator rows:")
    for row in (high_value_rows + memory_rows + cardinality_rows)[:40]:
        lines.append(f"- {row}")

    lines.append("")
    lines.append("Cardinality mismatch rows, actual rows vs estimated rows:")
    if cardinality_rows:
        for row in cardinality_rows[:30]:
            lines.append(f"- {row}")
    else:
        lines.append("- none detected by regex")

    lines.append("")
    lines.append("High-memory rows:")
    if memory_rows:
        for row in memory_rows[:30]:
            lines.append(f"- {row}")
    else:
        lines.append("- none detected by regex")

    lines.append("")
    lines.append("All join/sort/analytic/exchange rows:")
    for row in join_sort_rows[:80]:
        lines.append(f"- {row}")

    return "\n".join(lines)


def build_prompt(case_dir: Path) -> str:
    digest_path = case_dir / "profile_digest.md"
    if not digest_path.exists():
        raise FileNotFoundError(f"profile_digest.md not found: {digest_path}")

    digest = read_text(digest_path, MAX_DIGEST_CHARS)
    notes = read_text(case_dir / "notes.md", 8000)
    signals = extract_key_signals(digest)

    return f"""
Ты — строгий русскоязычный BigData performance engineer по Apache Impala.

КРИТИЧЕСКИ ВАЖНО:
- Ответ только на русском языке.
- Используй ТОЛЬКО факты из блока DIGEST и AUTO-EXTRACTED SIGNALS.
- Не пересказывай запрос общими словами.
- Не анализируй мелкие per-instance counters как главную причину, если ExecSummary показывает дорогие операторы.
- Если Metric lines противоречат ExecSummary, приоритет у ExecSummary.
- Не говори, что запрос быстрый, если в ExecSummary есть операторы на десятки секунд или TotalTime в минутах.
- Не рекомендуй отключать codegen, если CodegenTotalWallClockTime/CodegenTime не является явным доминирующим временем.
- Не рекомендуй HDFS block size / replication, если нет доказательств small files / storage wait / many scan ranges как главного bottleneck.
- Не выдумывай индексы: в Impala/HDFS/Parquet классических индексов как в OLTP обычно нет.
- Отделяй факты от гипотез.
- Рекомендации должны быть инженерными и проверяемыми.

Главные типы проблем, которые нужно искать:
1. Ошибки cardinality estimates: actual rows сильно больше Est. #Rows.
2. Дорогие HASH JOIN / SORT / ANALYTIC / AGGREGATION.
3. Peak Mem сильно больше Est. Peak Mem.
4. Большой TotalBytesRead / TotalBytesSent.
5. Partition pruning / scan volume.
6. Spill / scratch I/O, если явно есть.
7. Admission/planning/metadata только если явно есть.

ФОРМАТ ОТВЕТА:

# Query Doctor Report

## 1. Краткий диагноз
2-4 предложения. Сразу назови главную проблему.

## 2. Уровень уверенности
low / medium / high и почему.

## 3. Доказанные факты из профиля
Список конкретных строк/метрик из digest.

## 4. Главные bottleneck'и
Разбери по приоритету:
1. самый важный
2. второй
3. третий

Для каждого:
- факт
- интерпретация
- что проверить

## 5. Что, скорее всего, НЕ является причиной
Например: codegen, HDFS latency, small files, если нет доказательств.

## 6. Рекомендации
### Быстрые проверки
### Изменения в SQL
### Изменения в данных/статистике
### Что не делать без проверки

## 7. Что добавить в следующий сбор данных
Каких данных не хватает для более точной диагностики.

## 8. Итог для инженера
5-8 коротких пунктов.

NOTES:
{notes if notes.strip() else "No notes.md"}

AUTO-EXTRACTED SIGNALS:
{signals}

DIGEST:
{digest}
""".strip()


def stream_ollama(model: str, prompt: str, output_path: Path) -> None:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты строгий русскоязычный BigData/Impala performance engineer. "
                    "Отвечай только на русском. Используй только предоставленные факты. "
                    "Не делай generic advice."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {
            "temperature": 0,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()
    received = 0

    with urllib.request.urlopen(req, timeout=1800) as resp:
        with output_path.open("a", encoding="utf-8") as out:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                event = json.loads(line)
                if "error" in event:
                    raise RuntimeError(event["error"])

                content = event.get("message", {}).get("content", "")
                if content:
                    out.write(content)
                    out.flush()
                    print(content, end="", flush=True)

                    received += len(content)
                    if received % 1200 < len(content):
                        elapsed = int(time.time() - started)
                        print(
                            f"\n[Query Doctor v2] generated chars: {received}, elapsed: {elapsed}s",
                            file=sys.stderr,
                            flush=True,
                        )

                if event.get("done"):
                    break


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict local Impala Query Doctor")
    parser.add_argument("case_dir", help="Case directory containing profile_digest.md")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else case_dir / "diagnosis_v2.md"
    )

    prompt = build_prompt(case_dir)

    header = f"""<!--
Generated by Query Doctor v2
Date: {datetime.now().isoformat(timespec="seconds")}
Model: {args.model}
Case: {case_dir}
Prompt chars: {len(prompt)}
QD_NUM_CTX: {NUM_CTX}
QD_NUM_PREDICT: {NUM_PREDICT}
QD_MAX_DIGEST_CHARS: {MAX_DIGEST_CHARS}
-->

"""

    output_path.write_text(header, encoding="utf-8")

    print(f"[Query Doctor v2] case: {case_dir}", file=sys.stderr)
    print(f"[Query Doctor v2] model: {args.model}", file=sys.stderr)
    print(f"[Query Doctor v2] prompt chars: {len(prompt)}", file=sys.stderr)
    print(f"[Query Doctor v2] num_ctx: {NUM_CTX}", file=sys.stderr)
    print(f"[Query Doctor v2] num_predict: {NUM_PREDICT}", file=sys.stderr)
    print(f"[Query Doctor v2] output: {output_path}", file=sys.stderr)
    print("[Query Doctor v2] streaming started...", file=sys.stderr)

    stream_ollama(args.model, prompt, output_path)

    print(f"\n[Query Doctor v2] done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
