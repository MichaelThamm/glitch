"""Tests for remediation planning."""
from __future__ import annotations

from glitch.analyze._classify import ClassificationVerdict
from glitch.analyze._remediate import (
    RemediationAction,
    plan_remediation,
)


def _verdict(test_id: str, labels: dict[str, float]) -> ClassificationVerdict:
    return ClassificationVerdict(
        test_id=test_id, labels=labels, reasoning_trace=""
    )


class TestPlanRemediation:
    def test_charm_bug_above_threshold(self) -> None:
        verdicts = [_verdict("t1", {"charm-bug": 0.95})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert len(plan.entries) == 1
        assert plan.entries[0].action == RemediationAction.PATCH

    def test_charm_bug_below_threshold(self) -> None:
        verdicts = [_verdict("t1", {"charm-bug": 0.6})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert len(plan.entries) == 1
        assert plan.entries[0].action == RemediationAction.SUGGESTION

    def test_test_bug_above_threshold(self) -> None:
        verdicts = [_verdict("t1", {"test-bug": 0.9})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert len(plan.entries) == 1
        assert plan.entries[0].action == RemediationAction.PATCH

    def test_test_bug_below_threshold(self) -> None:
        verdicts = [_verdict("t1", {"test-bug": 0.5})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert len(plan.entries) == 1
        assert plan.entries[0].action == RemediationAction.SUGGESTION

    def test_flaky_any_confidence(self) -> None:
        verdicts = [_verdict("t1", {"flaky": 0.95})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.entries[0].action == RemediationAction.SUGGESTION

        verdicts = [_verdict("t1", {"flaky": 0.3})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.entries[0].action == RemediationAction.SUGGESTION

    def test_infrastructure(self) -> None:
        verdicts = [_verdict("t1", {"infrastructure": 0.9})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.entries[0].action == RemediationAction.ISSUE_TEMPLATE

    def test_environment(self) -> None:
        verdicts = [_verdict("t1", {"environment": 0.9})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.entries[0].action == RemediationAction.ISSUE_TEMPLATE

    def test_unknown(self) -> None:
        verdicts = [_verdict("t1", {"unknown": 0.5})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.entries[0].action == RemediationAction.NARRATIVE

    def test_patch_generated_flag(self) -> None:
        verdicts = [_verdict("t1", {"charm-bug": 0.9})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.patch_generated is True

        verdicts = [_verdict("t1", {"flaky": 0.9})]
        plan = plan_remediation(verdicts, threshold=0.8)
        assert plan.patch_generated is False

    def test_multiple_verdicts(self) -> None:
        verdicts = [
            _verdict("t1", {"charm-bug": 0.9, "flaky": 0.3}),
            _verdict("t2", {"infrastructure": 0.95}),
        ]
        plan = plan_remediation(verdicts, threshold=0.8)
        actions = {(e.test_id, e.label): e.action for e in plan.entries}
        assert actions[("t1", "charm-bug")] == RemediationAction.PATCH
        assert actions[("t1", "flaky")] == RemediationAction.SUGGESTION
        assert actions[("t2", "infrastructure")] == RemediationAction.ISSUE_TEMPLATE
        assert plan.patch_generated is True
