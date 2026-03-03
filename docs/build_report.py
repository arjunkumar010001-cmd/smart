#!/usr/bin/env python3
"""
Smart Hiring — Final Report Builder
====================================
Combines 7 HTML part files into a single print-ready HTML report.

Usage:
    python docs/build_report.py

Output:
    docs/Smart_Hiring_Final_Report.html
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PARTS_DIR = SCRIPT_DIR / "report_parts"
OUTPUT_FILE = SCRIPT_DIR / "Smart_Hiring_Final_Report.html"

PART_FILES = [
    "part1_frontmatter.html",
    "part2_introduction.html",
    "part3_literature_survey.html",
    "part4_system_analysis.html",
    "part5_methodology.html",
    "part6_implementation.html",
    "part7_results_conclusion.html",
]

# ---------------------------------------------------------------------------
# CSS Stylesheet (print-ready, A4, Times New Roman 12pt)
# ---------------------------------------------------------------------------
CSS = r"""
/* ========== PAGE & PRINT SETUP ========== */
@page {
    size: A4;
    margin: 1in;
}

@media print {
    body { margin: 0; padding: 0; }
    .page { page-break-after: always; }
    .page:last-child { page-break-after: auto; }
    .no-print { display: none !important; }
}

/* ========== BASE TYPOGRAPHY ========== */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: "Times New Roman", Times, serif;
    font-size: 12pt;
    line-height: 1.6;
    color: #000;
    background: #f5f5f5;
}

/* ========== PAGE CONTAINER ========== */
.page {
    width: 8.27in;         /* A4 width */
    min-height: 11.69in;   /* A4 height */
    margin: 0.5in auto;
    padding: 1in;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    page-break-after: always;
}

.page:last-child {
    page-break-after: auto;
}

/* ========== HEADINGS ========== */
h1 {
    font-size: 22pt;
    text-align: center;
    margin-bottom: 18pt;
    text-transform: uppercase;
    letter-spacing: 1px;
}

h2 {
    font-size: 16pt;
    margin-top: 18pt;
    margin-bottom: 12pt;
    border-bottom: 2px solid #1a237e;
    padding-bottom: 4pt;
    color: #1a237e;
}

h2.chapter-title {
    text-align: center;
    font-size: 20pt;
    border-bottom: 3px double #1a237e;
    padding-bottom: 8pt;
    margin-bottom: 20pt;
    margin-top: 0;
    line-height: 1.4;
}

h3 {
    font-size: 14pt;
    margin-top: 16pt;
    margin-bottom: 8pt;
    color: #283593;
}

h4 {
    font-size: 12pt;
    font-weight: bold;
    margin-top: 12pt;
    margin-bottom: 6pt;
    color: #333;
}

/* ========== PARAGRAPHS & LISTS ========== */
p {
    margin-bottom: 8pt;
    text-align: justify;
}

ul, ol {
    margin-left: 24pt;
    margin-bottom: 10pt;
}

li {
    margin-bottom: 4pt;
}

/* ========== COVER PAGE ========== */
.cover-page {
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 9in;
}

.cover-page h1 {
    font-size: 26pt;
    margin-bottom: 10pt;
    color: #1a237e;
}

.cover-page .subtitle {
    font-size: 14pt;
    font-style: italic;
    margin-bottom: 30pt;
    color: #555;
}

.cover-page .university {
    font-size: 16pt;
    font-weight: bold;
    margin-bottom: 4pt;
    text-transform: uppercase;
}

.cover-page .department {
    font-size: 14pt;
    margin-bottom: 20pt;
    color: #333;
}

.cover-page .detail-line {
    font-size: 12pt;
    margin-bottom: 4pt;
}

.cover-page .year {
    font-size: 14pt;
    font-weight: bold;
    margin-top: 20pt;
}

/* ========== TABLES ========== */
.data-table {
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0;
    font-size: 10pt;
}

.data-table th,
.data-table td {
    border: 1px solid #333;
    padding: 6pt 8pt;
    text-align: left;
    vertical-align: top;
}

.data-table th {
    background-color: #1a237e;
    color: #fff;
    font-weight: bold;
    text-align: center;
}

.data-table tr:nth-child(even) {
    background-color: #f0f0f8;
}

.data-table .pass {
    color: #2e7d32;
    font-weight: bold;
}

.data-table .fail {
    color: #c62828;
    font-weight: bold;
}

.table-caption {
    text-align: center;
    font-size: 10pt;
    font-style: italic;
    margin-top: 4pt;
    margin-bottom: 16pt;
    color: #555;
}

/* ========== TOC TABLE ========== */
.toc-table {
    width: 100%;
    border-collapse: collapse;
    margin: 10pt 0;
}

.toc-table td {
    padding: 3pt 6pt;
    border: none;
    vertical-align: top;
}

.toc-table .toc-chapter {
    font-weight: bold;
    padding-top: 10pt;
}

.toc-table .toc-page {
    text-align: right;
    width: 40pt;
}

/* ========== FORMULA BOX ========== */
.formula-box {
    background: #f8f8ff;
    border: 1px solid #c5cae9;
    border-left: 4px solid #1a237e;
    padding: 12pt 16pt;
    margin: 12pt 0;
    font-family: "Cambria Math", "Times New Roman", serif;
    font-size: 11pt;
    text-align: center;
    border-radius: 4px;
}

.formula-box p {
    text-align: center;
    margin-bottom: 4pt;
}

