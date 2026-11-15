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
@page { size: A4; margin: 20mm 20mm 20mm 20mm; }
* { box-sizing: border-box; }
body { font: 11.5pt/1.4 "EB Garamond", Garamond, "Times New Roman", serif; color: #000; margin: 0; }
h1 { font-size: 18pt; font-weight: 600; margin: 0 0 4mm; }
h2 { font-size: 13.5pt; font-weight: 600; margin: 6mm 0 2mm; break-after: avoid; }
h3 { font-size: 12pt; font-weight: 600; margin: 4mm 0 1.5mm; }
p { margin: 1.4mm 0 2mm; text-align: justify; }
ul, ol { margin: 1mm 0 2mm 5mm; padding-left: 3mm; }
li { margin: .5mm 0; }
code { font: 9.5pt Consolas, "Courier New", monospace; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm; font-size: 10pt; break-inside: avoid; }
th, td { border: 0.6pt solid #000; padding: 1.2mm 1.8mm; text-align: left; vertical-align: top; }
th { font-weight: 600; }
strong { font-weight: 600; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; text-align: center; break-after: page; }
.cover h1 { font-size: 26pt; margin: 0 0 4mm; }
.cover .sub { font-size: 14pt; margin-bottom: 18mm; }
.cover .meta { font-size: 13pt; line-height: 1.7; }
.figure { margin: 2mm 0 3mm; break-inside: avoid; text-align: center; }
.figure .cap { font-size: 10pt; margin-top: 1.5mm; }
"""

DIAGRAM = """
<div class="figure"><svg viewBox="0 0 880 158" width="100%" font-family="EB Garamond, Garamond, serif" font-size="12"><defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#000"/></marker></defs><line x1="58" y1="76" x2="78" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="132" y1="76" x2="160" y2="28" stroke="#000" marker-end="url(#a)" stroke-dasharray="3 2"/><line x1="132" y1="76" x2="160" y2="76" stroke="#000" marker-end="url(#a)" stroke-dasharray="3 2"/><line x1="132" y1="76" x2="160" y2="124" stroke="#000" marker-end="url(#a)" stroke-dasharray="3 2"/><line x1="248" y1="28" x2="286" y2="66" stroke="#000" marker-end="url(#a)" /><line x1="248" y1="76" x2="270" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="248" y1="124" x2="286" y2="86" stroke="#000" marker-end="url(#a)" /><line x1="340" y1="76" x2="360" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="418" y1="76" x2="430" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="488" y1="76" x2="500" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="570" y1="76" x2="590" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="640" y1="76" x2="650" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="722" y1="76" x2="730" y2="76" stroke="#000" marker-end="url(#a)" /><line x1="796" y1="76" x2="810" y2="76" stroke="#000" marker-end="url(#a)" /><rect x="4" y="62" width="54" height="28" rx="14" fill="#fff" stroke="#000"/><text x="31.0" y="80" text-anchor="middle">Scout</text><rect x="78" y="62" width="54" height="28" rx="2" fill="#fff" stroke="#000"/><text x="105.0" y="80" text-anchor="middle">Intake</text><rect x="160" y="14" width="88" height="28" rx="2" fill="#fff" stroke="#000"/><text x="204.0" y="32" text-anchor="middle">Job Analyst</text><rect x="160" y="62" width="88" height="28" rx="2" fill="#fff" stroke="#000"/><text x="204.0" y="80" text-anchor="middle">Risk Assessor</text><rect x="160" y="110" width="88" height="28" rx="2" fill="#fff" stroke="#000"/><text x="204.0" y="128" text-anchor="middle">Fit Matcher</text><polygon points="305.0,54 340,76 305.0,98 270,76" fill="#fff" stroke="#000"/><text x="305.0" y="80" text-anchor="middle">Bid/skip</text><rect x="360" y="62" width="58" height="28" rx="2" fill="#fff" stroke="#000"/><text x="389.0" y="80" text-anchor="middle">Pricing</text><rect x="430" y="62" width="58" height="28" rx="2" fill="#fff" stroke="#000"/><text x="459.0" y="80" text-anchor="middle">Writer</text><rect x="500" y="62" width="70" height="28" rx="2" fill="#fff" stroke="#000"/><text x="535.0" y="80" text-anchor="middle">Verifier</text><rect x="590" y="62" width="50" height="28" rx="2" fill="#fff" stroke="#000"/><text x="615.0" y="80" text-anchor="middle">Critic</text><rect x="650" y="62" width="72" height="28" rx="2" fill="#fff" stroke="#000"/><text x="686.0" y="80" text-anchor="middle">Compliance</text><rect x="730" y="62" width="66" height="28" rx="2" fill="#fff" stroke="#000"/><text x="763.0" y="80" text-anchor="middle">Approval</text><rect x="810" y="62" width="62" height="28" rx="14" fill="#fff" stroke="#000"/><text x="841.0" y="80" text-anchor="middle">Submit</text><path d="M615 90 C615 118, 459 118, 459 92" fill="none" stroke="#000" stroke-dasharray="3 2" marker-end="url(#a)"/><text x="537" y="126" text-anchor="middle" font-size="10">revise, at most 2</text><text x="146" y="150" text-anchor="middle" font-size="10">parallel (Send)</text><text x="763" y="108" text-anchor="middle" font-size="10">interrupt()</text></svg><div class="cap">Figure 1. The bid graph (agent/graphs/bid_graph.py). Job Analyst, Risk Assessor and Fit Matcher run in parallel; nothing is submitted without the human approval interrupt.</div></div>
"""


def build(name: str, roll: str, section: str) -> Path:
    md = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    md = re.sub(r"^# .*\n", "", md, count=1)  # title goes on the cover
    body = markdown.markdown(md, extensions=["tables", "sane_lists"])
    body = body.replace("<h2>2. Architecture</h2>", "<h2>2. Architecture</h2>" + DIAGRAM, 1)
    cover = f"""
<section class="cover">
  <h1>GigBid: A Multi-Agent Freelancer Copilot</h1>
  <div class="sub">R&amp;D Report, AI-4016</div>
  <div class="meta">
    {name}<br/>{roll} · {section}<br/><br/>
    FAST School of Computing, FAST-NUCES Islamabad<br/>
    Instructor: Muhammad Owais Idrees<br/>{date.today():%d %B %Y}<br/><br/>
    github.com/AbdullahBinNasir16/Gigbid
  </div>
</section>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>GigBid R&amp;D report</title>
<style>{CSS}</style>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;600&display=swap" rel="stylesheet">
</head><body>{cover}{body}</body></html>"""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "GigBid_RD_Report.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Abdullah Bin Nasir")
    ap.add_argument("--roll", default="23-0803")
    ap.add_argument("--section", default="CS-A")
    a = ap.parse_args()
    html = build(a.name, a.roll, a.section)
    pdf = html.with_suffix(".pdf")
    subprocess.run(["node", "scripts/html_to_pdf.mjs", str(html), str(pdf)],
                   cwd=ROOT / "apps" / "web", check=True)
    print(pdf)


if __name__ == "__main__":
    main()
