# Caterva: Smart Science

An assistant in Caterva Studio, built so that the guardrails are the product. Caterva's claim is that every
number says whether it was cited, fitted, computed, chosen or a placeholder, and that it refuses rather than
guesses. An assistant that could put an unverified number in front of a scientist would end that claim. So the
assistant is built the other way round: it is allowed to help, and the engine checks everything it says.

This document is the design. The code is `caterva/assistant/`; the routes are in `CONTRACT.md` ("Assistant" and
22.9 to 22.10); the page is `src/components/assistant/` and the Assistant section of Settings.

## 1. The rule: the assistant proposes, the engine disposes

The model never authors a scientific value that reaches a result. It may:

- **interpret** free text into a structured intent that is validated against the engine's own shapes and
  grammar, and shown to the person as a proposal they must confirm (Compose "describe it");
- **choose** among candidates deterministic code already produced (the enzyme finder's candidates, the ranked
  next measurements), never invent one: an EC number the finder did not list is rejected;
- **explain, summarise or draft** text from a run's own structured result.

It may never: run anything without a person's click, set or alter a constant, produce a citation, claim a
verdict, give clinical, dosing or safety advice (it refuses and says what it cannot do), or answer from its own
knowledge about values ("what is the Km of X" is refused with a pointer to Constants, the cited lookup).

## 2. A sixth mark: `ai`

`ai` means "suggested by an assistant, not a measurement". It is not an engine kind (the engine's five are
untouched; no adapter emits `ai`). It has its own shape (an open hexagon with a centre dot, in the muted ink),
its own name in the legend, and its own colour token (`--prov-ai`). Text with this mark is always visibly
marked, always beside the engine's own text, and never styled like a verdict. A number never wears it, because
an assistant never authors one. Once a person confirms a proposal, the values it set are `chosen` by that
person, and the record names the assistant as the source of the suggestion (`suggested_by`).

## 3. The grounding check (the heart)

Every explanation, summary or draft is verified after generation by `caterva/assistant/grounding.py`, a pure
module with no model, network or I/O. It extracts the checkable claims and requires each to be traceable to the
digest of the result the text was written from (the digest is also exactly what was sent):

| claim | rule |
|---|---|
| a number (digits, `1.4e-3`, `1.4 x 10^-3`, `1,234`, `30%`, ranges, number words such as "forty") | equals a number in the source rounded to the precision the text shows (0.0432 is grounded by 0.043 and 0.04, not by 0.05); an integer is compared at all its digits |
| a unit | the number must be in the source with that unit; spellings of one unit are one unit; a rewritten unit (0.03 mM as 30 uM) is refused, and named as a unit change |
| an EC number, a citation id (BRENDA ref, PMID, DOI, PDB, UniProt), "et al." | must be in the source |
| a link | must be in the source; markup and images are refused outright |
| a name (a capitalised word, an organism abbreviation, an -ase word) | must be in the source or the small plain-word list (`plainwords.py`) |
| a comparison ("higher than", "exceeds") | two grounded figures of one unit in the stated order, or the source itself makes the comparison |
| "significant" | the source must hold a statistical test; "one significant figure" is not one |
| verdict words, clinical or safety words | must be in the source |
| a quantity worked out in words ("twice", "half", "a third") | refused: the result never said it |
| a key-shaped string, an echo of the assistant's own instructions | refused |

Structure is not data and does not false-positive: "step 2", "Figure 1", "tier 3", list numbers, "2nd", HK2,
1I10, the pronoun "one". Text from outside the engine (a BRENDA row's commentary, a paper title, a file name,
the person's own input) is untrusted: it can supply a name to be quoted, but it can never ground a figure, an
identifier, a link, a verdict word or evidence of a test, so planted text cannot vouch for itself.

When the check fails the text is NOT shown. The page shows the engine's own text and says: "The assistant's
wording was rejected because it contained a figure that is not in your results", with a disclosure of the
rejected text and which tokens failed.

**Limits, stated.** A lowercase noun that is not enzyme-shaped (a compound) is not detected as a name. The right
figure attributed to the wrong quantity passes ("the Ki is 0.03 mM" when 0.03 mM is the Km). Small integers
appear all over a result, so a wrong small count can be grounded by an unrelated 2 or 3. A sentence can be true
of every token and still mislead. These are why AI text is labelled and shown beside the engine's text, never
instead of a verdict.

## 4. Untrusted input

BRENDA commentary, paper titles, PDB headers, CSV cells, file names and the person's own text are data. They go
into one JSON document inside `<caterva_data>` tags: `json.dumps` keeps a string in its quotes, `<`, `>` and `&`
are written as escapes so a value cannot close the tag, and the system prompt says nothing inside is addressed to
the model. The model has no tools: the request carries no tool or function definitions and only text is read from
the reply. The reply is parsed against a strict schema (exact keys, types, length limits, no duplicate keys, one
JSON object); anything else is discarded. The server, not the model, performs every action, after a click.
`test_assistant_injection.py` runs a corpus of planted text and of replies from a model that obeyed it.

## 5. Privacy and consent

Off by default. Three switches must be on: the assistant, the feature, and (once per feature) the person's
agreement to what that feature sends. Before every send the page can show "Show exactly what will be sent": the
real payload after redaction. For the first use of each feature it is shown before the send button works; the
server refuses a send without consent, and refuses a payload whose hash the page did not echo, so what was shown is
what is sent, byte for byte. A persistent indicator reads "Assistant active: sends to api.anthropic.com" whenever
data can leave. Redaction removes file paths, the home folder, the user name, e-mail addresses and key shapes. The
person's own input to the run is withheld unless they tick "include my data" for that call. Every call is logged
(`assistant/calls.jsonl`). A local provider (an OpenAI-compatible server on a loopback address, such as Ollama)
sends nothing off the machine, and the page says so. Offline mode blocks every provider but a local one.

Providers: Anthropic's Messages API and OpenAI-compatible chat completions (OpenAI, Groq, OpenRouter, Mistral,
local). Plain `httpx` over the bundled certificate store, a timeout, retry with backoff, no streaming. The model
name is a setting with an editable list; the only default is `claude-sonnet-5-5`, and other providers start empty
rather than guess an id that may be retired. A spend guard (requests per hour, tokens per call) is a hard stop.

