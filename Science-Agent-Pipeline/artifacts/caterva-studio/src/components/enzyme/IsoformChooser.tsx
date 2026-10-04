/**
 * Which protein is it? Offered when the chosen EC number is a few proteins
 * in the organism asked about (EC 2.7.1.1 is five in human).
 *
 * The proteins are the enzyme nomenclature's UniProt entries for the
 * organism, read from `GET /api/enzymes/{ec}?organism=` and shown by the
 * gene symbol UniProt gives them (HK1, HK2, GCK), not by entry-name
 * mnemonic (HXK1, HXK4), which no paper writes. Choosing one fills the
 * Isoform field with that gene symbol, and says so.
 *
 * WHAT THE ISOFORM FIELD DOES. `caterva compose --isoform HK2` takes each
 * constant from a BRENDA row whose own commentary names that isozyme, under
 * any of the names UniProt gives the protein (hexokinase II, HK-2, HXK2).
 * It does not make a constant belong to that isozyme: where no row names one,
 * the constant is taken from a row that names none and is flagged, and where
 * every row names another, it is refused. The result says which happened.
 *
 * A broad class (more than 12 proteins under one EC number, such as the 245
 * human kinases of EC 2.7.11.1) is not isozymes of one enzyme: no chooser is
 * offered for it, only the plain statement. Nothing is shown when the EC
 * number is one protein, none, or the organism is one the finder does not
 * know. Nothing is chosen for the person.
 */
import { useEnzymeDetail } from "@/api/enzymes";

export function IsoformChooser({
  ec,
  organism,
  value,
  onChange,
}: {
  ec: string;
  organism: string;
  value: string;
  onChange: (isoform: string) => void;
}) {
  const detail = useEnzymeDetail(ec, organism.trim());
  if (!ec || !organism.trim() || !detail.data) return null;
  const iso = detail.data.isozymes;
  if (!iso.organism_known || iso.proteins.length < 2) return null;
  const label = iso.organism_label ?? organism.trim();
  if (iso.broad) {
    return (
      <div className="enz-iso" role="group" aria-label={`Proteins of EC ${ec} in ${label}`}>
        <p className="field-hint">
          {iso.count} different {label} proteins share EC {ec} (a broad class), so the cited constants may belong to any of them. They are
          not isozymes of one enzyme, and no list of them is offered here. If the model is about one protein, type its gene symbol in the
          Isoform field; the result says whether a row names it.
        </p>
      </div>
    );
  }
  const chosen = iso.proteins.find((p) => (p.label ?? p.symbol).toLowerCase() === value.trim().toLowerCase());
  return (
    <div className="enz-iso" role="group" aria-label={`Isoforms of EC ${ec} in ${label}`}>
      <p className="field-hint">
        EC {ec} is {iso.count} proteins in {label}
        {iso.organism_scope ? ` (${iso.organism_scope})` : ""}. The cited constants may belong to any of them; choose the one the model is
        about.
      </p>
      <ul className="enz-iso-list">
        {iso.proteins.map((p) => {
          const name = p.label ?? p.symbol;
          const pressed = value.trim().toLowerCase() === name.toLowerCase();
          return (
            <li key={p.accession}>
              <button
                type="button"
                className="btn btn-sm enz-iso-button"
                aria-pressed={pressed}
                title={`UniProt ${p.accession} (${p.entry_name}). Fills the Isoform field with ${name}.`}
                onClick={() => onChange(pressed ? "" : name)}
              >
                <span className="font-mono">{name}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {chosen ? (
        <p className="field-hint" data-testid="isoform-filled">
          Filled the Isoform field with <span className="font-mono">{chosen.label ?? chosen.symbol}</span> (UniProt {chosen.accession}).{" "}
          {chosen.engine_matches && chosen.names?.length
            ? `Compose takes a constant from a row whose commentary names it as any of: ${chosen.names.slice(0, 6).join(", ")}. A constant whose rows name no isozyme is kept and flagged, and one whose rows all name another isozyme is refused.`
            : "Caterva knows no other names for this protein, so rows are compared with this text as typed; a row that states the isozyme in other words will not match, and the result says so."}
        </p>
      ) : null}
      {iso.filed_elsewhere ? <p className="field-hint">{iso.filed_elsewhere}.</p> : null}
    </div>
  );
}
