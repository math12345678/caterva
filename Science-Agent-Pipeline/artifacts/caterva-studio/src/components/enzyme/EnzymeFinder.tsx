/**
 * The one place an enzyme is chosen.
 *
 * Every screen that asks which enzyme (Compose, Constants, Structures,
 * Dynamics, Binding) uses this, so a name means the same thing on all of
 * them and the engine is only ever sent an EC number. The person types a
 * name ("hexokinase"), an abbreviation ("LDHA"), an EC number ("1.1.1.27")
 * or part of one ("1.1.1"); the finder (`GET /api/enzymes/find`, the
 * IUBMB nomenclature, offline) answers with ranked candidates; the person
 * chooses one, and what the screen holds is that EC number.
 *
 * WHAT IT NEVER DOES
 * - Choose for the person. A name that is several enzymes ("lactate
 *   dehydrogenase" is L- and D-lactate dehydrogenase, and more) shows each
 *   by name; the finder's recommendation is marked "suggested" and still
 *   waits for a click or Enter. Only a query the finder resolved to one
 *   enzyme has an option ready for Enter, and Enter still has to be pressed.
 * - Offer what the finder did not return. UniProt's suggestions appear only
 *   when the server asked UniProt (the nomenclature found nothing and the
 *   network was reachable) and are labelled as UniProt's.
 * - Hide a retired number. A transferred or deleted EC number is shown with
 *   its replacement, or with the fact that it has none.
 *
 * KEYBOARD: ArrowDown and ArrowUp move through the candidates, Enter
 * chooses the highlighted one, Escape clears what was typed. The control is
 * a combobox with a listbox (WAI-ARIA 1.2): focus stays in the input and
 * `aria-activedescendant` names the highlighted option. The candidates open
 * below the field, in the flow of the form, so nothing is clipped by the
 * pane and there is no overlay to dismiss.
 *
 * ONCE CHOSEN the field is a compact summary (EC number in DM Mono, the
 * accepted name, the reaction, and the organism's proteins) with a Change
 * button. A screen that opens with an EC number already (a link, a
 * reopened run) shows the same summary, read from `GET /api/enzymes/{ec}`.
 */
