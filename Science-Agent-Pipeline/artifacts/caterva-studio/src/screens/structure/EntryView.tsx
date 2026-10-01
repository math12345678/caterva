/**
 * One PDB entry in 3D with what the tools know about its active site: the
 * atoms (GET /api/structure/{id}/coordinates), the entry's own citation,
 * and which M-CSA mechanism the catalytic residues were carried over from,
 * with the identity that carried them. Used by Structures and Prepare.
 *
 * The viewer (three.js) is loaded only when an entry is opened, so the
 * screens around it paint without it.
 */
import { lazy, Suspense, useState } from "react";

import { ApiRequestError } from "@/api/client";
import { Value } from "@/components/provenance/Value";
import { Loading } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";

import { useCoordinates } from "./useCoordinates";

const MoleculeView = lazy(() => import("./MoleculeView").then((m) => ({ default: m.MoleculeView })));

export function EntryView({ pdbId }: { pdbId: string }) {
  const coords = useCoordinates(pdbId);
  const [selected, setSelected] = useState<string | null>(null);

  if (coords.isPending) {
    return (
      <div className="py-8">
        <Loading label={`Reading PDB ${pdbId}'s atoms, fetched and cached as caterva prepare fetches them`} />
      </div>
    );
  }
  if (coords.isError) {
    const error =
      coords.error instanceof ApiRequestError
        ? coords.error.error
        : { code: "crash" as const, message: String(coords.error) };
    return <ErrorState error={error} />;
  }
  const c = coords.data;
  const ref = c.catalytic_reference ?? null;
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        <p className="m-0 text-[13.5px]">
          <span className="font-mono">{c.pdb_id}</span>
          {c.title ? <span className="text-muted">{`  ${c.title.charAt(0)}${c.title.slice(1).toLowerCase()}`}</span> : null}
        </p>
        <p className="m-0 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] text-muted">
          {c.method ? <span>{c.method.toLowerCase()}</span> : null}
          {c.resolution ? (
            <span className="text-fg">
              <Value v={c.resolution} />
            </span>
          ) : null}
          <span>
            {c.citation.url ? (
              <a href={c.citation.url} target="_blank" rel="noreferrer noopener">
                {c.citation.text}
              </a>
            ) : (
              c.citation.text
            )}
          </span>
        </p>
      </div>
      <Suspense fallback={<Loading label="Starting the 3D view" />}>
        <MoleculeView coords={c} selected={selected} onSelect={setSelected} />
      </Suspense>
      {ref ? (
        <p className="m-0 max-w-[75ch] text-[13px] text-muted">
          Catalytic residues from M-CSA entry <span className="font-mono">{ref.mcsa_id}</span> ({ref.enzyme}, reference{" "}
          <span className="font-mono">{ref.uniprot}</span>), chosen by {ref.how}; sequence identity to chain{" "}
          {c.chains?.[0] ?? "?"}{" "}
          <span className="text-fg">
            <Value v={ref.identity} />
          </span>
          , carried onto each chain by global alignment.{" "}
          {ref.citation.url ? (
            <a href={ref.citation.url} target="_blank" rel="noreferrer noopener">
              {ref.citation.text}
            </a>
          ) : (
            ref.citation.text
          )}
          {ref.rejected.length ? `. Not used: ${ref.rejected.join("; ")}.` : null}
        </p>
      ) : null}
    </div>
  );
}
