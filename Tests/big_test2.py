# abstract_hkdc1 below re-verified live 2026-07 via
# verify_hkdc1_full_abstract_debug.py against the FULL abstract text
# (not just the opening) for PMID 41187334: every specific number quoted
# here (kcat/Km,glucose = 1.5 x 10^4 M-1 s-1; Km = 0.49 +/- 0.07 mM;
# G6P inhibition constant above 1 mM) is verbatim real text from the
# published abstract, not approximated or invented.
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# This claim is designed to actually match PMID 41187334 correctly
claim_correct = "The human hexokinase isozyme HKDC1 has a glucose Km value of approximately 0.49 mM"

# This claim is designed to be a subtle near-miss - right ballpark, wrong specifics
claim_near_miss = "Human HKDC1 has a glucose Km value of approximately 0.49 mM and is potently inhibited by glucose-6-phosphate at physiological concentrations"

abstract_hkdc1 = "we describe the kinetic and regulatory features of recombinant human HKDC1, demonstrating it to be a robust hexokinase (kcat/Km,glucose = 1.5 x 10^4 M-1 s-1) with a unique glucose Km value (0.49 +/- 0.07 mM) that differs markedly from all other human hexokinase isozymes... Unlike all other 100 kDa vertebrate hexokinases characterized to date, HKDC1 is insensitive to product inhibition by physiological concentrations of glucose 6-phosphate, with apparent inhibition constants above 1 mM."

def check(claim, abstract, label):
    prompt = f"""Claim to verify: "{claim}"

Abstract excerpt: "{abstract}"

Does this abstract provide direct, specific support for the claim? Check every specific detail in the claim against the abstract, not just the general topic.

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

check(claim_correct, abstract_hkdc1, "TEST A: Should say YES (accurate claim)")
check(claim_near_miss, abstract_hkdc1, "TEST B: Should say NO or PARTIAL (Km right, but inhibition claim is backwards - abstract says INSENSITIVE to G6P, not inhibited)")
