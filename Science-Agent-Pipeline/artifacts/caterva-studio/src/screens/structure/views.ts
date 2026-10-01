/**
 * The shapes inside the structure kinds' results that the contract declares
 * loosely (`Record<string, unknown>[]`), as the adapters write them
 * (caterva/studio/adapters/prepare.py and analyze.py). They are read here,
 * never re-derived: every number is still a SourcedValue the backend sent.
 *
 * Declared beside the screens rather than in src/api/types.ts because the
 * contract fixes those fields' types; tightening them there is a contract
 * amendment, and these views are what the amendment would say.
 */
import type { SourcedValue } from "@/api/types";

/** prepare: one catalytic residue as the audit placed it on a chain. */
export interface CatalyticRowView {
  chain: string;
  resseq: string;
  expected: string;
  found: string | null;
  conserved: boolean;
  roles: string;
  reference: string;
  seq_id: number | null;
}

/** prepare: the M-CSA mechanism the catalytic residues come from. */
export interface ReferenceView {
  mcsa_id: number;
  enzyme: string;
  uniprot: string;
  how: string;
  identity: SourcedValue;
  citation: { text: string; url?: string | null };
  rejected: string[];
}

/** prepare: one row of the protonation table, judged at the assay pH. */
export interface ChargeRowView {
  residue: string;
  chain: string;
  resseq: string;
  resname: string;
  catalytic: boolean;
  distance: SourcedValue;
  at_ph: string;
  state: string;
  emphasised: boolean;
  contradicted: boolean;
  uncertain: boolean;
  pka: SourcedValue | null;
  pka_sd: SourcedValue | null;
  protonated: SourcedValue | null;
  band: [SourcedValue, SourcedValue] | null;
  default_protonated: boolean | null;
}

/** analyze: one replica's view of a quantity (convergence_values). */
export interface ReplicaView {
  name: string;
  mean: SourcedValue;
  error: SourcedValue;
  verdict: string;
  frames?: number;
  kept?: number;
  plateaued?: boolean;
  effective_samples?: SourcedValue | null;
}

export interface AngleView {
  label: string;
  crystal: SourcedValue;
  change: SourcedValue;
  moved: boolean;
  change_word: string | null;
  mean: SourcedValue;
  spread: SourcedValue | null;
  ci95: SourcedValue | null;
  verdict: string;
  reasons: string[];
  per_replica: ReplicaView[];
}

export interface FlexibilityView {
  pocket_residues: number;
  rest_residues: number;
  pocket_radius: SourcedValue;
  per_replica: { replica: string; pocket: SourcedValue; rest: SourcedValue; ratio: SourcedValue | null }[];
  measurable: boolean;
  ratio_mean: SourcedValue | null;
  ratio_sd: SourcedValue | null;
  is_result: boolean;
}

export interface HbondView {
  label: string;
  at_start: number;
  bonded: boolean;
  per_replica: { replica: string; fraction: SourcedValue; mean_bonds: SourcedValue }[];
  verdict: string;
  reported: string;
}

export interface RotamerView {
  label: string;
  at_start: SourcedValue;
  start_well: string;
  per_replica: { replica: string; wells: Record<string, SourcedValue>; kept: SourcedValue }[];
  verdict: string;
  reported: string;
}

export interface FaceView {
  label: string;
  crystal_out_of_flat: SourcedValue;
  crystal_face: string;
  per_replica: { replica: string; kept: SourcedValue | null; other: SourcedValue | null }[];
  verdict: string;
  reported: string;
}

export interface WaterView {
  label: string;
  atoms: string[];
  stand_in: boolean;
  at_start: number;
  per_replica: { replica: string; mean: SourcedValue | null; fraction: SourcedValue | null }[];
  verdict: string;
  reported: string;
}

export interface SiteView {
  resnr: number;
  label: string;
  atoms: string[];
  functional: boolean;
}
