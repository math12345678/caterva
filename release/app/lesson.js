"use strict";
/**
 * Turn the report into a question, before it becomes an answer.
 *
 * WHY THIS EXISTS
 * ---------------
 * The report already contains the lesson. It says:
 *
 *     The evidence ranked 2 values of km equal: 0.03 to 0.398. Running the
 *     model at each ... the substrate remaining at t=10 ranges from 7.509 to
 *     7.609. A factor of 1.01.
 *
 * A thirteen-fold disagreement in a textbook constant, producing a one per
 * cent difference in the answer. Most courses teach students to code the
 * equation; almost none teach that Km has a 13x range in the literature, or
 * that the size of that range tells you very little on its own about whether
 * it matters.
 *
 * The report states all of this. It states it as a lecture. A teacher would
 * ask first -- and the asking is the only part missing, because Terrium has
 * already done the work of computing both runs.
 *
 * WHAT THIS DOES NOT DO
 * ---------------------
 * It invents no numbers. Every figure in the question and the reveal is read
 * out of the document the builder produced; the mechanism sentence is
 * derived from those figures, not written about this enzyme in advance. If
 * the report has no disagreement section -- because the literature reported
 * one value, or none -- there is no lesson and this says so rather than
 * manufacturing one.
 *
 * That refusal matters more than it looks. A teaching tool that always has a
 * lesson ready will invent one, and a fabricated lesson about provenance
 * would be a worse failure than no lesson at all.
 */

/** Numbers as the report writes them: `0.03`, `7.60877`, `1.01`. */
const NUM = "([0-9]+(?:\\.[0-9]+)?)";

/**
 * The two-column table under "The literature disagrees about ...".
 * Returns [{value, result}] in the order the report lists them.
 */
