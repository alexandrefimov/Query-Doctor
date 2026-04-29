#!/usr/bin/env python3
"""
Query Doctor report writer.

This script reads only deterministic analysis facts and asks a local Ollama
model to turn those facts into a human-readable markdown report. It never reads
profile_digest.md, profile.txt, or other raw profile files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0")
NUM_CTX = int(os.getenv("QD_NUM_CTX", "16384"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "2400"))
PROGRESS_PREFIX = "[Query Doctor report]"
MIN_REPORT_CHARS = int(os.getenv("QD_MIN_REPORT_CHARS", "1500"))
MIN_MARKDOWN_SECTIONS = int(os.getenv("QD_MIN_MARKDOWN_SECTIONS", "8"))
REQUIRED_REPORT_SECTIONS = [
    "# Query Doctor Report",
    "## Краткий вывод",
    "## Главная причина замедления",
    "## Подтверждающие факты",
    "## Что усиливает проблему",
    "## Что НЕ подтверждается фактами",
    "## Практические рекомендации",
    "## Что проверить следующим запуском",
]
UNSUPPORTED_RECOMMENDATION_RE = (
    "hdfs",
    "хранилищ",
    "репликац",
    "replication",
    "block size",
    "блок",
    "размер блок",
    "external network",
    "network",
    "влияние внешней сети",
    "внешняя сеть",
    "внешней сети",
    "сетевая",
    "сетевых",
    "сетев",
    "сеть",
    "сети",
    "codegen",
    "llvm",
)
UNSUPPORTED_IF_ABSENT_RE = (
    "packet loss",
    "restart impala",
)
SPILL_SCRATCH_REWRITE_RE = re.compile(r"\b(spill|scratch|спилл|спай[лл]|спила|спайла)\b", re.IGNORECASE)
STORAGE_WORDING_RE = re.compile(
    r"(физическ\w*\s+хранен\w*|проблем\w*\s+с\s+хранилищ\w*|хранилищ\w*)",
    re.IGNORECASE,
)
SPILL_SCRATCH_NEXT_CHECK = (
    "- Проверить spill/scratch counters в raw profile, чтобы подтвердить или исключить memory pressure со spill."
)


def resolve_case_file(case_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return case_dir / path


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


def read_required_facts(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Facts file not found: {path}. Run analyze_profile_digest.py first. "
            "Refusing to fall back to profile_digest.md or profile.txt."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Facts path is not a file: {path}")

    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    return text, hashlib.sha256(data).hexdigest()


def build_prompt(
    *,
    facts_text: str,
    facts_path: Path,
    facts_sha256: str,
    model: str,
    language: str,
) -> str:
    language_instruction = "Ответ должен быть на русском языке." if language == "ru" else f"Language: {language}."

    return f"""
You are only a report writer.
Use only facts provided below.
Do not parse or infer anything from profile_digest.md, profile.txt, raw profiles, SQL text, or external knowledge.
Do not invent metrics, operator IDs, root causes, timings, row counts, memory values, table names, columns, or SQL rewrites.
If something is not present in facts, say it is not supported by parsed evidence.
Preserve the "What is NOT supported" conclusions.
Do not recommend HDFS block size, replication factor, external network fixes, disabling codegen, or spill tuning unless facts explicitly support it.
Do not output hidden reasoning, chain-of-thought, or <think> blocks.

{language_instruction}

Engineering interpretation rules:
- The report must distinguish cardinality mismatch from memory mismatch.
- Cardinality mismatch means actual rows are much larger than estimated rows.
- Memory mismatch means peak memory is larger than estimated peak memory.
- Do not use operators with mem ratio below 1.0 as evidence for memory underestimation.
- If an operator has rows ratio above threshold but mem ratio below 1.0, use it only as cardinality/intermediate-row evidence, not memory-underestimation evidence.
- The main root cause wording must explicitly mention actual rows in millions vs estimated rows around 10.55K for dominant HASH JOIN / SORT / ANALYTIC operators when those facts are present.
- Distinguish "large intermediate/exchange traffic" from external network instability.
- Do not recommend checking external network based only on TotalBytesSent.
- TotalBytesSent means intermediate/exchange data volume unless facts explicitly say network fault.
- Do not describe EXCHANGE as a main memory bottleneck when absolute peak memory is small.
- For memory impact, prefer operators with large absolute peak memory, especially GiB-scale SORT/HASH JOIN.
- Treat skew and spill only as established causes if the facts explicitly contain skew evidence or non-zero spill/scratch metrics.
- If skew/spill evidence is absent, mention them only under "Что проверить следующим запуском".

