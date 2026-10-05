"""The result digest: the part of a run's result the assistant sees, and the only source its wording is checked against.

A compose result is 200 KB: trajectories, sweeps, charts. A model does not
need them and a person does not want them sent. `digest` keeps a bounded,
structured subset of the result JSON (never a rewritten one): every number in
it is a number in the result, with its unit and its provenance beside it, so a
sentence grounded against the digest is grounded against the result.

Two sections are separated on purpose:

  `result`     what the engine produced. Always part of an assistant payload
               for a feature about this run.
  `your_input` what the person typed or chose to start the run. Sent only
               when they tick "include my data" for that call; otherwise the
               key holds a note saying it was withheld.

Everything in a digest is DATA. Free text a registry or a file supplied (a
BRENDA row's commentary, a compound name, a title) is in there because the
explanation may need to say what a row said; `prompts.py` puts it behind a
delimiter and says it is never an instruction.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

#: Keys whose values are large and derivable: dropped whole.
DROP_KEYS = frozenset({
    "report_markdown", "document_markdown", "exports", "events", "charts", "times", "columns", "search_log",
    "series", "rows_all", "coordinates", "frames", "svg", "png", "image", "ensemble_candidates",
    "literature_candidates", "relatedness", "form_mixtures", "organism_discrepancies", "source_mixtures",
})
MAX_LIST = 12
MAX_STRING = 600
MAX_DEPTH = 7
BUDGET = 28_000


def _prune(value: Any, depth: int, list_cap: int, string_cap: int) -> Any:
    if isinstance(value, dict):
        if depth >= MAX_DEPTH:
            return {"_omitted": "nested deeper than the digest keeps"}
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if key in DROP_KEYS:
                continue
            out[str(key)] = _prune(item, depth + 1, list_cap, string_cap)
        return out
    if isinstance(value, list):
        if value and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value) and len(value) > 8:
            return f"a series of {len(value)} numbers, left out"
        kept = [_prune(v, depth + 1, list_cap, string_cap) for v in value[:list_cap]]
        if len(value) > list_cap:
            kept.append({"_omitted": f"{len(value) - list_cap} more entries"})
        return kept
    if isinstance(value, str):
        return value if len(value) <= string_cap else value[:string_cap] + " [cut]"
    return value


def digest(kind: str, result: Any, record: Optional[Mapping[str, Any]] = None, *, include_input: bool = False,
           budget: int = BUDGET) -> Dict[str, Any]:
    """The bounded view of a run: kind, title, outcome, result and (optionally) the person's input."""
    record = record or {}
    outcome = record.get("outcome") if isinstance(record.get("outcome"), dict) else None
    base: Dict[str, Any] = {"run_kind": kind}
    if outcome:
        base["outcome"] = {k: outcome.get(k) for k in ("meaning", "summary", "reason", "exit_code") if k in outcome}
    for cap_list, cap_str in ((MAX_LIST, MAX_STRING), (8, 400), (5, 250), (3, 160)):
        built = dict(base)
        trimmed = result
        if isinstance(result, dict) and isinstance(result.get("sections"), list):
            trimmed = dict(result)
            trimmed["sections"] = [{k: v for k, v in sec.items() if k != "data"} if isinstance(sec, dict) else sec
                                   for sec in result["sections"]]
        built["result"] = _prune(trimmed, 0, cap_list, cap_str)
        ranked = ranked_experiments(result)
        if ranked:
            built["ranked_experiments"] = _prune(ranked[:6], 0, cap_list, cap_str)
        if include_input:
            built["your_input"] = _prune(record.get("request") or {}, 0, cap_list, cap_str)
            if record.get("title"):
                built["your_input_title"] = str(record["title"])[:200]
        else:
            built["your_input"] = "withheld: the person did not tick 'include my data' for this call"
        if len(json.dumps(built, ensure_ascii=False)) <= budget:
            return built
    built["result"] = {"_omitted": "the result was too large to send; only its outcome is included"}
    return built


