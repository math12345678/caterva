// The lesson layer: does it read the report, and does it refuse?
//
//   node release/test_lesson.mjs <path-to-markdown>
//
// The markdown comes from the real builder, supplied by the caller. Nothing
// here contains a sample report -- a test carrying its own copy would keep
// passing while the real document changed, which is the failure
// `scripts/demo.py` describes.
//
// Two things are worth testing about a teaching layer, and only one of them
// is "does it produce a lesson":
//
//   1. Every number it shows is read out of the document, not invented.
//   2. When the document cannot support a lesson, it says so instead of
//      manufacturing one. A teaching tool that always has something ready
//      will eventually make something up, and a fabricated lesson about
//      provenance would be worse than no lesson at all.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { lessonFrom } = require(path.join(HERE, "app", "lesson.js"));

const markdownPath = process.argv[2];
if (!markdownPath) {
  console.error("usage: node release/test_lesson.mjs <markdown-file>");
  console.error("  Must be real builder output, not a sample.");
  process.exit(2);
}
const markdown = readFileSync(markdownPath, "utf-8");
if (markdown.trim().length === 0) {
  console.error("UNDETERMINED: the markdown file is empty; nothing was checked.");
  process.exit(3);
}

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(ok ? `  ok    ${name}` : `  FAIL  ${name}${detail ? `\n          ${detail}` : ""}`);
  if (!ok) failures++;
};

console.log(`lesson layer, against ${markdown.length} characters of real report\n`);

const lesson = lessonFrom(markdown);
check("a lesson is produced from the real report", lesson.ok === true,
      lesson.ok ? "" : lesson.reason);

if (lesson.ok) {
  // Every figure it quotes must appear in the source document.
  for (const v of lesson.values) {
    check(`the parameter value ${v} is in the report`, markdown.includes(String(v)));
  }
  for (const r of lesson.results) {
    check(`the result ${r} is in the report`, markdown.includes(String(r)));
  }

  check("the question states the parameter spread",
        /factor of \d/.test(lesson.question), lesson.question);
  check("exactly one choice is marked correct",
        lesson.choices.filter((c) => c.id === lesson.correctId).length === 1);

  // The point of the whole exercise: the answer must be derived, not fixed.
  // If `correctId` were hardcoded, this would still pass -- so the sabotage
  // below is what makes it mean something.
  check("the reveal states the outcome spread",
        lesson.reveal.includes(lesson.outcomeSpread.toFixed(2)));

  check("the caution about uncertainty survives",
        /not an uncertainty estimate/i.test(lesson.caution));
}

// --- refusal -----------------------------------------------------------
// A report with no disagreement section must produce no lesson.
const noSection = markdown.replace(/^## The literature disagrees about.*$/m,
                                   "## Something else entirely");
const refused = lessonFrom(noSection);
check("no disagreement section -> refuses, with a reason",
      refused.ok === false && /single value|nothing to predict/i.test(refused.reason),
      refused.ok ? "it produced a lesson anyway" : refused.reason);

// A section with only one row is not a comparison.
const oneRow = markdown.replace(/^\| 0?\.?\d[^\n]*\|$/m, "");
const single = lessonFrom(oneRow);
check("fewer than two values -> refuses rather than comparing one thing",
      single.ok === false || single.values.length >= 2,
      single.ok ? `it compared ${single.values.length} value(s)` : single.reason);

// --- the answer is computed, not stored --------------------------------
// Swap the results so the outcome spread becomes large. If `correctId` is
// derived, it must move; if it were hardcoded, this test fails and says so.
const widened = markdown
  .replace("| 0.03 (returned) | 7.5086 |", "| 0.03 (returned) | 1.0 |")
  .replace("| 0.398 | 7.60877 |", "| 0.398 | 90.0 |");
const moved = lessonFrom(widened);
if (moved.ok && widened !== markdown) {
  check("a bigger outcome spread moves the correct answer",
        moved.correctId !== lesson.correctId,
        `both answered ${moved.correctId}; the answer may be hardcoded`);
} else {
  console.log("  --    outcome-spread sabotage did not apply to this report");
}

// --- the mechanism is derived from s0, not asserted ---------------------
if (lesson.ok) {
  const bigKm = markdown.replace("| 0.398 | 7.60877 |", "| 900.0 | 7.60877 |");
  const other = lessonFrom(bigKm);
  if (other.ok && bigKm !== markdown) {
    check("a Km above s0 changes the explanation",
          other.mechanism !== lesson.mechanism,
          "the same mechanism sentence was produced for both");
  }
}

console.log(failures === 0 ? "\nlesson OK" : `\nlesson FAILED: ${failures} check(s)`);
process.exit(failures === 0 ? 0 : 1);