import { type KeyboardEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";

import { chosenEc, isCompleteEc, organismLine, useEnzymeDetail, useEnzymeFind } from "@/api/enzymes";
import type { EnzymeCandidate, EnzymeFindResponse } from "@/api/types";
import { cn } from "@/lib/cn";
import { describeError } from "@/lib/errors";

import "./enzyme.css";

/** What the screen is told when an enzyme is chosen. */
export interface ChosenEnzyme {
  ec: string;
  name: string;
  reaction: string;
}

export interface EnzymeFinderProps {
  /** The chosen EC number, or "" while nothing is chosen. The screen sends this and nothing else. */
  value: string;
  onChange: (ec: string, chosen: ChosenEnzyme | null) => void;
  /** The organism field's text; changing it re-ranks the candidates and re-reads the isozymes. */
  organism?: string;
  /** Text to start the search with when nothing is chosen (a link that carried a name). */
  seed?: string;
  label?: ReactNode;
  optional?: boolean;
  hint?: ReactNode;
  /** The server's message when it refused this field. */
  error?: string | null;
  autoFocus?: boolean;
  disabled?: boolean;
}

/** One row of the list: a finder candidate, or a suggestion UniProt returned. */
interface Row {
  key: string;
  candidate: EnzymeCandidate;
  /** The EC number choosing this row sends, or null when it cannot be chosen. */
  choose: string | null;
  source: "nomenclature" | "uniprot" | "given";
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return settled;
}

/** The sentence above the list: what the finder made of the query, as plainly as it can be said. */
export function summaryLine(answer: EnzymeFindResponse): string {
  const q = answer.query;
  const total = answer.candidates_total;
  switch (answer.outcome) {
    case "resolved":
      return answer.candidates.length > 1 ? `${q} names one enzyme; the others listed also matched.` : `${q} names one enzyme.`;
    case "ambiguous":
      if (answer.confirm_only) {
        return `${q} is an abbreviation or gene symbol, so it is never chosen for you. ${total === 1 ? "This is what it can mean" : `${total} enzymes can be meant`}: choose the one you mean.`;
      }
      return `${total} enzymes match ${q}. Choose the one you mean.`;
    case "partial":
      return `${q} matches only part of an enzyme name, or is a protein symbol. Choose one, or type more of the name.`;
    case "suggestions":
      return `No enzyme is named ${q}. Did you mean:`;
    default: {
      // The finder's own sentence: it says whether a number was deleted or a name matched nothing.
      const why = answer.reason?.trim();
      return why ? `${why.charAt(0).toUpperCase()}${why.slice(1)}` : `Nothing in the nomenclature matches ${q}.`;
    }
  }
}

function rowsOf(answer: EnzymeFindResponse | undefined): Row[] {
  if (!answer) return [];
  const rows: Row[] = answer.candidates.map((c) => ({
    key: `n-${c.ec}`,
    candidate: c,
    choose: chosenEc(c),
    source: "nomenclature",
  }));
  for (const s of answer.fallback?.suggestions ?? []) {
    rows.push({
      key: `u-${s.ec}`,
      source: "uniprot",
      choose: s.ec,
      candidate: {
        ec: s.ec,
        name: s.name ?? "",
        why: "UniProt files reviewed proteins of this name under this EC number",
        tier: 99,
        reaction: "",
        class_path: "",
        alternative_names: [],
        organism: null,
        organism_proteins: [],
        organism_protein_count: 0,
        has_organism_protein: false,
        status: "active",
        superseded_by: [],
        partial_match: false,
        matched_by: "uniprot",
      },
    });
  }
  const given = answer.query.replace(/^\s*(?:E\.?C\.?\s*)/i, "").trim();
  if (answer.outcome === "none" && answer.candidates.length === 0 && isCompleteEc(given)) {
    rows.push({
      key: `g-${given}`,
      source: "given",
      choose: given,
      candidate: {
        ec: given,
        name: "",
        why: "Not in the enzyme nomenclature release Caterva holds. BRENDA may still know this number, so it can be used as given.",
        tier: 99,
        reaction: "",
        class_path: "",
        alternative_names: [],
        organism: null,
        organism_proteins: [],
        organism_protein_count: 0,
        has_organism_protein: false,
        status: "active",
        superseded_by: [],
        partial_match: false,
        matched_by: "ec",
      },
    });
  }
  return rows;
}

function statusText(c: EnzymeCandidate): string | null {
  if (c.status === "transferred") {
    if (c.superseded_by.length === 0) return "transferred";
    return `transferred, now ${c.superseded_by.map((e) => `EC ${e}`).join(" and ")}`;
  }
  if (c.status === "deleted") return "deleted, no replacement";
  return null;
}

function Option({
  row,
  id,
  active,
  organismLabel,
  organismAsked,
  scope,
  total,
  onChoose,
  onHover,
}: {
  row: Row;
  id: string;
  active: boolean;
  organismLabel: string | null;
  organismAsked: boolean;
  /** What the organism code covers when narrower than its name. */
  scope: string | null;
  /** How many enzymes the finder matched in all, listed or not. */
  total: number;
  onChoose: () => void;
  onHover: () => void;
}) {
  const c = row.candidate;
  const status = statusText(c);
  const proteins = c.organism_proteins;
  const line = row.source === "nomenclature" ? organismLine(proteins, c.organism_protein_count, organismLabel, organismAsked, scope) : null;
  const disabled = row.choose === null;
  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      aria-disabled={disabled || undefined}
      className="enz-option"
      data-active={active ? "true" : undefined}
      data-disabled={disabled ? "true" : undefined}
      data-recommended={c.recommended ? "true" : undefined}
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onClick={() => {
        if (!disabled) onChoose();
      }}
    >
      <span className="enz-head">
        <span className="enz-ec font-mono">EC {c.ec}</span>
        {c.name ? <span className="enz-name">{c.name}</span> : null}
        {c.recommended ? <span className="chip" data-tone="signal">suggested</span> : null}
        {c.matched_by === "abbreviation" ? <span className="chip">abbreviation or symbol</span> : null}
        {c.matched_by === "mnemonic" ? <span className="chip">UniProt entry name</span> : null}
        {row.source === "uniprot" ? <span className="chip">from UniProt</span> : null}
        {row.source === "given" ? <span className="chip" data-tone="caution">use as given</span> : null}
        {status ? <span className="chip" data-tone="caution">{status}</span> : null}
      </span>
      <span className="enz-why">{c.why}</span>
      {c.reaction ? (
        <span className="enz-reaction" title={c.reaction}>
          {c.reaction}
        </span>
      ) : null}
      {line ? (
        <span className="enz-organism" data-none={organismAsked && organismLabel && !c.has_organism_protein ? "true" : undefined}>
          {line}
        </span>
      ) : null}
      {c.recommended ? (
        <span className="enz-note">
          The only one of the {total} enzymes matched that has a {organismLabel ?? "listed"} protein. Suggested, not chosen: you choose.
        </span>
      ) : null}
      {c.status === "transferred" && c.superseded_by.length === 1 ? (
        <span className="enz-note">Choosing this uses EC {c.superseded_by[0]}, which replaced it.</span>
      ) : null}
      {c.status === "transferred" && c.superseded_by.length > 1 ? (
        <span className="enz-note">It was split: choose one of the replacements.</span>
      ) : null}
      {c.status === "deleted" ? <span className="enz-note">The nomenclature deleted this number; it cannot be chosen.</span> : null}
    </li>
  );
}