def engine_text(kind: str, result: Any, record: Optional[Mapping[str, Any]] = None) -> str:
    """The engine's own words for a run: what the page shows when the assistant is off or its wording is rejected."""
    record = record or {}
    if isinstance(result, dict):
        verdict = result.get("verdict")
        if isinstance(verdict, dict) and isinstance(verdict.get("text"), str) and verdict["text"].strip():
            return verdict["text"].strip()
        for key in ("document_markdown", "report_text", "report_markdown", "text", "summary"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:4000]
    outcome = record.get("outcome")
    if isinstance(outcome, dict):
        text = outcome.get("reason") or outcome.get("summary")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return "The engine gave no text for this run."


def leaf_facts(value: Any, path: str = "") -> List[Dict[str, Any]]:
    """Flatten a digest into (path, text) facts: the deterministic answer to 'ask this run' when the assistant is off."""
    facts: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        unit = value.get("unit") if isinstance(value.get("unit"), str) else None
        if "value" in value and not isinstance(value["value"], (dict, list)):
            prov = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
            facts.append({"path": path, "text": f"{path}: {value['value']}{(' ' + unit) if unit else ''}"
                          + (f" ({prov.get('kind')})" if prov.get("kind") else ""), "provenance": prov})
        for k, v in value.items():
            facts.extend(leaf_facts(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            facts.extend(leaf_facts(v, f"{path}[{i}]"))
    elif isinstance(value, str) and value.strip() and not path.endswith("_omitted"):
        facts.append({"path": path, "text": f"{path}: {value[:300]}", "provenance": {}})
    return facts


def nearest_facts(digest_value: Mapping[str, Any], question: str, limit: int = 6) -> List[str]:
    """Facts whose path or text shares words with the question: the deterministic stand-in for an answer."""
    import re

    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2}
    scored = []
    for fact in leaf_facts(digest_value.get("result", {}), "result"):
        hay = set(re.findall(r"[a-z0-9]+", fact["text"].lower()))
        score = len(words & hay)
        if score:
            scored.append((score, fact["text"]))
    scored.sort(key=lambda s: -s[0])
    return [t for _, t in scored[:limit]]


def ranked_experiments(result: Any) -> List[Dict[str, Any]]:
    """The engine's own ranked next observations (a compose design section), best first, or [].

    Read from `sections[key=design].data.report.gains`, which is
    `design.DesignReport.gains` as the compose adapter sent it. Only fields the
    engine computed are kept: the observation's key, its description and
    protocol, its novelty and angle, and whether it clears the run's floor."""
    found: List[Dict[str, Any]] = []
    if not isinstance(result, dict):
        return found
    for section in result.get("sections") if isinstance(result.get("sections"), list) else []:
        if not (isinstance(section, dict) and section.get("key") == "design"):
            continue
        data = section.get("data")
        report = data.get("report") if isinstance(data, dict) else None
        gains = report.get("gains") if isinstance(report, dict) else None
        for gain in gains if isinstance(gains, list) else []:
            obs = gain.get("observation") if isinstance(gain, dict) else None
            if not isinstance(obs, dict) or not isinstance(obs.get("key"), str):
                continue
            found.append({
                "key": obs["key"], "description": obs.get("description"), "protocol": obs.get("protocol"),
                "novelty": gain.get("novelty"), "angle_degrees": gain.get("angle_degrees"),
                "informative": bool(gain.get("informative")), "rank_before": gain.get("rank_before"),
                "rank_after": gain.get("rank_after"),
            })
    found.sort(key=lambda g: -(g["novelty"] if isinstance(g["novelty"], (int, float)) else 0.0))
    return found


__all__ = ["BUDGET", "DROP_KEYS", "digest", "engine_text", "leaf_facts", "nearest_facts", "ranked_experiments"]
