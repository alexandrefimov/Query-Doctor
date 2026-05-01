"""Pure HTML rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


DEMO_STAGES = (
    (0, "Проверяем Query ID", 4),
    (1, "Собираем или переиспользуем профиль", 24),
    (2, "Анализируем профиль", 50),
    (3, "Генерируем отчёт", 74),
    (4, "Проверяем отчёт", 90),
    (5, "Готово", 100),
)


def render_page(
    settings: Any,
    *,
    query_id: str = "",
    report_mode: str = "user",
    result: Any | None = None,
    job: Any | None = None,
    error: object | None = None,
    active_nav: str = "home",
    extra_sections: list[str] | None = None,
) -> str:
    query_value = html.escape(query_id, quote=True)
    admin_checked = "checked" if report_mode == "admin" else ""
    user_checked = "checked" if report_mode == "user" else ""
    has_output = result is not None or error is not None or job is not None
    shell_class = "page-shell page-shell--with-result" if has_output else "page-shell"
    body = [
        "<!doctype html>",
        "<html lang=\"ru\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Query Doctor Demo</title>",
        "<style>",
        ":root{color-scheme:dark;--bg:#111318;--panel:#171a20;--tile:#101318;--line:#2a3038;--line-soft:#222830;--text:#eef2f7;--muted:#9aa3ad;--accent:#7aa2f7;--accent-soft:#22304a;--danger:#ef8585;--ok:#8dd8a2;--shadow:0 14px 42px rgba(0,0,0,.28)}",
        "*{box-sizing:border-box}html{min-height:100%}body{min-height:100vh;margin:0;font-family:'Segoe UI',system-ui,-apple-system,BlinkMacSystemFont,sans-serif;background:radial-gradient(circle at 74% 38%,rgba(122,162,247,.09),transparent 30%),#101216;color:var(--text);line-height:1.4;overflow-x:hidden}fieldset{border:0;margin:0;padding:0}",
        ".demo-watermark{position:fixed;right:calc(50% - 500px);top:50%;width:min(24vw,230px);height:auto;opacity:.34;pointer-events:none;z-index:0;transform:translateY(-48%);filter:drop-shadow(0 14px 28px rgba(0,0,0,.28))}",
        ".page-shell{position:relative;z-index:1;min-height:100vh;width:min(100% - 32px,700px);margin:0 auto;display:flex;flex-direction:column;justify-content:center;gap:10px;padding:22px 0}.page-shell--with-result{justify-content:flex-start;padding-top:22px;padding-bottom:34px}",
        ".hero-card,.summary-card,.report-card,.progress-card{border:1px solid var(--line);background:rgba(23,26,32,.96);box-shadow:var(--shadow);border-radius:12px}",
        ".hero-card{padding:17px 18px 16px}.top-nav{display:flex;justify-content:flex-end;gap:8px;margin-bottom:10px}.nav-link{display:inline-flex;align-items:center;min-height:30px;padding:5px 9px;border:1px solid var(--line-soft);border-radius:8px;color:var(--muted);text-decoration:none;font-weight:650;font-size:.78rem}.nav-link:hover,.nav-link:focus{border-color:var(--accent);color:#eaf1ff;outline:none}.nav-link--active{background:var(--accent-soft);color:#eaf1ff;border-color:rgba(122,162,247,.42)}.brand{text-align:center;margin-bottom:14px}.brand-home{display:inline-grid;justify-items:center;color:inherit;text-decoration:none}.brand-home:focus{outline:2px solid #9bb8f7;outline-offset:5px;border-radius:12px}.brand-mark-wrap{display:inline-grid;place-items:center;width:46px;height:46px;margin-bottom:7px;border:1px solid var(--line);border-radius:12px;background:#11151b}.brand-mark{width:36px;height:36px;display:block}.brand h1{margin:0;font-size:clamp(1.48rem,3vw,2rem);line-height:1.06;font-weight:650;letter-spacing:0}.brand p{margin:6px auto 0;max-width:500px;color:var(--muted);font-size:.86rem}",
        ".query-row{display:grid;grid-template-columns:1fr 112px;gap:9px;align-items:end}.field label,.fieldset-title{display:block;margin:0 0 5px;color:#d7dde5;font-weight:600;font-size:.78rem}.field input[type=text]{width:100%;height:36px;border-radius:8px;border:1px solid var(--line);background:#101318;color:var(--text);font:inherit;padding:0 10px;outline:none}.field input[type=text]:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(122,162,247,.18)}",
        ".mode-card{min-width:0;margin-top:10px}.segmented{display:grid;grid-template-columns:1fr 1fr;gap:0;background:#101318;border:1px solid var(--line);border-radius:8px;overflow:hidden}.segmented input{position:absolute;opacity:0;pointer-events:none}.segmented span{display:block;text-align:center;padding:7px 10px;color:var(--muted);font-weight:600;border-right:1px solid var(--line)}.segmented label:last-child span{border-right:0}.segmented input:checked+span{background:var(--accent-soft);color:#eaf1ff}",
        ".primary{height:36px;border:1px solid rgba(122,162,247,.52);border-radius:8px;background:#345da8;color:white;font:inherit;font-weight:650;padding:0 14px;min-width:0;cursor:pointer;box-shadow:none}.primary:hover{background:#3d68b5}.primary:focus{outline:2px solid #9bb8f7;outline-offset:2px}.primary[disabled]{opacity:.62;cursor:wait}",
        ".error-card{border:1px solid rgba(239,133,133,.5);background:rgba(56,26,31,.92);padding:12px 14px;color:#fee2e2;border-radius:10px}.error-card strong{color:#fecaca}",
        ".progress-card{padding:13px 14px}.progress-card--hidden{display:none}.progress-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.progress-title{font-weight:650}.progress-stage{color:var(--muted);font-size:.84rem}.progress-bar{height:6px;border-radius:999px;background:#101318;border:1px solid var(--line-soft);overflow:hidden}.progress-fill{display:block;height:100%;width:4%;background:#7aa2f7;transition:width .2s ease}.progress-note{margin:8px 0 0;color:var(--muted);font-size:.77rem}",
        ".summary-card{padding:13px 14px;border-color:#2c4434}.summary-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.status-pill{display:inline-flex;align-items:center;gap:8px;border-radius:8px;padding:4px 8px;background:rgba(141,216,162,.1);border:1px solid rgba(141,216,162,.3);color:#c9f7d3;font-weight:700}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.metric{border:1px solid var(--line-soft);background:rgba(16,19,24,.88);border-radius:8px;padding:8px}.metric span{display:block;color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.04em}.metric strong,.metric code{display:block;margin-top:4px;color:var(--text);font-size:.88rem;overflow-wrap:anywhere}.metric--wide{grid-column:span 3}",
        ".report-card{padding:0;overflow:hidden}.report-card summary{cursor:pointer;padding:11px 14px;font-size:.94rem;font-weight:700;border-bottom:1px solid var(--line);background:#151920}.report-body{padding:15px;color:#e8edf5;font-size:.9rem}.report-body h1,.report-body h2,.report-body h3,.report-body h4{margin:1.1em 0 .45em;line-height:1.18}.report-body h1:first-child,.report-body h2:first-child,.report-body h3:first-child{margin-top:0}.report-body h1{font-size:1.35rem}.report-body h2{font-size:1.18rem}.report-body h3{font-size:1.04rem}.report-body p{margin:.7em 0}.report-body ul,.report-body ol{margin:.55em 0 .8em;padding-left:1.35rem}.report-body li{margin:.28em 0}.report-body code{background:#0d1117;border:1px solid var(--line-soft);border-radius:5px;padding:.08rem .28rem;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}.report-body pre{margin:.75em 0;padding:12px;background:#0d1117;border:1px solid var(--line-soft);border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}.report-body pre code{border:0;background:transparent;padding:0}.report-body blockquote{margin:.75em 0;padding:.35em .8em;border-left:3px solid var(--accent);background:rgba(122,162,247,.07);color:#d9e2ee}.report-body table{width:100%;border-collapse:collapse;margin:.8em 0;font-size:.86rem}.report-body th,.report-body td{border:1px solid var(--line-soft);padding:6px 8px;text-align:left;vertical-align:top}.report-body th{background:#151920;color:#f2f6fb}",
        "@media (max-width:720px){.page-shell{width:min(100% - 20px,700px);padding:18px 0}.hero-card{padding:16px}.query-row{grid-template-columns:1fr}.summary-grid{grid-template-columns:1fr}.metric--wide{grid-column:span 1}.demo-watermark{right:-58px;top:auto;bottom:22px;width:170px;opacity:.16;transform:none}}",
        "</style>",
        render_client_script(),
        "</head>",
        "<body>",
        render_watermark_svg(),
        f"<main class=\"{shell_class}\">",
        "<section class=\"hero-card\" aria-label=\"Query Doctor Demo form\">",
        render_top_nav(active_nav),
        "<header class=\"brand\">",
        "<a class=\"brand-home\" href=\"/\" aria-label=\"Query Doctor home\">",
        "<div class=\"brand-mark-wrap\">",
        render_brand_mark_svg(),
        "</div>",
        "<h1>Query Doctor Demo</h1>",
        "</a>",
        "</header>",
        "<form id=\"analyze-form\" method=\"post\" action=\"/analyze\">",
        "<div class=\"query-row\">",
        "<div class=\"field\">",
        "<label for=\"query_id\">Query ID</label>",
        f"<input id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" autocomplete=\"off\" required placeholder=\"fa469f95f6fb7286:ea9f070d00000000\">",
        "</div>",
        "<button class=\"primary\" type=\"submit\">Run</button>",
        "</div>",
        "<fieldset class=\"mode-card\" aria-labelledby=\"mode_title\">",
        "<legend id=\"mode_title\" class=\"fieldset-title\">Режим отчёта</legend>",
        "<div class=\"segmented\">",
        f"<label><input type=\"radio\" name=\"mode\" value=\"user\" {user_checked}><span>user</span></label>",
        f"<label><input type=\"radio\" name=\"mode\" value=\"admin\" {admin_checked}><span>admin</span></label>",
        "</div>",
        "</fieldset>",
        "</form>",
        "</section>",
        render_pending_progress_panel(),
    ]
    if error is not None:
        body.append(f"<section class=\"error-card\" role=\"alert\"><strong>FAILED</strong><br>{html.escape(str(error))}</section>")
    if job is not None:
        body.append(render_job_panel(job))
    if result is not None:
        body.extend(render_result(result))
    if extra_sections:
        body.extend(extra_sections)
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body)


def render_top_nav(active: str) -> str:
    home_class = "nav-link nav-link--active" if active == "home" else "nav-link"
    readme_class = "nav-link nav-link--active" if active == "readme" else "nav-link"
    return (
        "<nav class=\"top-nav\" aria-label=\"Main navigation\">"
        f"<a class=\"{home_class}\" href=\"/\">Home</a>"
        f"<a class=\"{readme_class}\" href=\"/readme\">README</a>"
        "</nav>"
    )


def render_readme_page(settings: Any) -> str:
    return render_page(
        settings,
        active_nav="readme",
        extra_sections=[render_readme_card(settings.repo_dir)],
    )


def render_readme_card(repo_dir: Path) -> str:
    readme_text = read_repository_readme(repo_dir)
    if readme_text is None:
        readme_html = "<p>README.md не найден в корне репозитория.</p>"
    else:
        readme_html = render_report_markdown_html(readme_text)
    return (
        "<details class=\"report-card\" open>"
        "<summary>README.md</summary>"
        f"<div class=\"report-body\">{readme_html}</div>"
        "</details>"
    )


def read_repository_readme(repo_dir: Path) -> str | None:
    try:
        return (repo_dir / "README.md").read_text(encoding="utf-8")
    except OSError:
        return None


def render_client_script() -> str:
    return """<script>
