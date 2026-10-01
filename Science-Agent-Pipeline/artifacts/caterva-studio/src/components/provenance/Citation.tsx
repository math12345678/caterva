/**
 * A citation, as the adapter recorded it, one activation from its source.
 *
 * The text is the library's own ("BRENDA ref 641068"), set in DM Mono. It
 * links only where the contract carries a link of a form known to work
 * (CONTRACT.md section 9): `citation.url` (for a BRENDA row, the enzyme
 * page that lists the reference by number), and a PubMed id or DOI through
 * their stable resolvers. Nothing here guesses a link; a citation without
 * one says so, so a missing link is never mistaken for a broken one.
 *
 * Links leave the app: inside Caterva.app they open in the default browser
 * (the shell refuses to navigate its own window away from the studio).
 */
import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import type { Citation as CitationShape } from "@/api/types";
import { cn } from "@/lib/cn";

export function pubmedUrl(pmid: string): string | null {
  return /^[0-9]{1,9}$/.test(pmid) ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : null;
}

export function doiUrl(doi: string): string | null {
  const bare = doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:/i, "");
  return /^10\.\d{4,9}\/\S+$/.test(bare) ? `https://doi.org/${bare}` : null;
}

function External({ href, children, label }: { href: string; children: ReactNode; label?: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label}>
      {children}
      <ExternalLink size={11} aria-hidden="true" />
    </a>
  );
}

export function Citation({
  citation,
  detailed = false,
  className,
}: {
  citation: CitationShape;
  /** Also show title, journal, year, PubMed and DOI when the adapter recorded them. */
  detailed?: boolean;
  className?: string;
}) {
  const pubmed = citation.pubmed ? pubmedUrl(citation.pubmed) : null;
  const doi = citation.doi ? doiUrl(citation.doi) : null;
  const source = [citation.journal, citation.year ?? null].filter((x) => x !== null && x !== undefined && x !== "");
  return (
    <span className={cn("citation", className)}>
      {citation.url ? (
        <External href={citation.url} label={`${citation.text}, opens the source in your browser`}>
          {citation.text}
        </External>
      ) : (
        <span>{citation.text}</span>
      )}
      {detailed ? (
        <>
          {citation.title ? <span className="citation-meta">{citation.title}</span> : null}
          {source.length ? <span className="citation-meta">{source.join(", ")}</span> : null}
          {pubmed ? <External href={pubmed}>PMID {citation.pubmed}</External> : null}
          {doi ? <External href={doi}>doi:{citation.doi}</External> : null}
          {!citation.url && !pubmed && !doi ? (
            <span className="citation-meta">no link was recorded for this source</span>
          ) : null}
          {citation.via ? <span className="citation-meta">via {citation.via}</span> : null}
        </>
      ) : null}
    </span>
  );
}
