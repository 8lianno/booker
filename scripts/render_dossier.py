#!/usr/bin/env python3
"""Render a Markdown book dossier to HTML and, when possible, PDF."""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
from pathlib import Path


CSS = """
body {
  max-width: 820px;
  margin: 48px auto;
  padding: 0 28px;
  color: #171717;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.62;
}
h1, h2, h3, h4 {
  line-height: 1.25;
  margin-top: 1.7em;
}
h1 {
  font-size: 2rem;
  border-bottom: 2px solid #111;
  padding-bottom: 0.35rem;
}
h2 {
  font-size: 1.45rem;
  border-bottom: 1px solid #ddd;
  padding-bottom: 0.25rem;
}
h3 { font-size: 1.18rem; }
blockquote {
  border-left: 4px solid #ccc;
  margin-left: 0;
  padding-left: 1rem;
  color: #444;
}
code {
  background: #f3f3f3;
  padding: 0.1rem 0.25rem;
  border-radius: 4px;
}
pre {
  background: #f6f6f6;
  padding: 1rem;
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
}
th, td {
  border: 1px solid #d7d7d7;
  padding: 0.45rem 0.55rem;
  vertical-align: top;
}
th { background: #f4f4f4; }
@page { margin: 0.75in; }
"""


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "timed out")


def fallback_markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    out: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if not line:
            close_list()
            out.append("")
            continue
        if line.startswith("#"):
            close_list()
            level = min(len(line) - len(line.lstrip("#")), 6)
            text = line[level:].strip()
            out.append(f"<h{level}>{html.escape(text)}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:].strip())}</li>")
        else:
            close_list()
            out.append(f"<p>{html.escape(line)}</p>")
    close_list()
    return "\n".join(out)


def write_html(md_path: Path, html_path: Path, title: str | None) -> None:
    if shutil.which("pandoc"):
        result = run([
            "pandoc",
            str(md_path),
            "--standalone",
            "--metadata",
            f"title={title or md_path.stem}",
            "--css",
            "data:text/css," + CSS,
            "-o",
            str(html_path),
        ])
        if result.returncode == 0 and html_path.exists():
            return

    body = fallback_markdown_to_html(md_path.read_text(encoding="utf-8"))
    doc_title = html.escape(title or md_path.stem)
    html_path.write_text(
        f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>{doc_title}</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>\n",
        encoding="utf-8",
    )


def write_pdf(md_path: Path, html_path: Path, pdf_path: Path, timeout: int) -> str:
    if shutil.which("weasyprint"):
        result = run(["weasyprint", str(html_path), str(pdf_path)], timeout=timeout)
        if result.returncode == 0 and pdf_path.exists():
            return "pdf_ok_weasyprint"
        if result.returncode == 124:
            return "pdf_failed_weasyprint_timeout"

    if shutil.which("pandoc"):
        result = run(["pandoc", str(md_path), "-o", str(pdf_path)], timeout=timeout)
        if result.returncode == 0 and pdf_path.exists():
            return "pdf_ok_pandoc"
        if result.returncode == 124:
            return "pdf_failed_pandoc_timeout"
        return "pdf_failed_pandoc_or_pdf_engine"

    return "pdf_skipped_no_weasyprint_or_pandoc"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Markdown dossier to HTML and PDF when possible.")
    parser.add_argument("markdown", help="Path to dossier.md")
    parser.add_argument("--title", default=None, help="Optional document title")
    parser.add_argument("--out-dir", default=None, help="Optional output directory")
    parser.add_argument("--skip-pdf", action="store_true", help="Only write HTML; skip PDF rendering")
    parser.add_argument("--pdf-timeout", type=int, default=300, help="Seconds before a PDF renderer is stopped")
    args = parser.parse_args()

    md_path = Path(args.markdown).expanduser().resolve()
    if not md_path.exists():
        print(f"missing_markdown={md_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else md_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / f"{md_path.stem}.html"
    pdf_path = out_dir / f"{md_path.stem}.pdf"

    write_html(md_path, html_path, args.title)
    pdf_status = "pdf_skipped"
    if not args.skip_pdf:
        pdf_status = write_pdf(md_path, html_path, pdf_path, args.pdf_timeout)

    print(f"html={html_path}")
    print(f"pdf_status={pdf_status}")
    if pdf_path.exists():
        print(f"pdf={pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