document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('analyze-form');
  var pending = document.getElementById('pending-panel');
  if (form && pending) {
    form.addEventListener('submit', function () {
      pending.classList.remove('progress-card--hidden');
      var button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Запускаем...';
      }
    });
  }
  var jobPanel = document.querySelector('[data-job-status-url]');
  if (!jobPanel) {
    return;
  }
  var stage = document.getElementById('job-stage');
  var fill = document.getElementById('job-progress-fill');
  var resultSlot = document.getElementById('job-result-slot');
  var errorSlot = document.getElementById('job-error-slot');
  function poll() {
    fetch(jobPanel.getAttribute('data-job-status-url'), {cache: 'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (stage) { stage.textContent = data.stage || ''; }
        if (fill) { fill.style.width = String(data.progress || 0) + '%'; }
        if (data.status === 'ok') {
          if (resultSlot) { resultSlot.innerHTML = data.result_html || ''; }
          return;
        }
        if (data.status === 'failed') {
          if (errorSlot) {
            errorSlot.hidden = false;
            errorSlot.textContent = data.error || 'Analysis failed.';
          }
          return;
        }
        window.setTimeout(poll, 1200);
      })
      .catch(function () { window.setTimeout(poll, 1800); });
  }
  poll();
});
</script>"""


def render_pending_progress_panel() -> str:
    stage = DEMO_STAGES[0]
    return (
        "<section id=\"pending-panel\" class=\"progress-card progress-card--hidden\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Анализ запущен</span>"
        f"<span class=\"progress-stage\">{html.escape(stage[1])}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\"><span class=\"progress-fill\"></span></div>"
        "<p class=\"progress-note\">Обычно это занимает от нескольких секунд до пары минут.</p>"
        "</section>"
    )


def render_job_panel(job: Any) -> str:
    result_html = job.result_html if job.status == "ok" else ""
    error_html = html.escape(job.error) if job.status == "failed" else ""
    error_hidden = "" if job.status == "failed" else " hidden"
    return (
        f"<section class=\"progress-card\" data-job-status-url=\"/jobs/{html.escape(job.job_id)}/status\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Анализ выполняется</span>"
        f"<span id=\"job-stage\" class=\"progress-stage\">{html.escape(job.stage_label)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span id=\"job-progress-fill\" class=\"progress-fill\" style=\"width:{job.progress}%\"></span>"
        "</div>"
        "<p class=\"progress-note\">Обычно это занимает от нескольких секунд до пары минут.</p>"
        f"<div id=\"job-error-slot\" class=\"error-card\" role=\"alert\"{error_hidden}>{error_html}</div>"
        f"<div id=\"job-result-slot\">{result_html}</div>"
        "</section>"
    )


def render_watermark_svg() -> str:
    return """<svg class="demo-watermark doctor-impala-mascot" viewBox="0 0 220 220" aria-hidden="true" focusable="false">
