/**
 * A table of results: Ki rows, structures, findings, replicas, runs.
 *
 * Real table semantics (caption, th scope, aria-sort), because a reader
 * comparing Ki rows uses the table's own navigation in a screen reader.
 * Numeric columns are right-aligned in DM Mono with tabular figures, so
 * digits line up; a column whose cells are SourcedValues renders them with
 * <Value>, which carries the mark, so nothing here draws a bare number.
 *
 * Sorting is by a key the column supplies from the row's data, never by
 * the displayed text (which is rounded). A table longer than
 * `virtualizeAbove` rows draws only the rows in view, with spacer rows
 * keeping the scroll height true, so a 5,000-row atom list stays fluid.
 *
 * Rows are selectable with the mouse or the keyboard (Tab to a row, Enter
 * or Space) when `onRowSelect` is given.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  /** The header as plain text, for the sort button's accessible name. */
  headerText?: string;
  cell: (row: Row, index: number) => ReactNode;
  /** A sort key from the row's data (not its display text). Omit to make the column unsortable. */
  sortValue?: (row: Row) => number | string | null;
  numeric?: boolean;
  align?: "start" | "end";
  /** A width the column keeps, as CSS (e.g. "8rem"). */
  width?: string;
}

type SortState = { key: string; dir: "asc" | "desc" } | null;

function compare(a: number | string | null, b: number | string | null): number {
  // Missing values sort last in both directions, so "none" never hides the top of a ranking.
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "en", { numeric: true });
}

export function sortRows<Row>(rows: readonly Row[], column: Column<Row> | undefined, dir: "asc" | "desc"): Row[] {
  if (!column?.sortValue) return [...rows];
  const key = column.sortValue;
  const indexed = rows.map((row, i) => ({ row, i, k: key(row) }));
  indexed.sort((x, y) => {
    if (x.k === null || y.k === null) return compare(x.k, y.k) || x.i - y.i;
    const c = compare(x.k, y.k);
    return (dir === "asc" ? c : -c) || x.i - y.i;
  });
  return indexed.map((x) => x.row);
}

const ROW_HEIGHT = 34;

export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  caption,
  captionHidden = false,
  empty = "Nothing to show.",
  onRowSelect,
  selectedKey,
  initialSort = null,
  virtualizeAbove = 300,
  maxHeight = "32rem",
  className,
}: {
  rows: readonly Row[];
  columns: readonly Column<Row>[];
  rowKey: (row: Row, index: number) => string;
  caption: string;
  captionHidden?: boolean;
  empty?: ReactNode;
  onRowSelect?: (row: Row) => void;
  selectedKey?: string | null;
  initialSort?: SortState;
  virtualizeAbove?: number;
  maxHeight?: string;
  className?: string;
}) {
  const [sort, setSort] = useState<SortState>(initialSort);
  const sorted = useMemo(() => {
    if (!sort) return [...rows];
    return sortRows(
      rows,
      columns.find((c) => c.key === sort.key),
      sort.dir,
    );
  }, [rows, columns, sort]);

  const scroller = useRef<HTMLDivElement>(null);
  const virtual = sorted.length > virtualizeAbove;
  const virtualizer = useVirtualizer({
    count: virtual ? sorted.length : 0,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  const toggle = (key: string) => {
    setSort((s) => (s?.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));
  };

  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, row: Row) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowSelect?.(row);
    }
  };

  const renderRow = (row: Row, index: number) => {
    const key = rowKey(row, index);
    return (
      <tr
        key={key}
        data-selected={selectedKey === key ? "true" : undefined}
        data-interactive={onRowSelect ? "true" : undefined}
        aria-selected={onRowSelect ? selectedKey === key : undefined}
        tabIndex={onRowSelect ? 0 : undefined}
        onClick={onRowSelect ? () => onRowSelect(row) : undefined}
        onKeyDown={onRowSelect ? (e) => onKey(e, row) : undefined}
      >
        {columns.map((c) => (
          <td
            key={c.key}
            data-numeric={c.numeric ? "true" : undefined}
            data-align={c.align ?? (c.numeric ? "end" : undefined)}
          >
            {c.cell(row, index)}
          </td>
        ))}
      </tr>
    );
  };

  const items = virtual ? virtualizer.getVirtualItems() : [];
  const padTop = virtual && items.length ? items[0].start : 0;
  const padBottom = virtual && items.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;

  return (
    <div
      className={cn("table-wrap", className)}
      ref={scroller}
      style={virtual ? { maxHeight } : undefined}
      tabIndex={virtual ? 0 : undefined}
      aria-label={virtual ? caption : undefined}
      role={virtual ? "region" : undefined}
    >
      <table className="table" aria-rowcount={virtual ? sorted.length + 1 : undefined}>
        <caption className={captionHidden ? "sr-only" : undefined}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key ? sort.dir : null;
              return (
                <th
                  key={c.key}
                  scope="col"
                  style={c.width ? { width: c.width } : undefined}
                  data-align={c.align ?? (c.numeric ? "end" : undefined)}
                  aria-sort={active === "asc" ? "ascending" : active === "desc" ? "descending" : c.sortValue ? "none" : undefined}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      className="table-sort"
                      onClick={() => toggle(c.key)}
                      aria-label={`Sort by ${c.headerText ?? c.key}`}
                    >
                      {c.header}
                      {active === "asc" ? (
                        <ArrowUp size={12} aria-hidden="true" />
                      ) : active === "desc" ? (
                        <ArrowDown size={12} aria-hidden="true" />
                      ) : (
                        <ArrowUpDown size={12} aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="table-empty">
                {empty}
              </td>
            </tr>
          ) : virtual ? (
            <>
              {padTop > 0 ? (
                <tr aria-hidden="true">
                  <td colSpan={columns.length} style={{ height: padTop, padding: 0, border: 0 }} />
                </tr>
              ) : null}
              {items.map((item) => renderRow(sorted[item.index], item.index))}
              {padBottom > 0 ? (
                <tr aria-hidden="true">
                  <td colSpan={columns.length} style={{ height: padBottom, padding: 0, border: 0 }} />
                </tr>
              ) : null}
            </>
          ) : (
            sorted.map((row, i) => renderRow(row, i))
          )}
        </tbody>
      </table>
    </div>
  );
}
