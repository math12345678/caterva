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
    description: "Serine protease that cleaves peptide chains at lysine/arginine",
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
    ecNumber: "1.9.3.1",
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
    substrates: ["acetyl-CoA", "biotin"],
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
