// Does the viewer typeset the document the builder actually produces?
//
//   node release/test_viewer.mjs <path-to-markdown>
//
// The markdown is supplied by the caller, produced by running the real
// builder. Nothing here contains a sample report: a test with its own copy of
// the document would keep passing while the real one changed, which is the
// failure `scripts/demo.py` describes and this release is built to avoid.
//
// The `typeset` function is extracted from viewer.html rather than duplicated.
// Two copies of a renderer drift, and the copy under test would be the one
// that never ships.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VIEWER = path.join(HERE, "app", "viewer.html");

function loadViewerFunctions() {
  const html = readFileSync(VIEWER, "utf-8");
  const match = html.match(/<script>\n([\s\S]*?)<\/script>/);
  if (!match) throw new Error("no <script> block found in viewer.html");

  // The script ends by wiring up DOM handlers, which do not exist here. Take
  // everything up to the first line that touches `document`, which is exactly
  // the pure part: esc, inline, the row helpers, and typeset.
  const source = match[1];
  const cut = source.indexOf("const doc = document.getElementById");
  if (cut === -1) throw new Error("viewer.html no longer has the expected structure");

  const pure = source.slice(0, cut);
  const factory = new Function(`${pure}\nreturn { typeset, esc, inline };`);
  return factory();
}

const { typeset, inline } = loadViewerFunctions();

const markdownPath = process.argv[2];
if (!markdownPath) {
  console.error("usage: node release/test_viewer.mjs <markdown-file>");
  console.error("  The file must be output from the real builder, not a sample.");
  process.exit(2);
}
const markdown = readFileSync(markdownPath, "utf-8");
if (markdown.trim().length === 0) {
  // An empty input is not a passing test. It is the absence of one.
  console.error("UNDETERMINED: the markdown file is empty; nothing was checked.");
  process.exit(3);
}

let failures = 0;
const check = (name, condition, detail = "") => {
  if (condition) {
    console.log(`  ok    ${name}`);
  } else {
    console.log(`  FAIL  ${name}${detail ? `\n          ${detail}` : ""}`);
    failures++;
  }
};

console.log(`viewer, against ${markdown.length} characters of real report\n`);

const { html, unhandled } = typeset(markdown);

// The assertion this file exists for. A renderer that silently drops a line
// makes a disclosure document look complete while omitting the disclosure.
check(
  "every line of the real report is typeset",
  unhandled.length === 0,
  unhandled.length ? `${unhandled.length} unhandled: ${JSON.stringify(unhandled.slice(0, 3))}` : ""
);

check("the title becomes a heading", html.includes("<h1>"));
check("sections become headings", html.includes("<h2>"));
check("the parameter table becomes a table", html.includes("<table>") && html.includes("<th>"));
check("bold survives", html.includes("<strong>"));
check(
  "the provenance section is present",
  html.includes("What Terrium would not do"),
  "the report's refusal disclosure did not reach the rendered output"
);
check("the BRENDA reference reaches the output", html.includes("BRENDA"));

// Every table row in the source should reach the output. A renderer that
// dropped the second half of a table would still look plausible.
const sourceRows = markdown.split("\n").filter(l => {
  const t = l.trim();
  // Mirrors the viewer's own divider test, which requires a dash: `| | |`
  // is an empty header ROW in the real report, not a divider.
  return t.startsWith("|") && t.endsWith("|") && !/^\|[\s:|-]*-[\s:|-]*\|$/.test(t);
}).length;
const renderedRows = (html.match(/<tr>/g) || []).length;
check(
  `all ${sourceRows} table rows reach the output`,
  renderedRows === sourceRows,
  `source ${sourceRows}, rendered ${renderedRows}`
);

// Escaping. The report carries database text and a user-written question;
// none of it is markup.
check(
  "angle brackets are escaped, not interpreted",
  inline("<img src=x onerror=alert(1)>").includes("&lt;img"),
  inline("<img src=x onerror=alert(1)>")
);
check(
  "quotes are escaped",
  inline(`a "quoted" value`).includes("&quot;")
);

// And the negative case: prove the unhandled detector can fire, so a green
// run means something. A check that cannot fail is worse than no check.
const sabotaged = typeset("> a blockquote, which this viewer does not support");
check(
  "an unsupported construct is reported rather than dropped",
  sabotaged.unhandled.length === 0 ? false : true,
  sabotaged.unhandled.length === 0
    ? "a blockquote vanished silently -- the detector does not work"
    : ""
);

console.log(
  failures === 0
    ? "\nviewer OK"
    : `\nviewer FAILED: ${failures} check(s)`
);
process.exit(failures === 0 ? 0 : 1);
