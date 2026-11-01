export interface EnzymeEntry {
  pattern: RegExp;
  enzymeName: string;
  substrates: string[];
  ecNumber: string;
  description: string;
  organism: string;
}

export const ENZYMES: EnzymeEntry[] = [
  {
    pattern: /lactate dehydrogenase|ldh/i,
    enzymeName: "lactate dehydrogenase",
    substrates: ["lactate", "pyruvate"],
    ecNumber: "1.1.1.27",
    description: "Interconverts lactate and pyruvate with NAD+",
    organism: "Homo sapiens",
  },
  {
    pattern: /hexokinase|hk\d?/i,
    enzymeName: "hexokinase",
    substrates: ["glucose", "ATP"],
    ecNumber: "2.7.1.1",
    description: "Phosphorylates glucose to glucose-6-phosphate",
    organism: "Homo sapiens",
  },
  {
    pattern: /acetylcholinesterase|ache/i,
    enzymeName: "acetylcholinesterase",
    substrates: ["acetylcholine", "acetylthiocholine"],
    ecNumber: "3.1.1.7",
    description: "Hydrolyzes acetylcholine in synaptic cleft",
    organism: "Homo sapiens",
  },
  {
    pattern: /trypsin/i,
    enzymeName: "trypsin",
    substrates: ["protein"],
    ecNumber: "3.4.21.4",
    description:
      "Serine protease that cleaves peptide chains at lysine/arginine",
    organism: "Homo sapiens",
  },
  {
    pattern: /chymotrypsin/i,
    enzymeName: "chymotrypsin",
    substrates: ["protein"],
    ecNumber: "3.4.21.1",
    description: "Serine protease that cleaves at aromatic residues",
    organism: "Homo sapiens",
  },
  {
    pattern: /alcohol dehydrogenase|adh/i,
    enzymeName: "alcohol dehydrogenase",
    substrates: ["ethanol", "acetaldehyde"],
    ecNumber: "1.1.1.1",
    description: "Oxidizes ethanol to acetaldehyde with NAD+",
    organism: "Homo sapiens",
  },
  {
    pattern: /catalase/i,
    enzymeName: "catalase",
    substrates: ["hydrogen peroxide", "H2O2"],
    ecNumber: "1.11.1.6",
    description: "Decomposes hydrogen peroxide to water and oxygen",
    organism: "Homo sapiens",
  },
  {
    pattern: /cytochrome c oxidase|cox|complex iv/i,
    enzymeName: "cytochrome c oxidase",
    substrates: ["cytochrome c", "oxygen"],
    // EC 1.9.3.1 until 2026-09-05. IUBMB TRANSFERRED that number to
    // 7.1.1.9 when class EC 7 (translocases) was created in 2018 --
    // cytochrome c oxidase pumps protons, so it is a translocase.
    // Verified against Expasy the same day: EC/1.9.3.1.txt reads
    // "Transferred entry: 7.1.1.9", and 7.1.1.9 is "cytochrome-c oxidase".
    //
    // A transferred EC still resolves, which is why this survived: it
    // looks like a working identifier and is silently the wrong one. All
    // 24 EC numbers in this table were checked against Expasy; this was
    // the only stale one. Guarded now by
    // scripts/check_ec_numbers_current.py.
    ecNumber: "7.1.1.9",
    description: "Terminal enzyme of electron transport chain",
    organism: "Homo sapiens",
  },
  {
    pattern: /dna polymerase|dna pol/i,
    enzymeName: "DNA polymerase",
    substrates: ["dNTPs", "DNA template"],
    ecNumber: "2.7.7.7",
    description: "Synthesizes DNA from deoxynucleotides",
    organism: "Escherichia coli",
  },
  {
    pattern: /phosphofructokinase|pfk/i,
    enzymeName: "phosphofructokinase-1",
    substrates: ["fructose-6-phosphate", "ATP"],
    ecNumber: "2.7.1.11",
    description: "Key regulatory enzyme of glycolysis",
    organism: "Homo sapiens",
  },
  {
    pattern: /pyruvate kinase|pklr?/i,
    enzymeName: "pyruvate kinase",
    substrates: ["phosphoenolpyruvate", "ADP"],
    ecNumber: "2.7.1.40",
    description: "Final ATP-generating step of glycolysis",
    organism: "Homo sapiens",
  },
  {
    pattern: /superoxide dismutase|sod/i,
    enzymeName: "superoxide dismutase",
    substrates: ["superoxide"],
    ecNumber: "1.15.1.1",
    description: "Scavenges superoxide radicals",
    organism: "Homo sapiens",
  },
  {
    pattern: /ribulose.?bisphosphate carboxylase|rubisco/i,
    enzymeName: "RuBisCO",
    substrates: ["ribulose-1,5-bisphosphate", "CO2"],
    ecNumber: "4.1.1.39",
    description: "Carbon fixation in photosynthesis",
    organism: "Arabidopsis thaliana",
  },
  {
    pattern: /acetyl.?coa carboxylase|acc/i,
    enzymeName: "acetyl-CoA carboxylase",
    // "biotin" was listed here as a substrate until 2026-09-05. It is not
    // one: it is the PROSTHETIC GROUP, covalently attached to the
    // biotin-carboxyl-carrier-protein domain, which ferries a carboxyl
    // between the enzyme's two active sites and is never consumed.
    // Expasy's reaction for EC 6.4.1.2 is
    //   hydrogencarbonate + acetyl-CoA + ATP = malonyl-CoA + ADP +
    //   phosphate + H(+)
    // and biotin does not appear in it at all.
    //
    // This was not cosmetic. queryResolver.ts picks the substrate a query
    // mentions out of THIS list, so "Km of acetyl-CoA carboxylase for
    // biotin" would have been accepted as a well-formed request and sent
    // to BRENDA looking for the Km of a cofactor that has none.
    //
    // Replaced with the two real co-substrates the old list omitted.
    substrates: ["acetyl-CoA", "hydrogencarbonate", "ATP"],
    ecNumber: "6.4.1.2",
    description: "Regulates fatty acid synthesis",
    organism: "Homo sapiens",
  },
  {
    pattern: /hiv.?1 protease|hiv protease/i,
    enzymeName: "HIV-1 protease",
    substrates: ["Gag-Pol polyprotein"],
    ecNumber: "3.4.23.16",
    description: "Viral protease essential for HIV maturation",
    organism: "Human immunodeficiency virus 1",
  },
  // The entries below were added after "amylase" and other common
  // undergraduate-biochem enzymes silently fell through this list (matched
  // no pattern, so no EC number, so no BRENDA lookup ever ran) and the
  // resolver defaulted with no indication *why*. This list is still finite
  // and still not a substitute for a real name -> EC lookup service; it
  // just now covers more of the enzymes people actually type.
  {
    pattern: /(alpha[\s-]?)?amylase/i,
    enzymeName: "alpha-amylase",
    substrates: ["starch", "glycogen"],
    ecNumber: "3.2.1.1",
    description: "Hydrolyzes alpha-1,4-glycosidic bonds in starch",
    organism: "Homo sapiens",
  },
  {
    pattern: /pepsin/i,
    enzymeName: "pepsin",
    substrates: ["protein"],
    ecNumber: "3.4.23.1",
    description: "Acid protease that cleaves peptide bonds in the stomach",
    organism: "Homo sapiens",
  },
  {
    pattern: /lysozyme/i,
    enzymeName: "lysozyme",
    substrates: ["peptidoglycan"],
    ecNumber: "3.2.1.17",
    description: "Hydrolyzes peptidoglycan in bacterial cell walls",
    organism: "Gallus gallus",
  },
  {
    pattern: /carbonic anhydrase/i,
    enzymeName: "carbonic anhydrase",
    substrates: ["carbon dioxide", "water"],
    ecNumber: "4.2.1.1",
    description: "Catalyzes the reversible hydration of CO2",
    organism: "Homo sapiens",
  },
  {
    pattern: /beta[\s-]?galactosidase|lactase/i,
    enzymeName: "beta-galactosidase",
    substrates: ["lactose"],
    ecNumber: "3.2.1.23",
    description: "Hydrolyzes lactose into glucose and galactose",
    organism: "Escherichia coli",
  },
  {
    pattern: /glucose oxidase/i,
    enzymeName: "glucose oxidase",
    substrates: ["glucose", "oxygen"],
    ecNumber: "1.1.3.4",
    description: "Oxidizes beta-D-glucose to D-glucono-1,5-lactone",
    organism: "Aspergillus niger",
  },
  {
    pattern: /urease/i,
    enzymeName: "urease",
    substrates: ["urea"],
    ecNumber: "3.5.1.5",
    description: "Hydrolyzes urea into ammonia and carbamate",
    organism: "Canavalia ensiformis",
  },
  {
    pattern: /(triacylglycerol )?lipase/i,
    enzymeName: "triacylglycerol lipase",
    substrates: ["triglycerides"],
    ecNumber: "3.1.1.3",
    description: "Hydrolyzes ester bonds in triglycerides",
    organism: "Homo sapiens",
  },
  {
    pattern: /glucose-?6-?phosphate dehydrogenase|g6pd/i,
    enzymeName: "glucose-6-phosphate dehydrogenase",
    substrates: ["glucose-6-phosphate", "NADP+"],
    ecNumber: "1.1.1.49",
    description: "First and rate-limiting enzyme of the pentose phosphate pathway",
    organism: "Homo sapiens",
  },
];

export function matchEnzyme(query: string): EnzymeEntry | undefined {
  const lower = query.toLowerCase();
  for (const entry of ENZYMES) {
    if (entry.pattern.test(lower)) {
      return entry;
    }
  }
  return undefined;
}
