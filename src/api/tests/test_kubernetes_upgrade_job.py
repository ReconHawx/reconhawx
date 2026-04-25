"""KubernetesService: upgrade Job and batch Job flush exclusions."""

from unittest.mock import MagicMock, patch

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


def test_delete_all_batch_jobs_skips_upgrade_prefix(k8s_no_config):
    svc = k8s_no_config
    svc.batch_v1 = MagicMock()

    def _job(name, active=1):
        j = MagicMock()
        j.metadata.name = name
        j.status = MagicMock(active=active)
        return j

    svc.batch_v1.list_namespaced_job.return_value = MagicMock(
        items=[
            _job("db-restore-1"),
            _job("reconhawx-upgrade-abc"),
            _job("workflow-job-1"),
        ]
    )
    svc.batch_v1.delete_namespaced_job = MagicMock()
    result = svc.delete_all_batch_jobs_flush_kueue()
    assert result["deleted_count"] == 1
    assert result["skipped_restore_count"] == 2
    assert svc.batch_v1.delete_namespaced_job.call_count == 1
    call_kw = svc.batch_v1.delete_namespaced_job.call_args.kwargs
    assert call_kw["name"] == "workflow-job-1"
    assert call_kw["propagation_policy"] == "Background"


def test_count_running_batch_jobs_skips_upgrade_prefix(k8s_no_config):
    svc = k8s_no_config
    svc.batch_v1 = MagicMock()

    def _job(name, active=1):
        j = MagicMock()
        j.metadata.name = name
        j.status = MagicMock(active=active)
        return j

    svc.batch_v1.list_namespaced_job.return_value = MagicMock(
        items=[
            _job("db-restore-1", active=1),
            _job("reconhawx-upgrade-x", active=1),
            _job("runner-work", active=1),
        ]
    )
    n, names = svc.count_running_batch_jobs_exclude_restore()
    assert n == 1
    assert names == ["runner-work"]


def test_create_upgrade_job_build(k8s_no_config, monkeypatch):
    monkeypatch.setenv("KUBERNETES_NAMESPACE", "reconhawx")
    svc = k8s_no_config
    svc.batch_v1 = MagicMock()
    svc.batch_v1.create_namespaced_job.return_value = MagicMock()

    svc.create_upgrade_job(
        "reconhawx-upgrade-test123",
        upgrader_image="ghcr.io/o/reconhawx/upgrader:0.1.0",
        target_version="latest",
        github_repo="ReconHawx/reconhawx",
        pull_token=None,
        staging_id=None,
        api_internal_base=None,
        kueue_resync_quotas=False,
        triggered_by_user_id="u1",
    )

    svc.batch_v1.create_namespaced_job.assert_called_once()
    body = svc.batch_v1.create_namespaced_job.call_args[1]["body"]
    assert body.metadata.name == "reconhawx-upgrade-test123"
    assert body.spec.template.spec.service_account_name == "upgrader-sa"
    assert body.spec.template.spec.automount_service_account_token is True
    assert body.spec.template.spec.containers[0].image == "ghcr.io/o/reconhawx/upgrader:0.1.0"
    env_names = {e.name for e in body.spec.template.spec.containers[0].env}
    assert "RECONHAWX_NS" in env_names
    assert "RECONHAWX_VERSION" in env_names
    assert "RECONHAWX_GITHUB_REPO" in env_names
    env_by_name = {e.name: e.value for e in body.spec.template.spec.containers[0].env}
    assert env_by_name.get("RECONHAWX_OBSERVABILITY") == "1"
    ed = body.spec.template.spec.volumes[0].empty_dir
    assert ed is not None and str(ed.size_limit) == "1Gi"
    assert str(body.spec.template.spec.containers[0].resources.limits["memory"]) == "2Gi"


def test_create_upgrade_job_empty_k8s_namespace_falls_back(k8s_no_config, monkeypatch):
    monkeypatch.setenv("KUBERNETES_NAMESPACE", "")
    svc = k8s_no_config
    svc.batch_v1 = MagicMock()
    svc.batch_v1.create_namespaced_job.return_value = MagicMock()

    svc.create_upgrade_job(
        "reconhawx-upgrade-emptyns",
        upgrader_image="ghcr.io/o/reconhawx/upgrader:0.1.0",
        target_version="0.1.0",
        github_repo="ReconHawx/reconhawx",
    )

    kw = svc.batch_v1.create_namespaced_job.call_args.kwargs
    assert kw["namespace"] == "reconhawx"
    body = kw["body"]
    recon_ns = next(
        e.value for e in body.spec.template.spec.containers[0].env if e.name == "RECONHAWX_NS"
    )
    assert recon_ns == "reconhawx"
