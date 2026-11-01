import { FileDown, FileJson } from "lucide-react";
import { exportResultCSV, exportResultJSON } from "@/lib/export";

interface ExportButtonsProps {
  trajectory: Record<string, number>[];
  result?: Record<string, unknown>;
  filenamePrefix?: string;
  runId?: string;
}

export default function ExportButtons({
  trajectory,
  result,
  filenamePrefix = "simulation",
  runId,
}: ExportButtonsProps) {
  const id = runId ? `-${runId.slice(0, 8)}` : "";
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() =>
          exportResultCSV(trajectory, `${filenamePrefix}${id}.csv`)
        }
        className="flex items-center gap-1 rounded border border-fg/[0.12] px-2 py-1 text-[10px] text-fg/70 hover:text-fg/80 hover:border-fg/[0.24] transition-all duration-200 bg-fg/[0.02] hover:bg-fg/[0.04]"
        title="Download trajectory as CSV"
      >
        <FileDown className="size-3" />
        CSV
      </button>
      {result && (
        <button
          onClick={() =>
            exportResultJSON(result, `${filenamePrefix}${id}.json`)
          }
          className="flex items-center gap-1 rounded border border-fg/[0.12] px-2 py-1 text-[10px] text-fg/70 hover:text-fg/80 hover:border-fg/[0.24] transition-all duration-200 bg-fg/[0.02] hover:bg-fg/[0.04]"
          title="Download full result as JSON"
        >
          <FileJson className="size-3" />
          JSON
        </button>
      )}
    </div>
  );
}
