"""recon_task_defaults: builtin merge and deprecated-parameter stripping."""

from app.recon_task_defaults import DEPRECATED_RECON_TASK_PARAMETER_KEYS, effective_parameters


def test_effective_parameters_strips_deprecated_max_retries_from_stored_merge():
    eff = effective_parameters(
        "resolve_domain",
        {"max_retries": 99, "timeout": 999},
    )
    assert "max_retries" not in eff
    assert eff["timeout"] == 999
    assert "chunk_size" in eff


def test_deprecated_keys_constant_includes_max_retries():
    assert "max_retries" in DEPRECATED_RECON_TASK_PARAMETER_KEYS
