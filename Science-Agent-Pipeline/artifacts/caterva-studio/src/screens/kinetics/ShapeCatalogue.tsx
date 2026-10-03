/**
 * The shapes `caterva compose` recognises, as the server lists them
 * (`GET /api/compose/shapes`, exactly `grammar.shapes()`): each entry is
 * "name: what it is". Choosing one writes its description into the
 * mechanism field, where it can be edited before anything runs; a shape
 * whose description needs a number ("N catalytic steps") is offered as it
 * reads, and the engine's own refusal says what to change if it is sent
 * unedited. Nothing here guesses a phrasing the grammar may not accept.
 *
 * `limit` shows the first few as suggestions (Home) with the rest one
 * activation away; the filter matches name and description.
 */
import { ChevronDown } from "lucide-react";
import { useId, useMemo, useState } from "react";

export interface Shape {
  name: string;
  description: string;
}

export function parseShapes(shapes: readonly string[]): Shape[] {
  return shapes.map((s) => {
    const at = s.indexOf(": ");
    return at < 0 ? { name: s, description: s } : { name: s.slice(0, at), description: s.slice(at + 2) };
  });
}

/** What choosing a shape writes into the mechanism field. */
export function phraseFor(shape: Shape): string {
  return shape.description;
}

export function ShapeCatalogue({
  shapes,
  error,
  onPick,
  limit,
  startOpen = false,
}: {
  shapes: readonly string[] | undefined;
  error?: boolean;
  onPick: (phrase: string) => void;
  /** Show this many as suggestions before the list is opened. */
  limit?: number;
  startOpen?: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  const [filter, setFilter] = useState("");
  const listId = useId();
  const parsed = useMemo(() => parseShapes(shapes ?? []), [shapes]);
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const matching = q ? parsed.filter((s) => `${s.name} ${s.description}`.toLowerCase().includes(q)) : parsed;
    return open ? matching : limit ? matching.slice(0, limit) : [];
  }, [parsed, filter, open, limit]);

  if (error) return <p className="field-hint">The list of shapes did not load; any description can still be sent, and the engine says when it does not recognise one.</p>;
  if (!shapes) return <p className="field-hint">Reading the shapes the grammar recognises</p>;

  return (
    <div className="k-shapes">
      <div className="k-shapes-head">
        <button
          type="button"
          className="k-shapes-toggle"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((o) => !o)}
        >
          <ChevronDown size={13} aria-hidden="true" data-open={open ? "true" : undefined} />
          {open ? "Hide the shapes" : <>Browse the <span className="font-mono">{parsed.length}</span> shapes it recognises</>}
        </button>
        {open ? (
          <input
            className="input k-shapes-filter"
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter shapes"
            aria-label="Filter the shapes"
            spellCheck={false}
            autoComplete="off"
          />
        ) : null}
      </div>
      {shown.length ? (
        <ul className="k-shapes-list" id={listId} data-open={open ? "true" : undefined} aria-label="Recognised shapes">
          {shown.map((s) => (
            <li key={s.name}>
              <button type="button" className="k-shape" onClick={() => onPick(phraseFor(s))}>
                <span className="k-shape-name font-mono">{s.name.replace(/_/g, " ")}</span>
                <span className="k-shape-desc">{s.description}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : open ? (
        <p className="field-hint" id={listId}>
          No shape matches. Any description can still be sent; the engine says whether it recognises it.
        </p>
      ) : null}
    </div>
  );
}
