"""Wright-Fisher scenario presets."""

try:
    from Tellurium.scenarios.wf_scenarios import (_SCENARIO_REGISTRY, list_scenarios, wright_fisher_scenario)
except (ModuleNotFoundError, ImportError):
    from scenarios.wf_scenarios import (_SCENARIO_REGISTRY, list_scenarios, wright_fisher_scenario)
