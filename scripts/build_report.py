"""Build the R&D report PDF from docs/REPORT.md.

Run: python -m scripts.build_report --name "Your Name" --roll "22I-0000"
Writes docs/report/GigBid_RD_Report.html and (via headless Chromium) GigBid_RD_Report.pdf.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "report"

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body { font: 10.2pt/1.45 "Segoe UI", Inter, Arial, sans-serif; color: #24141b; margin: 0; }
h1 { font-size: 17pt; color: #7a1e3a; margin: 0 0 4mm; }
h2 { font-size: 12.5pt; color: #7a1e3a; margin: 6mm 0 2mm; padding-bottom: 1mm; border-bottom: 1.5px solid #efd3dc; break-after: avoid; }
h3 { font-size: 11pt; margin: 4mm 0 1.5mm; }
p { margin: 1.4mm 0 2mm; text-align: justify; }
ul, ol { margin: 1mm 0 2mm 5mm; padding-left: 3mm; }
li { margin: .6mm 0; }
code { font: 8.8pt Consolas, monospace; background: #f8eef2; padding: 0 1mm; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm; font-size: 8.9pt; break-inside: avoid; }
th { background: #7a1e3a; color: #fff; text-align: left; padding: 1.4mm 1.8mm; font-weight: 600; }
td { padding: 1.2mm 1.8mm; border-bottom: 1px solid #eee3e7; vertical-align: top; }
tr:nth-child(even) td { background: #fcf7f9; }
strong { color: #3d0f1f; }
.cover { height: 262mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page;
  background: linear-gradient(140deg, #4a0f22 0%, #7a1e3a 55%, #a8325a 100%); color: #fff; padding: 22mm 18mm; margin: -16mm -15mm 0; }
.cover h1 { color: #fff; font-size: 30pt; margin: 0; letter-spacing: -.5px; }
.cover .sub { font-size: 14pt; opacity: .9; margin-top: 4mm; }
.cover .meta { font-size: 11pt; line-height: 1.8; }
.cover .tag { display: inline-block; padding: 1mm 3mm; border: 1px solid rgba(255,255,255,.5); border-radius: 10px; font-size: 9pt; margin-right: 2mm; }
.figure { border: 1px solid #eee3e7; border-radius: 6px; padding: 3mm; margin: 2mm 0 3mm; break-inside: avoid; text-align: center; }
.figure .cap { font-size: 8.5pt; color: #6e5a63; margin-top: 1.5mm; }
.mermaid svg { max-width: 100%; height: auto; }
"""

DIAGRAM = """
<div class="figure"><pre class="mermaid">
graph LR;
  scout([Scout]) --> intake
  intake -. Send .-> analyst[Job Analyst] & risk[Risk Assessor] & matcher[Fit Matcher]
  analyst --> decide{Bid / skip}
  risk --> decide
  matcher --> decide
  decide -- bid --> pricing[Pricing] --> writer[Writer] --> verifier[Claim verifier] --> critic[Critic]
  critic -. revise, max 2 .-> writer
  critic --> compliance[Compliance] --> approval{{Human approval<br/>interrupt}} --> submit[(Submit once)]
</pre><div class="cap">Figure 1. The bid graph (rendered from the same structure as agent/graphs/bid_graph.py).
Analyst, Risk and Matcher run in parallel; nothing is submitted without the approval interrupt.</div></div>
"""


def build(name: str, roll: str) -> Path:
    md = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    md = re.sub(r"^# .*\n", "", md, count=1)  # title goes on the cover
    body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    body = body.replace("<h2>2. Architecture</h2>", "<h2>2. Architecture</h2>" + DIAGRAM, 1)
    cover = f"""
<section class="cover">
  <div><span class="tag">AI-4016</span><span class="tag">R&amp;D report</span></div>
  <div>
    <h1>GigBid</h1>
    <div class="sub">A multi-agent freelancer copilot: LangGraph agents, advanced RAG,
    MCP tools and a human approval gate. Engineering design review.</div>
  </div>
  <div class="meta">
    <b>{name}</b><br/>{roll}<br/>FAST School of Computing, FAST-NUCES Islamabad<br/>
    Instructor: Muhammad Owais Idrees<br/>{date.today():%d %B %Y}<br/>
    Repository: github.com/AbdullahBinNasir16/Gigbid
  </div>
</section>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>GigBid R&amp;D report</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: "base", themeVariables: {{
  primaryColor: "#f8e9ee", primaryBorderColor: "#7a1e3a", primaryTextColor: "#24141b",
  lineColor: "#7a1e3a", fontSize: "13px" }}}});</script>
</head><body>{cover}{body}</body></html>"""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "GigBid_RD_Report.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Student name")
    ap.add_argument("--roll", default="Roll number")
    a = ap.parse_args()
    html = build(a.name, a.roll)
    pdf = html.with_suffix(".pdf")
    subprocess.run(["node", "scripts/html_to_pdf.mjs", str(html), str(pdf)],
                   cwd=ROOT / "apps" / "web", check=True)
    print(pdf)


if __name__ == "__main__":
    main()
