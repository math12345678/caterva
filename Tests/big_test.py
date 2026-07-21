# All 5 PMIDs below re-verified live 2026-07 via
# verify_hardcoded_abstracts_debug.py: real papers, titles and abstract
# text match what's excerpted here (42326350 nanoparticles, 42323674
# yeast, 42220071 brain PET, 41187334 HKDC1, 40854155 cerebral modeling).
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

claim = "Hexokinase Km is approximately 0.05 mM"

abstracts = {
    "42326350 (nanoparticles)": "Autonomous reversibility is fundamental to many natural systems... hexokinase (HK) as an enzymatic disassembling trigger...",
    "42323674 (yeast)": "Kinetic analyses revealed a functional specialization, with the hexokinases acting as high-capacity enzymes and Glk1 functioning as a high-affinity, low-capacity kinase...",
    "42220071 (brain PET)": "During neuronal activation, glucose transport and phosphorylation by hexokinase are elevated to meet increased energy requirements...",
    "41187334 (HKDC1)": "we describe the kinetic and regulatory features of recombinant human HKDC1... a unique glucose Km value (0.49 +/- 0.07 mM) that differs markedly from all other human hexokinase isozymes",
    "40854155 (cerebral modeling)": "VmaxHK = 0.260 +/- 0.039 umol/g/min, comparing well with the simpler models...",
}

for label, abstract in abstracts.items():
    prompt = f"""Claim to verify: "{claim}"

Abstract excerpt: "{abstract}"

Does this abstract provide direct, specific support for the claim (a matching or closely matching Km value)? Answer in this exact format:
SUPPORTS: yes/no/partial
REASON: one sentence
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    print(f"=== {label} ===")
    print(response.choices[0].message.content)
    print()