## 6. The key

Never in the repository, a `.env`, the data folder, a run record, a bundle, a log, the page, an argument vector or
an error message. On macOS the shell keeps it in the login Keychain (service `org.caterva.assistant`, per provider)
and writes it to the server's stdin as one JSON line at launch and when it changes; the server keeps it in memory.
Settings has no route that accepts a key (a field hands it to the shell once and clears itself). In a browser or
development run the key may come from `CATERVA_ASSISTANT_KEY` only, and Settings says so. Every error and log line
is scrubbed of key shapes and of the exact key held.

## 7. Audit and reproducibility

Every call is recorded in the run (`runs/<id>/assistant.jsonl`): provider, model, feature, the exact payload
sent, the response, the grounding result, accepted or rejected, a timestamp, and the person's confirmation. The
record is in the bundle with `assistant-methods.txt`, deterministic sentences for a methods section ("An assistant
(model, provider) suggested X; the person confirmed it", "AI-generated text was checked against the results").
History marks runs that used the assistant.

## 8. Everything works without it

With no key, offline or switched off, every screen behaves as before and the assistant's affordances are one calm
line ("Assistant off") or absent. A test proves that no assistant code path builds a payload or creates a transport
while it is off, and that no socket is used.

## 9. Where it is embedded

Built, each behind its own switch, each following the above, each with a deterministic fallback:

- **A. Describe it** (Compose): when the grammar refuses, "Ask the assistant to interpret" proposes a shape (one of
  the 36), a step count or a named variant where the engine would refuse to choose, and names the person's own words
  contain. The description sent to the engine is built from the shape's own line, never from the model's text, and
  the person is shown the engine's reading before they confirm. The enzyme finder's candidates are the only ECs
  allowed.
- **B. Explain this result** (Compose, Constants, Bind, Analyze, Rates when present): the verdict, the worst thing
  wrong, what to do next, terms defined once, beside the deterministic text, marked `ai`.
- **C. Draft my methods**: a polish of the engine's own methods text, editable, with a copy button; the engine's
  text stays the default.
- **D. Ask this run**: questions about this result only, answered from its digest, refusing clinical, value-from-
  memory and action requests before anything is sent; no history beyond the run.
- **E. What should I measure next**: the engine's ranked measurements in plain words; the model may only order
  keys the engine ranked.

**On a Rates run** (B, C and D work; E does not apply). The server reads the run's own `result.json`; its digest
(`caterva/assistant/digest.py`, `rates_view`) keeps the findings only: every constant with its estimate, interval,
unit and provenance, the lack-of-fit and group tests, the rate laws compared by AICc, the cautions and "what to
change" lines, the verdict lines, the error model, the engine's methods paragraph and the BRENDA rows or the reason
none was made. It leaves out the drawn figure points, the duplicate copy of the analysis and, unless "include my
data" is ticked, the reading of the person's file (its decisions and problems quote its comments, headers and
cells). The group labels and the file name still reach the assistant, because the verdict and the engine's methods
paragraph name them. A constant the data bound on one side is stated by the engine with ">" ("Vmax > 55.7"), and
the grounding check refuses "greater than" for it (a comparison the result does not state), so the system prompt
asks for "at least" and "at most". Tested on the real Rates fixtures in `caterva/tests/test_assistant_rates.py` and
`src/__tests__/assistant-rates.test.tsx`. D's fallback (nearest facts) and B's fallback (the engine's own report)
read the same result.

Designed, not built, for Rates: "What should I measure next". Rates ranks nothing: its "what to change" lines are
the engine's prose, with concentrations it computed, not a ranked list with keys. E needs ranked keys the model
may only order; narrating prose would let it reword computed concentrations. It would need Rates to emit the
suggestions as keyed, ranked items (a design section like Compose's) first. The button is not shown for a Rates
run and the server answers 409 with that reason.

Designed, not built: a plain-language gloss on each concern in the verdict; "why was this row excluded" for Bind;
translating a CSV's column headings into column roles for Analyze (the schema is the intent validator's, the
mapping shown for confirmation); a reading-list summary of a result's cited papers from their titles only; a
"what changed between these two runs" narration of two real results; a hint for a refused Constants lookup that
chooses among the finder's suggestions; a first-run tour written from the legend.

## 10. Guardrails not enforced

- A key typed into Settings crosses the page's JavaScript once on its way to the shell. A hostile page script could
  read it. The shell's own prompt would close that; it is not built.
- In a browser run the key is an environment variable the whole process can read.
- The consent screen is only as honest as the person reading it; a payload can be large and the preview long.
- The grounding limits in section 3.
- A real model's resistance to injection is not claimed; the studio does not depend on it.
