/**
 * The figure: measured rates with error bars, the fitted curve with its band,
 * the residuals beneath, and the buttons that take it to a paper.
 *
 * The drawing is `figureSvg`, the same function the exports use, so what is
 * on the page is what is saved. The numbers are also a table one activation
 * away, because a screen reader cannot read a plot and a person checking a
 * point wants the digits.
 */
import { Download, Image } from "lucide-react";
import { useMemo, useState } from "react";

import type { RatesFigure } from "@/api/types";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Segmented } from "@/components/forms/Segmented";
import { DataTable } from "@/components/table/DataTable";
import { describeError } from "@/lib/errors";
import { formatNumber } from "@/lib/format";
import { notify } from "@/lib/toast";

import { COLUMNS, type Column, figureSvg, PAGE_OPTIONS } from "./figureSvg";
import { figureFile, figureFileName, figurePng, pngSize, saveBlob, saveText } from "./exports";

interface PointRow {
  key: string;
  series: string;
  line: number;
  s: number | null;
  v: number | null;
  sigma: number | null;
  fitted: number | null;
  residual: number | null;
}

export function pointRows(fig: RatesFigure): PointRow[] {
  return fig.series.flatMap((s) =>
    s.points.s.map((v, k) => ({
      key: `${s.key}-${k}`,
      series: s.label || s.law_title,
      line: s.points.line[k],
      s: v,
      v: s.points.v[k],
      sigma: s.points.sigma[k],
      fitted: s.points.fitted[k],
      residual: s.points.residual[k],
    })),
  );
}

const num = (v: number | null) => (v === null ? "none" : formatNumber(v));

export function RatesChart({ figure, base }: { figure: RatesFigure; base: string }) {
  const [log, setLog] = useState(false);
  const [column, setColumn] = useState<Column>("single");
  const [white, setWhite] = useState(true);
  const [busy, setBusy] = useState(false);
  const drawn = useMemo(() => figureSvg(figure, { ...PAGE_OPTIONS, logX: log }), [figure, log]);
  const legend = figure.series.map((s, i) => ({ label: s.label || s.law_title, index: i, note: s.label ? s.law_title : undefined }));
  const xs = pointRows(figure).filter((r) => r.s !== null && r.s <= 0).length;
  const failed = (what: string) => (e: unknown) => notify("failed", `${what} was not saved`, { description: describeError(e).message });
  const level = figure.series[0]?.level ?? 0.95;

  return (
    <div className="r-figure">
      <div className="r-figure-controls">
        <Segmented
          label="Concentration axis"
          size="sm"
          value={log ? "log" : "linear"}
          options={[
            { value: "linear", label: "Linear axis" },
            { value: "log", label: "Log axis" },
          ]}
          onChange={(v) => setLog(v === "log")}
        />
      </div>
      <ChartFrame
        title="Initial rates and the fitted curve"
        summary={`${figure.series.length} series, ${pointRows(figure).length} measurements, with a residual plot beneath`}
        height={600}
        legend={legend}
        caption={
          <>
            Markers are your measured rates; the line is the fitted law and the shaded band its {Math.round(level * 1000) / 10}% band
            ({figure.series[0]?.band ?? "no band"}). {figure.bars?.text} The panel beneath is measured minus fitted, about zero.
            {log && xs ? ` ${drawn.hidden} measurement(s) at zero concentration cannot be drawn on a logarithmic axis.` : ""}
            {figure.notes.length ? ` ${figure.notes.join(" ")}` : ""}
          </>
        }
        table={
          <DataTable
            caption="Every measurement, what the curve gives there, and the difference"
            captionHidden
            rows={pointRows(figure)}
            rowKey={(r) => r.key}
            columns={[
              ...(figure.series.length > 1 ? [{ key: "series", header: "Series", cell: (r: PointRow) => r.series }] : []),
              { key: "line", header: "Line", numeric: true, cell: (r: PointRow) => r.line },
              { key: "s", header: `${figure.x.column}${figure.x.unit ? ` (${figure.x.unit})` : ""}`, numeric: true, cell: (r: PointRow) => num(r.s) },
              { key: "v", header: `${figure.y.column}${figure.y.unit ? ` (${figure.y.unit})` : ""}`, numeric: true, cell: (r: PointRow) => num(r.v) },
              { key: "sigma", header: "Error bar", numeric: true, cell: (r: PointRow) => num(r.sigma) },
              { key: "fitted", header: "Fitted", numeric: true, cell: (r: PointRow) => num(r.fitted) },
              { key: "residual", header: "Residual", numeric: true, cell: (r: PointRow) => num(r.residual) },
            ]}
          />
        }
      >
        <div className="r-svg" dangerouslySetInnerHTML={{ __html: drawn.svg }} />
      </ChartFrame>
      <div className="r-figure-export" role="group" aria-label="Save the figure for a paper">
        <Segmented
          label="Figure width"
          size="sm"
          value={column}
          options={(Object.keys(COLUMNS) as Column[]).map((c) => ({ value: c, label: c === "single" ? "Single column" : "Double column" }))}
          onChange={(v) => setColumn(v as Column)}
        />
        <label className="r-toggle r-toggle-inline">
          <input type="checkbox" checked={white} onChange={(e) => setWhite(e.target.checked)} />
          <span>White background</span>
        </label>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => saveText(figureFileName(base, column, "svg"), figureFile(figure, column, log, white), "image/svg+xml;charset=utf-8")}
        >
          <Download size={13} aria-hidden="true" />
          SVG
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            figurePng(figure, column, log, white)
              .then((blob) => saveBlob(figureFileName(base, column, "png"), blob))
              .catch(failed("The PNG"))
              .finally(() => setBusy(false));
          }}
        >
          <Image size={13} aria-hidden="true" />
          PNG, 300 dpi
        </button>
        <span className="r-figure-size font-mono">
          {COLUMNS[column].label}; PNG {pngSize(column).width} by {pngSize(column).height} px
        </span>
      </div>
    </div>
  );
}