The final markdown file is assembled by the wrapper with:
# Query Doctor Report

> Source facts: `{facts_path.name}`
> Facts sha256: `{facts_sha256}`
> Model: `{model}`

Do not write "# Query Doctor Report" yourself.
Do not repeat the Source facts / Facts sha256 / Model fingerprint yourself.
You must write only the report body, starting with exactly these headings, in this order:

## Краткий вывод
## Главная причина замедления
## Подтверждающие факты
## Что усиливает проблему
## Что НЕ подтверждается фактами
## Практические рекомендации
## Что проверить следующим запуском

Grounding rules for recommendations:
- Good: Проверить/обновить stats для таблиц/партиций, участвующих в join, потому что parsed facts show actual rows >> estimated rows.
- Good: Проверить порядок join / условия join / возможность предварительной фильтрации данных до analytic/sort.
- Good: Снизить объём intermediate rows перед SORT/ANALYTIC.
- Good: Проверить skew only if facts contain skew evidence; otherwise put it under "Что проверить следующим запуском", not as a cause.
- Bad: Do not claim HDFS bottleneck.
- Bad: Do not claim network instability.
- Bad: Do not recommend checking external network because TotalBytesSent is large.
- Bad: Do not claim codegen problem.
- Bad: Do not claim spill unless facts contain non-zero spill metrics.

Report writing guidance:
- Be concise and engineering-focused.
- Separate deterministic facts from hypotheses.
- Quote concrete operators and ratios only when they appear in the facts.
- In "Главная причина замедления", name cardinality estimate errors as the primary cause if facts show actual rows in millions versus estimated rows around 10.55K.
- In "Подтверждающие факты", group facts separately: cardinality mismatch, memory mismatch, expensive operators, intermediate/exchange traffic.
- In "Что усиливает проблему", discuss SORT/ANALYTIC and memory underestimation only where the facts support them.
- In "Что усиливает проблему", do not call EXCHANGE a main memory bottleneck if its absolute peak memory is small; describe it as intermediate/exchange data volume only.
- In "Что НЕ подтверждается фактами", explicitly carry over unsupported conclusions from facts.
- In "Практические рекомендации", explain why each recommendation is supported by facts.
- "Практические рекомендации" must include these concrete, fact-tied actions:
  1. Проверить/обновить table stats and partition stats for JOIN inputs.
  2. Найти место, где cardinality grows from estimated ~10.55K to millions before dominant HASH JOIN operators.
  3. Reduce intermediate rows before SORT/ANALYTIC.
  4. Проверить ключи join, фильтры join, CTE, DISTINCT, LEFT OUTER JOIN и LEFT ANTI JOIN.
  5. Put skew/spill checks under "Что проверить следующим запуском" unless facts explicitly establish them.

DETERMINISTIC FACTS BEGIN
Source facts filename: {facts_path.name}
Facts sha256: {facts_sha256}
Model requested: {model}

{facts_text}
DETERMINISTIC FACTS END
""".strip()


def report_header(facts_path: Path, facts_sha256: str, model: str) -> str:
    generated_at = datetime.now().isoformat(timespec="seconds")
    return f"""# Query Doctor Report

> Source facts: `{facts_path.name}`  
> Facts sha256: `{facts_sha256}`  
> Model: `{model}`  
> Generated: `{generated_at}`

