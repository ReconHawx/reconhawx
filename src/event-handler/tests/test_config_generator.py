"""Unit tests for config_generator.py"""

import pytest
import tempfile
import os

from app.config_generator import (
    generate_typosquat_config,
    generate_critical_findings_config,
    generate_asset_discovery_config,
    generate_comprehensive_config,
    save_config,
)


class TestGenerateTyposquatConfig:
    """Tests for generate_typosquat_config."""

    def test_returns_dict_with_handlers(self):
        config = generate_typosquat_config()
        assert isinstance(config, dict)
        assert "handlers" in config
        assert isinstance(config["handlers"], list)

    def test_handlers_have_required_fields(self):
        config = generate_typosquat_config()
        assert len(config["handlers"]) >= 1
        handler = config["handlers"][0]
        assert "event_type" in handler
        assert handler["event_type"] == "findings.nuclei.typosquat"
        assert "conditions" in handler
        assert "actions" in handler

    def test_actions_include_discord_and_workflow(self):
        config = generate_typosquat_config()
        action_types = [a["type"] for a in config["handlers"][0]["actions"]]
        assert "discord_notification" in action_types
        assert "workflow_trigger" in action_types
        assert "log" in action_types


class TestGenerateCriticalFindingsConfig:
    """Tests for generate_critical_findings_config."""

    def test_returns_dict_with_handlers(self):
        config = generate_critical_findings_config()
        assert "handlers" in config
        assert len(config["handlers"]) >= 1

    def test_event_type_is_critical(self):
        config = generate_critical_findings_config()
        assert config["handlers"][0]["event_type"] == "findings.nuclei.critical"

    def test_conditions_check_severity(self):
        config = generate_critical_findings_config()
        conditions = config["handlers"][0]["conditions"]
        severity_cond = next(c for c in conditions if c.get("field") == "severity")
        assert severity_cond["expected_value"] == "critical"
        assert severity_cond["operator"] == "equals"


class TestGenerateAssetDiscoveryConfig:
    """Tests for generate_asset_discovery_config."""

    def test_returns_multiple_handlers(self):
        config = generate_asset_discovery_config()
        assert len(config["handlers"]) >= 2

    def test_includes_subdomain_and_domain_handlers(self):
        config = generate_asset_discovery_config()
        event_types = [h["event_type"] for h in config["handlers"]]
        assert "assets.subdomain.created" in event_types
        assert "assets.domain.created" in event_types


class TestGenerateComprehensiveConfig:
    """Tests for generate_comprehensive_config."""

    def test_includes_all_handler_types(self):
        config = generate_comprehensive_config(include_examples=False)
        event_types = [h["event_type"] for h in config["handlers"]]
        assert "findings.nuclei.typosquat" in event_types
        assert "findings.nuclei.critical" in event_types
        assert "assets.subdomain.created" in event_types

    def test_include_examples_adds_more_handlers(self):
        config_no_examples = generate_comprehensive_config(include_examples=False)
        config_with_examples = generate_comprehensive_config(include_examples=True)
        assert len(config_with_examples["handlers"]) > len(config_no_examples["handlers"])

    def test_examples_include_high_and_ip_handlers(self):
        config = generate_comprehensive_config(include_examples=True)
        event_types = [h["event_type"] for h in config["handlers"]]
        assert "findings.nuclei.high" in event_types
        assert "assets.ip.created" in event_types


class TestSaveConfig:
    """Tests for save_config."""

    def test_save_config_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "handlers.yaml")
            config = {"handlers": [{"event_type": "test.event", "actions": []}]}
            result = save_config(config, filepath)
            assert result is True
            assert os.path.exists(filepath)

    def test_save_config_refuses_overwrite_by_default(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            filepath = f.name
        try:
            config = {"handlers": []}
            save_config(config, filepath)
            result = save_config(config, filepath, overwrite=False)
            assert result is False
        finally:
            os.unlink(filepath)

    def test_save_config_overwrites_when_requested(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            filepath = f.name
        try:
            config1 = {"handlers": [{"event_type": "old"}]}
            config2 = {"handlers": [{"event_type": "new"}]}
            save_config(config1, filepath)
            result = save_config(config2, filepath, overwrite=True)
            assert result is True
            with open(filepath) as fp:
                content = fp.read()
            assert "new" in content
        finally:
            os.unlink(filepath)