<path d="M73 97 C48 70 37 42 44 22 C62 41 80 66 91 94" fill="none" stroke="#7aa2f7" stroke-width="10" stroke-linecap="round"/>
<path d="M147 97 C172 70 183 42 176 22 C158 41 140 66 129 94" fill="none" stroke="#7aa2f7" stroke-width="10" stroke-linecap="round"/>
<path d="M72 88 C88 64 132 64 148 88 C166 116 157 158 110 184 C63 158 54 116 72 88 Z" fill="rgba(122,162,247,.12)" stroke="#8fb0f7" stroke-width="8" stroke-linejoin="round"/>
<path d="M88 78 H132 L125 58 H95 Z" fill="rgba(238,242,247,.08)" stroke="#dbe6f7" stroke-width="5" stroke-linejoin="round"/>
<path d="M110 64 v22 M99 75 h22" stroke="#7aa2f7" stroke-width="6" stroke-linecap="round"/>
<path d="M87 122 C98 133 122 133 133 122" fill="none" stroke="#e8eef7" stroke-width="7" stroke-linecap="round"/>
<path d="M74 151 C48 159 44 183 62 197 C80 211 104 200 104 177" fill="none" stroke="#7aa2f7" stroke-width="6" stroke-linecap="round"/>
<circle cx="104" cy="177" r="9" fill="rgba(122,162,247,.12)" stroke="#e8eef7" stroke-width="5"/>
</svg>"""


def render_brand_mark_svg() -> str:
    return """<svg class="brand-mark doctor-impala-mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
