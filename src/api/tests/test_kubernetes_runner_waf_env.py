"""Runner pod template injects WAF quarantine env from system_settings."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from kubernetes import config as kube_config

from services.kubernetes import KubernetesService


@pytest.fixture
def k8s_no_config():
    with patch.object(
        kube_config,
        "load_incluster_config",
        side_effect=kube_config.ConfigException(),
    ):
        with patch.object(kube_config, "load_kube_config"):
            yield KubernetesService()


@pytest.mark.asyncio
async def test_workflow_pod_template_includes_waf_quarantine_env(k8s_no_config):
    svc = k8s_no_config
    execution_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    workflow_data = {
        "workflow_id": "wf-def-1",
        "execution_id": execution_id,
        "name": "Test WF",
        "steps": [],
        "program_name": "prog-a",
    }

    waf_eff = {
        "enabled": True,
        "max_attempts": 3,
        "delay_seconds": 2100,
        "quarantine_ttl": 1111,
        "secondary_promote": 4,
        "secondary_window": 2222,
    }

    with patch(
        "services.workflow_waf_auto_rerun_settings.get_workflow_waf_auto_rerun_effective",
        new_callable=AsyncMock,
        return_value=waf_eff,
    ):
        with patch(
            "services.workflow_kubernetes_settings.get_workflow_kubernetes_merged",
            new_callable=AsyncMock,
            return_value={
                "runner_image": "ghcr.io/example/runner:1",
                "worker_image": "ghcr.io/example/worker:1",
                "image_pull_policy": "IfNotPresent",
            },
        ):
            with patch.object(svc, "_get_aws_credentials", new_callable=AsyncMock, return_value=None):
                pod = await svc._create_workflow_pod_template(
                    workflow_data, execution_id, f"workflow-data-{execution_id}"
                )

    env = {e["name"]: e["value"] for e in pod["spec"]["containers"][0]["env"] if "value" in e}
    assert env["WAF_QUARANTINE_TTL"] == "1111"
    assert env["WAF_SECONDARY_PROMOTE"] == "4"
    assert env["WAF_SECONDARY_WINDOW"] == "2222"