"""


def has_unsupported_recommendation_topic(line: str, facts_text: str = "") -> bool:
    lower = line.lower()
    if any(token in lower for token in UNSUPPORTED_RECOMMENDATION_RE):
        return True
    facts_lower = facts_text.lower()
    return any(token in lower and token not in facts_lower for token in UNSUPPORTED_IF_ABSENT_RE)


def should_rewrite_spill_storage_line(line: str) -> bool:
    return bool(SPILL_SCRATCH_REWRITE_RE.search(line) and STORAGE_WORDING_RE.search(line))


def strip_unsupported_prose(line: str, current_section: str, facts_text: str = "") -> str | None:
    stripped = line.lstrip()
    is_list_item = stripped.startswith(("-", "*")) or bool(re.match(r"^\d+\.\s+", stripped))
    if should_rewrite_spill_storage_line(line):
        if current_section == "## Что проверить следующим запуском":
            return SPILL_SCRATCH_NEXT_CHECK
        return None
    if current_section in {"## Практические рекомендации", "## Что проверить следующим запуском"}:
        return None

    if is_list_item:
        total_sent_match = re.search(
            r"TotalBytesSent\s*[:=]\s*(?P<value>\d[\d.]*\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B))",
            line,
            flags=re.IGNORECASE,
        )
        if total_sent_match:
            return f"- TotalBytesSent: {total_sent_match.group('value')} — объем intermediate/exchange данных."
        return None

    sentences = re.split(r"(?<=[.!?])\s+", line)
    kept = [
        sentence
        for sentence in sentences
        if sentence and not has_unsupported_recommendation_topic(sentence, facts_text)
    ]
    result = " ".join(kept).strip()
    return result or None


def sanitize_report_text(report_text: str, facts_text: str) -> str:
    """Return report text with unsupported recommendations removed.

    Pure helper for tests and callers: no file I/O, no network, no Ollama calls.
    """
    lines = [line for line in report_text.splitlines() if not line.startswith(PROGRESS_PREFIX)]

    # The wrapper owns the top-level title and fingerprint. Some local models
    # still repeat them; strip a repeated model-produced header block while
    # keeping the wrapper header intact.
    h1_indexes = [i for i, line in enumerate(lines) if line.strip() == "# Query Doctor Report"]
    if len(h1_indexes) > 1:
        duplicate_start = h1_indexes[1]
        next_section = None
        for i in range(duplicate_start + 1, len(lines)):
            if lines[i].startswith("## "):
                next_section = i
                break
        if next_section is not None:
            lines = lines[:duplicate_start] + lines[next_section:]

    normalized: list[str] = []
    current_section = ""
    for line in lines:
        if line.startswith("## "):
            current_section = line.strip()
        is_not_supported = current_section == "## Что НЕ подтверждается фактами"
        is_structure_line = line.startswith("#") or line.startswith(">") or not line.strip()
        if (
            not is_structure_line
            and not is_not_supported
            and (
                has_unsupported_recommendation_topic(line, facts_text)
                or should_rewrite_spill_storage_line(line)
            )
        ):
            stripped = strip_unsupported_prose(line, current_section, facts_text)
            if stripped is None:
                continue
            line = stripped
        normalized.append(line)

    return "\n".join(normalized).rstrip() + "\n"


def normalize_report_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(sanitize_report_text(text, ""), encoding="utf-8")


def validate_report_text(
    text: str,
    *,
    min_chars: int = MIN_REPORT_CHARS,
    min_sections: int = MIN_MARKDOWN_SECTIONS,
) -> list[str]:
    errors: list[str] = []
    stripped = text.strip()
    if len(stripped) < min_chars:
        errors.append(f"report is too short: {len(stripped)} chars, minimum is {min_chars}")

    section_lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("#")
    ]
    if len(section_lines) < min_sections:
        errors.append(
            f"report has too few markdown sections: {len(section_lines)}, minimum is {min_sections}"
        )

    for required in REQUIRED_REPORT_SECTIONS:
        if required not in section_lines:
            errors.append(f"missing required section: {required}")

    if section_lines.count("# Query Doctor Report") != 1:
        errors.append(
            f"expected exactly one '# Query Doctor Report' heading, found {section_lines.count('# Query Doctor Report')}"
        )

    return errors


def partial_report_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}.partial.md")


def validate_report_file(output_path: Path) -> list[str]:
    text = output_path.read_text(encoding="utf-8", errors="replace")
    return validate_report_text(text)


def move_failed_report_to_partial(output_path: Path) -> Path:
    partial_path = partial_report_path(output_path)
    if partial_path.exists():
        partial_path.unlink()
    output_path.replace(partial_path)
    return partial_path


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
        print(f"{PROGRESS_PREFIX} warning: could not parse ollama ps output; continuing", file=sys.stderr)
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
            print(f"{PROGRESS_PREFIX} warning: ollama stop {model_name!r} failed: {err}", file=sys.stderr)
            continue
        stopped.append(model_name)
    return stopped


def stream_ollama_report(
    *,
    prompt: str,
    model: str,
    output_path: Path,
    ollama_url: str,
    temperature: float,
    keep_alive: str,
) -> None:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are only a report writer. Use only supplied deterministic facts. "
                    "Write in Russian. Do not invent unsupported evidence or recommendations. "
                    "Keep cardinality mismatch separate from memory mismatch. "
                    "Do not treat mem ratio below 1.0 as memory underestimation evidence. "
                    "Do not recommend external network checks based only on TotalBytesSent. "
                    "Treat TotalBytesSent as intermediate/exchange data volume unless facts explicitly say network fault. "
                    "Do not call low-memory EXCHANGE operators memory bottlenecks. "
                    "Do not claim HDFS, external network, codegen, skew, or spill causes unless facts explicitly support them."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
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
    with urllib.request.urlopen(req, timeout=1800) as resp:
        with output_path.open("a", encoding="utf-8") as out:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"{PROGRESS_PREFIX} bad Ollama JSON line: {line[:200]}", file=sys.stderr)
                    continue

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
                            f"\n{PROGRESS_PREFIX} generated chars: {received}, elapsed: {elapsed}s",
                            file=sys.stderr,
                            flush=True,
                        )

                if event.get("done"):
                    break


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a Query Doctor markdown report from deterministic analysis facts only."
    )
    parser.add_argument("case_dir", help="Case directory containing analysis_facts.md")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--facts", default="analysis_facts.md", help="Facts file path, relative to CASE_DIR by default")
    parser.add_argument(
        "--out",
        default="diagnosis_report.md",
        help="Output report path. Relative paths are resolved under CASE_DIR; absolute paths are used as-is. Default: %(default)s",
    )
    parser.add_argument("--language", default="ru", help="Report language. Currently only ru is supported.")
    parser.add_argument("--dry-prompt", action="store_true", help="Print the final prompt and exit without calling Ollama")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--keep-alive",
        default=DEFAULT_KEEP_ALIVE,
        help="Ollama keep_alive value for the report model. Use 0 to unload after generation. Default: %(default)s",
    )
    parser.add_argument(
        "--stop-other-models",
        action="store_true",
        help="Before generation, unload other currently loaded Ollama models with `ollama ps` and `ollama stop MODEL`.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Debug only: skip post-generation report validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.language != "ru":
        print("ERROR: only --language ru is currently supported for the required report structure.", file=sys.stderr)
        return 2

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists() or not case_dir.is_dir():
        print(f"ERROR: case directory not found: {case_dir}", file=sys.stderr)
        return 2

    facts_path = resolve_case_file(case_dir, args.facts).resolve()
    output_path = resolve_case_file(case_dir, args.out).resolve()

    try:
        facts_text, facts_sha256 = read_required_facts(facts_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prompt = build_prompt(
        facts_text=facts_text,
        facts_path=facts_path,
        facts_sha256=facts_sha256,
        model=args.model,
        language=args.language,
    )

    if args.dry_prompt:
        print(prompt)
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_header(facts_path, facts_sha256, args.model), encoding="utf-8")

    print(f"{PROGRESS_PREFIX} case: {case_dir}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts: {facts_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts sha256: {facts_sha256}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} model: {args.model}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} resolved output path: {output_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} keep_alive: {args.keep_alive}", file=sys.stderr)

    if args.stop_other_models:
        stopped = stop_other_ollama_models(
            target_model=args.model,
        )
        if stopped:
            print(f"{PROGRESS_PREFIX} stopped other models: {', '.join(stopped)}", file=sys.stderr)
        else:
            print(f"{PROGRESS_PREFIX} no other loaded models to stop", file=sys.stderr)

    stream_ollama_report(
        prompt=prompt,
        model=args.model,
        output_path=output_path,
        ollama_url=args.ollama_url,
        temperature=args.temperature,
        keep_alive=args.keep_alive,
    )

    normalize_report_file(output_path)

    if not args.no_validate:
        validation_errors = validate_report_file(output_path)
        if validation_errors:
            partial_path = move_failed_report_to_partial(output_path)
            print(f"\n{PROGRESS_PREFIX} ERROR: generated report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    print(f"\n{PROGRESS_PREFIX} done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
