import pytest

from src.architecture import ARCHITECTURE_VIEWS, architecture_stages, render_architecture


def test_current_architecture_contains_only_built_components():
    stages = architecture_stages("Current state")

    assert ARCHITECTURE_VIEWS[0] == "Current state"
    assert all(node.status == "built" for stage in stages for node in stage.nodes)
    assert "Kaggle CSV" in render_architecture("Current state")


def test_target_architecture_distinguishes_built_and_planned_components():
    stages = architecture_stages("Target state")
    statuses = {node.status for stage in stages for node in stage.nodes}
    markup = render_architecture("Target state")

    assert statuses == {"built", "planned"}
    for connector in ("Outlook", "Teams", "Zoom", "Slack", "Intercom", "Zendesk"):
        assert connector in markup
    assert "Built today" in markup
    assert "Planned evolution" in markup


def test_unknown_architecture_view_is_rejected():
    with pytest.raises(ValueError, match="Unknown architecture view"):
        architecture_stages("Imaginary state")
