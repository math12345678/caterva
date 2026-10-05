"""Caterva: Smart Science. The Studio's assistant, behind guardrails the engine enforces.

See docs/studio/ASSISTANT.md. The short version: the assistant proposes, the
engine disposes. Nothing here runs a model unless a person has switched it on,
and nothing a model writes reaches a result or the screen without passing a
deterministic check (`grounding`, `intents`) first.
"""
