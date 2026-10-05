"""Questions the assistant refuses before any model is asked: deterministic, offline, no send.

"Ask this run" answers questions about THIS result. Three kinds of question
are refused here, in plain words, and nothing is sent anywhere:

  * clinical, dosing or safety questions: Caterva's results are about enzyme
    kinetics in a model and say nothing about people;
  * questions about values from the assistant's own knowledge ("what is the Km
    of lactate dehydrogenase?"): a value comes with a source or not at all, so
    the answer is the cited lookup (Constants), never a model's memory;
  * requests to DO something (run, change, set, delete): the assistant has no
    hands; the screen's own controls do things, on a click.

The screen is a first filter. The model may still decline (`answerable:
false`), and the grounding check still applies to whatever it says.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

MAX_QUESTION = 400


@dataclass(frozen=True)
class Refusal:
    code: str
    message: str


_CLINICAL = re.compile(
    r"\b(dose|doses|dosage|dosing|overdose|patient|patients|clinical|clinic|therapy|therapeutic|prescri\w+|"
    r"treat|treatment|cure|diagnos\w+|medicine|medication|toxic\w*|safe|safety|side effects?|pregnan\w+|"
    r"should i take|can i take|is it dangerous|poison\w*)\b", re.I)
_VALUE_NAMES = r"(?:km|kcat|ki|kd|vmax|ic50|ec50|k_?cat|k_?m|turnover(?: number)?|rate constant|michaelis constant|" \
               r"binding energy|delta ?g)"
_KNOWLEDGE = re.compile(
    rf"\b(?:what(?:'s| is| are| was)|tell me|give me|find|look up|know)\b[^?.]{{0,40}}\b{_VALUE_NAMES}\b"
    r"[^?.]{0,20}\b(?:of|for|in)\b", re.I)
_ANAPHORA = re.compile(r"\b(this|these|here|above|my|our|the run|the result|shown|reported|displayed|in the verdict|"
                       r"this run|that run|the placeholder|the table|the row|the citation)\b", re.I)
_ACTION = re.compile(r"^\s*(?:please\s+)?(?:run|start|launch|execute|delete|remove|erase|change|set|update|edit|"
                     r"overwrite|replace|install|download|email|send|post|publish|submit|save|rerun|re-run)\b", re.I)


def screen_question(question: str) -> Optional[Refusal]:
    q = (question or "").strip()
    if not q:
        return Refusal("empty", "Type a question about this run first.")
    if len(q) > MAX_QUESTION:
        return Refusal("too_long", f"Keep the question under {MAX_QUESTION} characters.")
    if _CLINICAL.search(q):
        return Refusal("clinical", "I can't give clinical, dosing or safety advice. Caterva's results describe "
                                   "enzyme kinetics in a model; they say nothing about people or what is safe.")
    if _ACTION.search(q):
        return Refusal("action", "I can't run or change anything. Use the screen's own buttons; nothing happens "
                                 "until you click them.")
    if _KNOWLEDGE.search(q) and not _ANAPHORA.search(q):
        return Refusal("knowledge", "I can only answer about this run, and I don't give values from memory. For a "
                                    "value with its source, use Constants: it looks the value up and cites it.")
    return None


__all__ = ["MAX_QUESTION", "Refusal", "screen_question"]
