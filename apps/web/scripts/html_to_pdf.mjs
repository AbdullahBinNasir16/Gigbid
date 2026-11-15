// Print an HTML file to an A4 PDF with headless Chromium (used by scripts/build_report.py).
import { chromium } from "@playwright/test";
import { pathToFileURL } from "node:url";

const [, , src, out] = process.argv;
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(src).href, { waitUntil: "networkidle" });
await page.waitForFunction(() => !document.querySelector("pre.mermaid:not([data-processed])"), null, { timeout: 15000 }).catch(() => {});
await page.pdf({ path: out, format: "A4", printBackground: true, preferCSSPageSize: true,
  displayHeaderFooter: true, headerTemplate: "<span></span>",
  footerTemplate: '<div style="font-size:9px;width:100%;text-align:center;color:#000;font-family:Garamond,serif"><span class="pageNumber"></span></div>' });
await browser.close();
