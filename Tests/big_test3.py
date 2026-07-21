# abstract_hkdc1 below re-verified live 2026-07 via
# verify_hkdc1_full_abstract_debug.py against the FULL abstract text for
# PMID 41187334: kcat/Km, the 0.49 +/- 0.07 mM Km value, the T58M mutant
# name, and the "2-fold decrease in catalytic efficiency" phrasing are
# all verbatim real text from the published abstract.
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

abstract_hkdc1 = "we describe the kinetic and regulatory features of recombinant human HKDC1, demonstrating it to be a robust hexokinase (kcat/Km,glucose = 1.5 x 10^4 M-1 s-1) with a unique glucose Km value (0.49 +/- 0.07 mM) that differs markedly from all other human hexokinase isozymes. An HKDC1 variant associated with retinitis pigmentosa, T58M, displays a modest, but statistically significant 2-fold decrease in catalytic efficiency compared to the wild-type enzyme."

def check(claim, abstract, label):
    prompt = f"""Claim to verify: "{claim}"

Abstract excerpt: "{abstract}"

Does this abstract provide direct, specific support for the claim? Check every specific detail (numbers, entities, species, direction of effect) against the abstract, not just the general topic.

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

# TEST C: Close-but-not-exact number. Real value is 0.49. This claims 0.50.
# A too-strict system says NO on trivial rounding. A well-calibrated one says
# YES or PARTIAL, since 0.49 rounds to 0.5 and is within the paper's own +/- 0.07 error bar.
check(
    "HKDC1 has a glucose Km value of approximately 0.50 mM",
    abstract_hkdc1,
    "TEST C: Numerical boundary case (0.50 claimed vs 0.49 +/- 0.07 actual)"
)

# TEST D: Entity swap. Real mutant is T58M. This claims a DIFFERENT mutant, T58A,
# with the same described effect. Tests whether the model checks the SPECIFIC
# entity/name, or just pattern-matches "a mutant with reduced activity."
check(
    "The HKDC1 variant T58A shows a 2-fold decrease in catalytic efficiency compared to wild-type",
    abstract_hkdc1,
    "TEST D: Entity-swap deception (T58A claimed, but abstract says T58M)"
)

# TEST E: Claim with genuinely no support in this abstract at all - tests
# whether it correctly says NO rather than inventing a connection.
check(
    "HKDC1 expression is upregulated by insulin signaling in adipose tissue",
    abstract_hkdc1,
    "TEST E: Plausible-sounding claim with zero actual support in this abstract"
)