function disagreementRows(markdown) {
  const start = markdown.search(/^##\s+The literature disagrees about\s+(\S+)/m);
  if (start === -1) return [];
  // [1], not [0]: the slice starts AT the heading, so the split
  // produces an empty string before it.
  const section = markdown.slice(start).split(/^##\s/m)[1] || "";
  const rows = [];
  for (const line of section.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|") || !t.endsWith("|")) continue;
    const cells = t.slice(1, -1).split("|").map((c) => c.trim());
    if (cells.length !== 2) continue;
    const v = cells[0].match(new RegExp("^" + NUM));
    const r = cells[1].match(new RegExp("^" + NUM + "$"));
    if (v && r) rows.push({ value: Number(v[1]), result: Number(r[1]), label: cells[0] });
  }
  return rows;
}

/** Which quantity the section is about -- `km`, `ki`, `kcat`. */
function disagreementQuantity(markdown) {
  const m = markdown.match(/^##\s+The literature disagrees about\s+(\S+)/m);
  return m ? m[1] : null;
}

/**
 * A value from the Parameters table, e.g. s0.
 *
 * Read from the report rather than from the payload the app sent, so the
 * lesson describes the run that actually happened.
 */
function parameterValue(markdown, name) {
  const start = markdown.search(/^##\s+Parameters/m);
  if (start === -1) return null;
  const section = markdown.slice(start).split(/^##\s/m)[1] || "";
  for (const line of section.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    const cells = t.slice(1, -1).split("|").map((c) => c.trim());
    if (cells.length >= 2 && cells[0].toLowerCase() === name.toLowerCase()) {
      const m = cells[1].match(new RegExp("^" + NUM));
      if (m) return { value: Number(m[1]), text: cells[1] };
    }
  }
  return null;
}

const ratio = (a, b) => (Math.max(a, b) / Math.min(a, b));

/**
 * The rate law the run used, as the report states it -- or null.
 *
 * WHY THIS IS READ AND NOT ASSUMED
 * --------------------------------
 * The mechanism sentence below explains a result in terms of
 * `v = Vmax*S/(Km+S)`. That was true of the one report this was written
 * against, and asserted about every report: nothing in the document said
 * the run used Michaelis-Menten, and it is only reached when there is a
 * `km` and an `s0`. A future domain with a `km` and a different rate law
 * -- Hill kinetics, ping-pong, competitive inhibition -- would have been
 * handed a confident explanation that did not apply to it.
 *
 * A wrong explanation is worse here than no explanation, because the whole
 * point of this layer is to teach someone where a claim comes from.
 */
function rateLaw(markdown) {
  const start = markdown.search(/^##\s+How this document was produced/m);
  if (start === -1) return null;
  const section = markdown.slice(start).split(/^##\s/m)[1] || "";
  for (const line of section.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    const cells = t.slice(1, -1).split("|").map((c) => c.trim());
    if (cells.length >= 2 && cells[0].toLowerCase() === "rate law") {
      return cells[1] || null;
    }
  }
  return null;
}

/** Michaelis-Menten, as opposed to merely having a Km. */
function isMichaelisMenten(law) {
  return law !== null && /michaelis[\s-]*menten/i.test(law);
}

/**
 * Build the lesson, or say why there is none.
 *
 * Shape: {ok: true, ...lesson} | {ok: false, reason}
 */
function lessonFrom(markdown) {
  const quantity = disagreementQuantity(markdown);
  if (!quantity) {
    return {
      ok: false,
      reason:
        "This report has no disagreement section, so there is nothing to " +
        "predict. That happens when the literature reported a single value " +
        "for the parameter -- which is a fact about the evidence, not a gap " +
        "in the lesson.",
    };
  }

  const rows = disagreementRows(markdown);
  if (rows.length < 2) {
    return {
      ok: false,
      reason:
        `The report names a disagreement about ${quantity} but lists fewer ` +
        "than two values with results, so there is no comparison to make.",
    };
  }

  const values = rows.map((r) => r.value);
  const results = rows.map((r) => r.result);
  const paramSpread = ratio(Math.min(...values), Math.max(...values));
  const outcomeSpread = ratio(Math.min(...results), Math.max(...results));

  // The choices are generated from the actual parameter spread, so the
  // right answer is not always in the same position and "the small one" is
  // not always correct. A quiz whose answer can be guessed from the shape
  // of the options teaches the shape, not the science.
  const choices = [
    { id: "same", label: "Almost identical", lo: 1, hi: 1.2 },
    { id: "small", label: "Noticeably different, under 2x", lo: 1.2, hi: 2 },
    { id: "large", label: "Several times different", lo: 2, hi: paramSpread * 0.6 },
    { id: "proportional", label: `About ${paramSpread.toFixed(0)}x, like the inputs`,
      lo: paramSpread * 0.6, hi: Infinity },
  ];
  const correct = choices.find((c) => outcomeSpread >= c.lo && outcomeSpread < c.hi)
                  || choices[choices.length - 1];

  const s0 = parameterValue(markdown, "s0");
  const law = rateLaw(markdown);
  const mm = isMichaelisMenten(law);
  let mechanism;
  if (!mm) {
    // The saturation argument is a fact about ONE rate law. Without the
    // document saying which was used, the outcome is still reported --
    // it was measured -- and the reason is not, because the reason would
    // be invented.
    mechanism = law
      ? `This run used ${law}, not Michaelis-Menten, so the saturation ` +
        `argument that would explain a spread this size does not apply. ` +
        `The result above is what the model produced; the reason for it is ` +
        `not derivable from this document.`
      : `This report does not state which rate law produced these numbers, ` +
        `so why the disagreement lands where it does is not derivable from ` +
        `it. The spread itself is measured and stands.`;
  } else if (s0 && Math.max(...values) < s0.value) {
    // Derived from the numbers in front of us, not asserted about this
    // enzyme in advance: Michaelis-Menten is v = Vmax*S/(Km+S), so when
    // every candidate Km sits well below S the enzyme is near saturation
    // either way and the rate is set by Vmax, not by Km.
    const worst = Math.max(...values);
    const sat = (s0.value / (s0.value + worst)) * 100;
    mechanism =
      `Both published values sit below the substrate concentration you ` +
      `chose (s0 = ${s0.text}). In v = Vmax·S/(Km+S), that puts the enzyme ` +
      `near saturation for either one -- at the larger Km it still runs at ` +
      `${sat.toFixed(1)}% of Vmax -- so the rate is set by Vmax, and Km ` +
      `barely gets a say. The disagreement is real and it lands somewhere ` +
      `this run cannot see it.`;
  } else if (s0) {
    mechanism =
      `At least one published value is comparable to or larger than the ` +
      `substrate concentration you chose (s0 = ${s0.text}), so the enzyme ` +
      `is not saturated and Km is doing real work in v = Vmax·S/(Km+S). ` +
      `That is why the disagreement reaches the answer here.`;
  } else {
    // No s0 in the report: state the outcome without explaining it, rather
    // than reaching for a mechanism the document does not support.
    mechanism =
      "The report does not state the substrate concentration this run used, " +
      "so the reason for this spread is not derivable from it here.";
  }

  return {
    ok: true,
    quantity,
    values,
    results,
    paramSpread,
    outcomeSpread,
    question:
      `The literature reports ${values.length} values for ${quantity}, and ` +
      `they differ by a factor of ${paramSpread.toFixed(1)} ` +
      `(${Math.min(...values)} to ${Math.max(...values)}). ` +
      `Before you look: how different will the two runs' answers be?`,
    choices: choices.map(({ id, label }) => ({ id, label })),
    correctId: correct.id,
    reveal:
      `A factor of ${outcomeSpread.toFixed(2)}. The ${quantity} values differ ` +
      `by ${paramSpread.toFixed(1)}x; the results differ by ` +
      `${outcomeSpread.toFixed(2)}x.`,
    mechanism,
    caution:
      "This is the spread of published measurements, not an uncertainty " +
      "estimate. It is bounded by which papers happen to be in the database, " +
      "not by any statement about the true value -- so a narrow spread here " +
      "is not evidence that the parameter is well known.",
  };
}

if (typeof module !== "undefined") module.exports = { lessonFrom, disagreementRows, parameterValue };