export function EnzymeFinder({
  value,
  onChange,
  organism = "",
  seed = "",
  label = "Enzyme",
  optional = false,
  hint,
  error,
  autoFocus = false,
  disabled = false,
}: EnzymeFinderProps) {
  const id = useId();
  const listId = `${id}-list`;
  const statusId = `${id}-status`;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  const changeRef = useRef<HTMLButtonElement>(null);
  const [query, setQuery] = useState(seed);
  const [open, setOpen] = useState(seed.trim() !== "");
  const [active, setActive] = useState(-1);
  const [picked, setPicked] = useState<ChosenEnzyme | null>(null);
  const [focusAfter, setFocusAfter] = useState<"change" | "input" | null>(null);

  const typed = query.trim();
  const settled = useDebounced(typed, 200);
  const settledOrganism = useDebounced(organism.trim(), 300);
  const waiting = typed !== settled;
  const found = useEnzymeFind(settled, settledOrganism, open && value === "");
  const answer = found.data;
  const rows = useMemo(() => rowsOf(answer), [answer]);
  const organismAsked = Boolean(answer?.organism);
  const organismLabel = answer?.organism_label ?? null;

  // The row Enter would choose: only when the finder resolved the query to one enzyme.
  const resolvedIndex = useMemo(() => {
    if (!answer || answer.outcome !== "resolved" || !answer.resolved_ec) return -1;
    return rows.findIndex((r) => r.source === "nomenclature" && r.candidate.ec === answer.resolved_ec && r.choose !== null);
  }, [answer, rows]);
  useEffect(() => {
    setActive(resolvedIndex);
  }, [resolvedIndex, answer?.query, answer?.organism]);

  // After choosing, focus lands on Change; after Change, on the input.
  useEffect(() => {
    if (focusAfter === "change") changeRef.current?.focus();
    if (focusAfter === "input") inputRef.current?.focus();
    if (focusAfter) setFocusAfter(null);
  }, [focusAfter, value]);

  // A screen that changes `seed` later (a link opened while the screen is up) starts a search from it.
  const seedRef = useRef(seed);
  useEffect(() => {
    if (seed !== seedRef.current) {
      seedRef.current = seed;
      if (seed.trim() && value === "") {
        setQuery(seed);
        setOpen(true);
      }
    }
  }, [seed, value]);

  const detail = useEnzymeDetail(value, organism.trim());
  const shown: ChosenEnzyme | null =
    value === "" ? null : picked && picked.ec === value ? picked : detail.data ? { ec: detail.data.ec, name: detail.data.name, reaction: detail.data.reaction } : null;

  const choose = (row: Row) => {
    if (row.choose === null) return;
    const ec = row.choose;
    const successor = ec !== row.candidate.ec;
    const chosen: ChosenEnzyme = successor
      ? { ec, name: rows.find((r) => r.candidate.ec === ec)?.candidate.name ?? "", reaction: rows.find((r) => r.candidate.ec === ec)?.candidate.reaction ?? "" }
      : { ec, name: row.candidate.name, reaction: row.candidate.reaction };
    setPicked(chosen);
    setQuery("");
    setOpen(false);
    setActive(-1);
    setFocusAfter("change");
    onChange(ec, chosen);
  };

  const change = () => {
    setPicked(null);
    setQuery("");
    setOpen(false);
    setFocusAfter("input");
    onChange("", null);
  };

  const clear = () => {
    setQuery("");
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    const last = rows.length - 1;
    switch (e.key) {
      case "ArrowDown":
        if (rows.length === 0) return;
        e.preventDefault();
        setOpen(true);
        setActive((a) => (a >= last ? last : a + 1));
        return;
      case "ArrowUp":
        if (rows.length === 0) return;
        e.preventDefault();
        setOpen(true);
        setActive((a) => (a <= 0 ? (a === -1 ? last : 0) : a - 1));
        return;
      case "Enter": {
        if (!open || rows.length === 0 || typed === "") return;
        // Never submit the form from here: Enter either chooses or does nothing yet.
        e.preventDefault();
        const row = rows[active];
        if (row && row.choose !== null && !waiting) choose(row);
        return;
      }
      case "Escape":
        if (typed !== "" || open) {
          e.preventDefault();
          e.stopPropagation();
          clear();
        }
        return;
      case "Tab":
        setOpen(false);
        return;
    }
  };

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  if (value !== "") {
    return (
      <div className="field enz">
        <span className="field-label" id={`${id}-label`}>
          {label}
          {optional ? <span className="field-optional">optional</span> : null}
        </span>
        <div className="enz-chip" role="group" aria-labelledby={`${id}-label`} data-state={detail.notListed ? "unlisted" : undefined}>
          <div className="enz-chip-body">
            <span className="enz-head">
              <span className="enz-ec font-mono">EC {value}</span>
              {shown?.name ? <span className="enz-name">{shown.name}</span> : detail.isPending ? <span className="muted">reading the nomenclature</span> : null}
            </span>
            {shown?.reaction ? <span className="enz-reaction">{shown.reaction}</span> : null}
            {detail.data?.name_note ? <span className="enz-note">{detail.data.name_note}</span> : null}
            {detail.data?.isozymes.organism_scope && organism.trim() ? (
              <span className="enz-note">{detail.data.isozymes.organism_scope}</span>
            ) : null}
            {detail.notListed ? (
              <span className="enz-note">
                This number is not in the enzyme nomenclature release Caterva holds, so it is sent as given; BRENDA may still know it.
              </span>
            ) : null}
            {detail.isError && !detail.notListed ? (
              <span className="enz-note">The nomenclature did not answer ({describeError(detail.error).message}). The EC number is still sent.</span>
            ) : null}
            {detail.data && organism.trim() ? (
              <span className="enz-organism" data-none={detail.data.isozymes.organism_known && detail.data.isozymes.count === 0 ? "true" : undefined}>
                {organismLine(
                  detail.data.isozymes.proteins,
                  detail.data.isozymes.count,
                  detail.data.isozymes.organism_label,
                  true,
                  detail.data.isozymes.organism_scope,
                )}
              </span>
            ) : null}
          </div>
          <button ref={changeRef} type="button" className="btn btn-sm" onClick={change} disabled={disabled} aria-label={`Change the enzyme, now EC ${value}`}>
            Change
          </button>
        </div>
        {hint ? (
          <p className="field-hint" id={hintId}>
            {hint}
          </p>
        ) : null}
        {error ? (
          <p className="field-error" id={errorId} role="alert">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  const showPanel = open && typed !== "";
  const activeId = active >= 0 && active < rows.length ? `${id}-opt-${rows[active].key}` : undefined;
  const fallbackNote = answer?.fallback?.note ?? answer?.fallback_unavailable ?? null;
  const unknownOrganism = answer && answer.organism && !answer.organism_code;

  return (
    <div className={cn("field enz")}>
      <label className="field-label" htmlFor={`${id}-input`}>
        {label}
        {optional ? <span className="field-optional">optional</span> : null}
      </label>
      <input
        ref={inputRef}
        id={`${id}-input`}
        type="text"
        className="input"
        role="combobox"
        aria-expanded={showPanel && (rows.length > 0 || Boolean(answer))}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        aria-describedby={[describedBy, statusId].filter(Boolean).join(" ") || undefined}
        aria-invalid={error ? true : undefined}
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
        autoFocus={autoFocus}
        disabled={disabled}
        placeholder="Name, abbreviation or EC number"
        value={query}
        maxLength={200}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          if (typed !== "") setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {hint ? (
        <p className="field-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="field-error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}

      <div className="enz-panel" hidden={!showPanel} aria-busy={waiting || found.isFetching}>
        <p className="enz-status" id={statusId} role="status" aria-live="polite">
          {!showPanel
            ? ""
            : found.isError
              ? `The enzyme finder did not answer: ${describeError(found.error).message}`
              : !answer
                ? "Searching the enzyme nomenclature"
                : waiting || found.isFetching
                  ? `Searching for ${typed}`
                  : summaryLine(answer)}
        </p>
        {showPanel && found.isError ? (
          <button type="button" className="btn btn-sm" onMouseDown={(e) => e.preventDefault()} onClick={() => void found.refetch()}>
            Try again
          </button>
        ) : null}
        <ul id={listId} role="listbox" aria-label={`Enzymes matching ${typed}`} className="enz-list" hidden={rows.length === 0}>
          {rows.map((row, i) => (
            <Option
              key={row.key}
              row={row}
              id={`${id}-opt-${row.key}`}
              active={i === active}
              organismLabel={organismLabel}
              organismAsked={organismAsked}
              scope={answer?.organism_scope ?? null}
              total={answer?.candidates_total ?? rows.length}
              onChoose={() => choose(row)}
              onHover={() => setActive(i)}
            />
          ))}
        </ul>
        {showPanel && answer && !waiting ? (
          <div className="enz-foot">
            {answer.candidates_total > answer.candidates.length ? (
              <p>
                {answer.candidates_total - answer.candidates.length} more match. Type more of the name, or an EC number, to narrow the list.
              </p>
            ) : null}
            {answer.outcome === "ambiguous" && answer.recommended_ec ? (
              <p>
                The finder suggests EC {answer.recommended_ec}, the only one of the {answer.candidates_total} enzymes matched that has a{" "}
                {organismLabel} protein. It does not choose for you.
              </p>
            ) : null}
            {answer.cautions.map((c) => (
              <p key={c} className="enz-caution">
                {c}
              </p>
            ))}
            {answer.outcome === "none" && answer.candidates.length === 0 ? (
              <p>Check the spelling, or type an EC number such as 1.1.1.27. Part of one (1.1.1) lists a class.</p>
            ) : null}
            {fallbackNote ? <p>{fallbackNote}</p> : null}
            {unknownOrganism ? (
              <p>The finder does not know {answer.organism} as an organism, so the list is not ranked by it.</p>
            ) : null}
            <p className="enz-release">Enzyme nomenclature, ExPASy ENZYME release {answer.release}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
