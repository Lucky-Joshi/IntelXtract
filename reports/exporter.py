"""Phase 19 (S19.2-S19.4): exporters for the shared report model.

Producers:
* JSON — canonical model dump (``.json``)
* CSV  — row per finding (``.csv``)
* Markdown — one-file human-readable report (``.md``)
* HTML — Jinja2 template rendered from ``BRAND.md`` tokens (``.html``)
* PDF  — WeasyPrint from the styled HTML; when WeasyPrint or its system
  libraries are missing, a print-friendly HTML fallback is returned with an
  explicit warning (``.html`` recommended on disk).
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from reports.brand import brand_tokens
from reports.builder import SEVERITY_ORDER, ReportModel

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "j2", "xml"]),
)


@dataclass
class ExportResult:
    """Bytes ready to write plus the actual content format."""

    format: str
    data: bytes
    warning: str | None = None


_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def _severity_rank(severity: Any) -> int:
    return int(_SEVERITY_RANK.get(str(severity), 10))


def _render_template(
    model: ReportModel, template_name: str, *, print_mode: bool = False
) -> str:
    tokens = brand_tokens()
    meta = model.to_dict()
    return _env.get_template(template_name).render(
        model=meta,
        brand=tokens,
        print_mode=print_mode,
        severity_order=SEVERITY_ORDER,
    )


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _export_json(model: ReportModel) -> ExportResult:
    data = json.dumps(
        model.to_dict(), indent=2, ensure_ascii=False, default=str
    ).encode("utf-8")
    return ExportResult(format="json", data=data)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _export_csv(model: ReportModel) -> ExportResult:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["severity", "module", "title", "confidence", "evidence"])
    ranked = sorted(
        model.findings,
        key=lambda item: (
            _severity_rank(item["severity"]),
            item["module"],
            item["title"],
        ),
    )
    for finding in ranked:
        writer.writerow(
            [
                finding["severity"],
                finding["module"],
                finding["title"],
                "" if finding.get("confidence") is None else finding["confidence"],
                finding["evidence"],
            ]
        )
    return ExportResult(format="csv", data=buffer.getvalue().encode("utf-8"))


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _export_markdown(model: ReportModel) -> ExportResult:
    target = str((model.target or {}).get("value") or "unknown")
    lines = [
        f"# {brand_tokens()['name']} — reconnaissance report",
        "",
        f"**Target:** {target}",
        f"**Generated:** {model.generated_at}",
        f"**Overall risk:** {str((model.risk or {}).get('rating') or 'low').upper()}",
        "",
        "## Executive summary",
        "",
    ]
    lines.extend(f"- {line}" for line in model.executive_summary)
    lines += ["", "## Risk overview", ""]
    categories = (model.risk or {}).get("categories") or {}
    for name, meta in categories.items():
        if not isinstance(meta, dict):
            continue
        lines.append(
            f"- **{name}:** {float(meta.get('score') or 0.0):.1f} across "
            f"{int(meta.get('rules') or 0)} rule(s)"
        )
    lines += ["", "## Findings", ""]
    lines.append("| severity | module | title | evidence |")
    lines.append("| --- | --- | --- | --- |")
    ranked = sorted(
        model.findings,
        key=lambda item: (
            _severity_rank(item["severity"]),
            item["module"],
            item["title"],
        ),
    )
    for finding in ranked:
        evidence = (finding["evidence"] or "").replace("|", "\\|").replace("\n", " ")
        title = (finding["title"] or "").replace("|", "\\|")
        lines.append(
            f"| {finding['severity']} | {finding['module']} | {title}"
            f" | {evidence[:80]} |"
        )
    if model.timeline:
        lines += ["", "## Timeline", ""]
        for event in model.timeline:
            lines.append(f"- {event['ts']:.0f} — {event['label']}")
    lines += ["", "## Methodology", ""]
    lines.extend(f"- {point}" for point in model.methodology)
    return ExportResult(format="md", data=("\n".join(lines) + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# HTML / PDF
# ---------------------------------------------------------------------------


def _export_html(model: ReportModel, *, print_mode: bool = False) -> ExportResult:
    rendered = _render_template(model, "report.html.j2", print_mode=print_mode)
    return ExportResult(format="html", data=rendered.encode("utf-8"))


def _load_weasyprint_html() -> Any:
    """Import WeasyPrint's ``HTML`` class lazily; ``None`` if unavailable."""
    if importlib.util.find_spec("weasyprint") is None:
        return None
    module = importlib.import_module("weasyprint")
    html_class = getattr(module, "HTML", None)
    return html_class if callable(html_class) else None


def _export_pdf(model: ReportModel) -> ExportResult:
    html_class = _load_weasyprint_html()
    if html_class is None:
        fallback = _export_html(model, print_mode=True)
        return ExportResult(
            format="html",
            data=fallback.data,
            warning=(
                "WeasyPrint is not installed; wrote print-friendly HTML "
                "instead of PDF. Install `weasyprint` (and its system "
                "libraries) to get real PDF output."
            ),
        )
    try:
        rendered = _render_template(model, "report.html.j2")
        pdf_bytes = html_class(string=rendered).write_pdf()
        return ExportResult(format="pdf", data=pdf_bytes)
    except Exception as exc:  # missing system libs (pango, cairo, ...)
        fallback = _export_html(model, print_mode=True)
        return ExportResult(
            format="html",
            data=fallback.data,
            warning=(
                f"WeasyPrint failed ({type(exc).__name__}: {exc}); wrote "
                "print-friendly HTML instead of PDF."
            ),
        )


def export_report(model: ReportModel, output_format: str) -> ExportResult:
    """Render ``model`` in ``output_format``, returning bytes + caveats."""
    fmt = output_format.lower().strip()
    if fmt == "json":
        return _export_json(model)
    if fmt == "csv":
        return _export_csv(model)
    if fmt == "md" or fmt in ("markdown", "mdown"):
        return _export_markdown(model)
    if fmt == "pdf":
        return _export_pdf(model)
    if fmt == "html":
        return _export_html(model)
    raise ValueError(f"unsupported report format: {output_format!r}")


__all__ = ["ExportResult", "export_report"]