/* ========== DIAGRAM BOX ========== */
.diagram-box {
    background: #fafafa;
    border: 2px solid #90a4ae;
    padding: 16pt;
    margin: 14pt 0;
    font-family: "Courier New", Courier, monospace;
    font-size: 8.5pt;
    line-height: 1.3;
    white-space: pre;
    overflow-x: auto;
    border-radius: 4px;
    text-align: center;
}

.diagram-box p.diagram-caption {
    font-family: "Times New Roman", Times, serif;
    font-size: 10pt;
    font-style: italic;
    text-align: center;
    margin-top: 8pt;
    margin-bottom: 0;
    white-space: normal;
}

/* ========== CODE BLOCKS ========== */
.code-block {
    background: #263238;
    color: #e0e0e0;
    padding: 12pt 16pt;
    margin: 12pt 0;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
    line-height: 1.5;
    border-radius: 4px;
    overflow-x: auto;
    white-space: pre;
}

.code-block .code-comment {
    color: #78909c;
    font-style: italic;
}

.code-block .code-keyword {
    color: #82b1ff;
}

.code-block .code-string {
    color: #c3e88d;
}

.code-block .code-function {
    color: #ffcb6b;
}

/* ========== SCREENSHOT PLACEHOLDER ========== */
.screenshot-placeholder {
    border: 2px dashed #90a4ae;
    background: #eceff1;
    padding: 30pt;
    margin: 14pt 0;
    text-align: center;
    color: #607d8b;
    font-style: italic;
    font-size: 11pt;
    border-radius: 6px;
    min-height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* ========== REFERENCES LIST ========== */
ol.references {
    counter-reset: ref-counter;
    list-style: none;
    margin-left: 0;
    padding-left: 0;
}

ol.references li {
    counter-increment: ref-counter;
    margin-bottom: 10pt;
    padding-left: 36pt;
    text-indent: -36pt;
    text-align: justify;
}

ol.references li::before {
    content: "[" counter(ref-counter) "]  ";
    font-weight: bold;
    color: #1a237e;
}

/* ========== SIGNATURE BLOCK ========== */
.signature-block {
    display: flex;
    justify-content: space-between;
    margin-top: 40pt;
    flex-wrap: wrap;
}

.signature-item {
    text-align: center;
    min-width: 200px;
    margin-top: 20pt;
}

.signature-line {
    border-top: 1px solid #000;
    margin-top: 40pt;
    padding-top: 4pt;
}

/* ========== MISC UTILITIES ========== */
.text-center { text-align: center; }
.text-bold { font-weight: bold; }
.mt-20 { margin-top: 20pt; }
.mb-20 { margin-bottom: 20pt; }
.page-break { page-break-after: always; }

hr.separator {
    border: none;
    border-top: 1px solid #ccc;
    margin: 16pt 0;
}

/* ========== PRINT BUTTON (screen only) ========== */
.print-btn-container {
    text-align: center;
    padding: 16pt;
    background: #1a237e;
    position: sticky;
    top: 0;
    z-index: 1000;
}

.print-btn {
    background: #fff;
    color: #1a237e;
    border: 2px solid #fff;
    padding: 10pt 28pt;
    font-size: 14pt;
    font-weight: bold;
    cursor: pointer;
    border-radius: 6px;
    font-family: Arial, sans-serif;
}

.print-btn:hover {
    background: #e8eaf6;
}

@media print {
    .print-btn-container { display: none !important; }
}
"""

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Hiring — Final Project Report</title>
    <style>
{css}
    </style>
</head>
<body>

<!-- Print button (visible on screen only) -->
<div class="print-btn-container no-print">
    <button class="print-btn" onclick="window.print()">
        &#128424; Print / Save as PDF
    </button>
</div>

<!-- ==================== REPORT CONTENT ==================== -->
{content}

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build Logic
# ---------------------------------------------------------------------------
def build_report():
    """Read all part files and combine into a single HTML report."""
    print("=" * 60)
    print("  Smart Hiring — Final Report Builder")
    print("=" * 60)

    # Verify parts directory exists
    if not PARTS_DIR.exists():
        print(f"\n[ERROR] Parts directory not found: {PARTS_DIR}")
        sys.exit(1)

    # Read each part
    content_parts = []
    for filename in PART_FILES:
        filepath = PARTS_DIR / filename
        if not filepath.exists():
            print(f"  [WARNING] Missing: {filename} — skipping")
            continue

        print(f"  [OK] Reading: {filename}")
        with open(filepath, "r", encoding="utf-8") as f:
            content_parts.append(f.read())

    if not content_parts:
        print("\n[ERROR] No part files found. Nothing to build.")
        sys.exit(1)

    # Combine
    combined_content = "\n\n".join(content_parts)

    # Build final HTML
    final_html = HTML_TEMPLATE.format(
        css=CSS,
        content=combined_content,
    )

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)

    file_size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\n{'=' * 60}")
    print(f"  [SUCCESS] Report built: {OUTPUT_FILE.name}")
    print(f"  Size: {file_size_kb:.1f} KB")
    print(f"  Parts combined: {len(content_parts)} / {len(PART_FILES)}")
    print(f"  Output: {OUTPUT_FILE}")
    print(f"{'=' * 60}")
    print(f"\n  Open in browser → Print → Save as PDF")
    print(f"  (Use 'Print / Save as PDF' button at the top)\n")


if __name__ == "__main__":
    build_report()