<path d="M21 29 C13 20 10 11 13 5 C19 12 25 21 29 30" fill="none" stroke="#7aa2f7" stroke-width="3.5" stroke-linecap="round"/>
<path d="M43 29 C51 20 54 11 51 5 C45 12 39 21 35 30" fill="none" stroke="#7aa2f7" stroke-width="3.5" stroke-linecap="round"/>
<path d="M20 25 C25 16 39 16 44 25 C50 36 43 51 32 58 C21 51 14 36 20 25 Z" fill="rgba(122,162,247,.13)" stroke="#9bb8f7" stroke-width="2.6" stroke-linejoin="round"/>
<path d="M24 23 H40 L37 16 H27 Z" fill="rgba(238,242,247,.10)" stroke="#dbe6f7" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M32 18 v11 M26.5 23.5 h11" stroke="#7aa2f7" stroke-width="3" stroke-linecap="round"/>
<path d="M25 40 C29 44 35 44 39 40" fill="none" stroke="#e8eef7" stroke-width="2.8" stroke-linecap="round"/>
<path d="M12 45 C7 48 7 55 12 58 C18 61 24 56 23 51" fill="none" stroke="#7aa2f7" stroke-width="2.2" stroke-linecap="round"/>
<circle cx="23" cy="51" r="2.8" fill="rgba(122,162,247,.15)" stroke="#e8eef7" stroke-width="1.8"/>
</svg>"""


def render_result(result: Any) -> list[str]:
    return [
        "<section class=\"summary-card\" aria-label=\"Analysis summary\">",
        "<div class=\"summary-head\"><span class=\"status-pill\">Status: OK</span><strong>Краткая сводка</strong></div>",
        "<div class=\"summary-grid\">",
        f"<div class=\"metric\"><span>Case source</span><strong>{html.escape(result.case_source)}</strong></div>",
        f"<div class=\"metric\"><span>Parsed operators</span><strong>{html.escape(result.parsed_operators)}</strong></div>",
        f"<div class=\"metric\"><span>Report mode</span><strong>{html.escape(result.report_mode)}</strong></div>",
        f"<div class=\"metric\"><span>Cardinality anomalies</span><strong>{html.escape(result.cardinality_anomalies)}</strong></div>",
        f"<div class=\"metric\"><span>Memory anomalies</span><strong>{html.escape(result.memory_anomalies)}</strong></div>",
        f"<div class=\"metric\"><span>Query ID</span><code>{html.escape(result.query_id)}</code></div>",
        f"<div class=\"metric metric--wide\"><span>Collected case directory</span><code>{html.escape(str(result.case_dir))}</code></div>",
        render_retry_metric(result),
        "</div>",
        "</section>",
        "<details class=\"report-card\" open>",
        "<summary>Полный отчёт</summary>",
        f"<div class=\"report-body\">{render_report_markdown_html(result.report_text)}</div>",
        "</details>",
    ]


def render_report_markdown_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{render_inline_markdown(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if list_type is not None:
            tag = "ol" if list_type == "ol" else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{tag}>")
            list_items.clear()
            list_type = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        fence_match = re.match(r"^\s*(```|~~~)", line)
        if fence_match:
            flush_paragraph()
            flush_list()
            fence = fence_match.group(1)
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code_text = html.escape("\n".join(code_lines))
            blocks.append(f"<pre><code>{code_text}</code></pre>")
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_markdown_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            blocks.append(f"<h{level}>{render_inline_markdown(heading_match.group(2))}</h{level}>")
            index += 1
            continue

        quote_match = re.match(r"^\s*>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines = [quote_match.group(1)]
            index += 1
            while index < len(lines):
                next_quote = re.match(r"^\s*>\s?(.*)$", lines[index])
                if not next_quote:
                    break
                quote_lines.append(next_quote.group(1))
                index += 1
            quote_text = "<br>".join(render_inline_markdown(part) for part in quote_lines)
            blocks.append(f"<blockquote>{quote_text}</blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            current_type = "ol" if ordered else "ul"
            if list_type != current_type:
                flush_list()
                list_type = current_type
            item_text = ordered.group(1) if ordered else unordered.group(1)
            list_items.append(render_inline_markdown(item_text))
            index += 1
            continue

        flush_list()
        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_inline_markdown(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return "|" in lines[index] and is_table_separator(lines[index + 1])


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|") if cell.strip()]


def render_markdown_table(table_lines: list[str]) -> str:
    header = split_table_row(table_lines[0])
    rows = [split_table_row(line) for line in table_lines[2:]]
    header_html = "".join(f"<th>{render_inline_markdown(cell)}</th>" for cell in header)
    body_rows: list[str] = []
    for row in rows:
        cells = row[: len(header)] + [""] * max(0, len(header) - len(row))
        body_rows.append("<tr>" + "".join(f"<td>{render_inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
    return "<table><thead><tr>" + header_html + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"


def render_retry_metric(result: Any) -> str:
    if not result.report_retry:
        return ""
    return (
        "<div class=\"metric metric--wide\"><span>Report generation</span>"
        "<strong>regenerated after validator retry</strong></div>"
    )
