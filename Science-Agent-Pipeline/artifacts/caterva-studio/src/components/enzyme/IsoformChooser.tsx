/**
 * Which protein is it? Offered when the chosen EC number is several
 * proteins in the organism asked about (EC 2.7.1.1 is five in human).
 *
 * The entries are the enzyme nomenclature's UniProt entries for the
 * organism, read from `GET /api/enzymes/{ec}?organism=`: HXK1_HUMAN,
 * HXK2_HUMAN and so on. Choosing one fills the Isoform field with its symbol
 * (HXK1), which `caterva compose --isoform` then uses to take each constant
 * from a row that measured that isoform. Nothing is chosen for the person,
 * and nothing is shown when the EC number is one protein, none, or the
 * organism is one the finder does not know.
 *
 * A symbol is not always how a paper wrote the isoform ("HK-1" for HXK1),
 * so the Isoform field stays editable beside this; the report says which
 * row a constant was taken from.
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
  return (
    <div className="enz-iso" role="group" aria-label={`Isoforms of EC ${ec} in ${label}`}>
      <p className="field-hint">
        EC {ec} is {iso.count} proteins in {label}. The cited constants may belong to any of them; choose the one the model is about.
      </p>
      <ul className="enz-iso-list">
        {iso.proteins.map((p) => {
          const pressed = value.trim().toLowerCase() === p.symbol.toLowerCase();
          return (
            <li key={p.accession}>
              <button
                type="button"
                className="btn btn-sm enz-iso-button"
                aria-pressed={pressed}
                title={`UniProt ${p.accession}. Sets the isoform to ${p.symbol}.`}
                onClick={() => onChange(pressed ? "" : p.symbol)}
              >
                <span className="font-mono">{p.entry_name}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
