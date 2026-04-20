"""Unit tests for workflow Job/Workload program metadata (Kubernetes label limits)."""

from services.kubernetes import (
    KubernetesService,
    WORKFLOW_PROGRAM_ID_LABEL,
    WORKFLOW_PROGRAM_NAME_ANNOTATION,
)


def test_workflow_program_metadata_uses_id_label_and_name_annotation():
    long_name = "YWH_programme-prive-de-prime-aux-bogues-du-gouvernement-du-quebec-extra"
    program_id = "90c18002-e669-4bd8-a9f5-b7ecbb439b2f"
    wf = {"program_name": long_name, "program_id": program_id}
    labels, annotations = KubernetesService._workflow_program_metadata_fragments(wf)
    assert labels.get(WORKFLOW_PROGRAM_ID_LABEL) == program_id
    assert annotations.get(WORKFLOW_PROGRAM_NAME_ANNOTATION) == long_name
    assert "program" not in labels
    assert all(len(v) <= 63 for v in labels.values())


def test_program_name_from_metadata_prefers_annotation_over_legacy_label():
    meta = {
        "labels": {"program": "short-legacy"},
        "annotations": {WORKFLOW_PROGRAM_NAME_ANNOTATION: "full-from-annotation"},
    }
    assert KubernetesService._program_name_from_workload_metadata(meta) == "full-from-annotation"


def test_program_name_from_metadata_legacy_label_fallback():
    meta = {"labels": {"program": "legacy-only"}, "annotations": {}}
    assert KubernetesService._program_name_from_workload_metadata(meta) == "legacy-only"
