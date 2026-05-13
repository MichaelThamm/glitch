"""Tests for LLM classification parsing and prompt building."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from glitch.analyze._classify import (
    ClassificationVerdict,
    _build_prompt,
    parse_classification,
)
from glitch.analyze._loader import AnalysisContext


class TestParseClassification:
    def test_parse_fenced_json(self) -> None:
        raw = '```json\n{"test_id": "test-foo", "labels": {"flaky": 0.9}}\n```'
        verdict = parse_classification(raw)
        assert isinstance(verdict, ClassificationVerdict)
        assert verdict.test_id == "test-foo"
        assert verdict.labels == {"flaky": 0.9}

    def test_parse_nested_braces_in_string(self) -> None:
        raw = (
            '```json\n'
            '{"test_id": "test-foo", "labels": {"flaky": 0.9}, '
            '"reasoning_trace": "check {braces} in string"}\n'
            '```'
        )
        verdict = parse_classification(raw)
        assert verdict.test_id == "test-foo"
        assert verdict.reasoning_trace == "check {braces} in string"

    def test_parse_no_fence_nested_json(self) -> None:
        raw = '{"test_id": "test-foo", "labels": {"flaky": 0.9}}'
        verdict = parse_classification(raw)
        assert verdict.labels == {"flaky": 0.9}

    def test_parse_bare_json(self) -> None:
        raw = '{"test_id": "test-bar", "labels": {"charm-bug": 0.85}, "reasoning_trace": "Step 1: x"}'
        verdict = parse_classification(raw)
        assert verdict.test_id == "test-bar"
        assert verdict.labels == {"charm-bug": 0.85}
        assert verdict.reasoning_trace == "Step 1: x"

    def test_parse_json_with_text_around(self) -> None:
        raw = 'Some preamble text.\n{"test_id": "test-baz", "labels": {"infrastructure": 0.7}}\nExtra trailing text.'
        verdict = parse_classification(raw)
        assert verdict.test_id == "test-baz"
        assert verdict.labels == {"infrastructure": 0.7}

    def test_parse_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON object found"):
            parse_classification("just some random text, no JSON at all")

    def test_parse_defaults_for_missing_fields(self) -> None:
        raw = '{"reasoning_trace": "some reasoning"}'
        verdict = parse_classification(raw)
        assert verdict.test_id == "unknown-test"
        assert verdict.labels == {"unknown": 1.0}
        assert verdict.reasoning_trace == "some reasoning"


class TestBuildPrompt:
    def test_build_prompt_without_discovery(self, tmp_path: pytest.TempPathFactory) -> None:
        ctx = AnalysisContext(
            artifact_dir=tmp_path,
            manifest={"test_id": "integration-test", "repository": "test-repo"},
            collector_paths={},
            discovery=None,
        )
        with patch(
            "glitch.analyze._loader.read_collector_content", return_value={}
        ):
            prompt = _build_prompt(ctx)
        assert "integration-test" in prompt
        assert "classification taxonomy" in prompt.lower() or "flaky" in prompt.lower()
        assert "## Flakiness Context" not in prompt

    def test_build_prompt_with_discovery(self, tmp_path: pytest.TempPathFactory) -> None:
        discovery = {
            "flakiness_index": 0.78,
            "heuristic_breakdown": {"change_independence": 0.9, "timing": 0.5},
        }
        ctx = AnalysisContext(
            artifact_dir=tmp_path,
            manifest={"test_id": "integration-test", "repository": "test-repo"},
            collector_paths={},
            discovery=discovery,
        )
        with patch(
            "glitch.analyze._loader.read_collector_content", return_value={}
        ):
            prompt = _build_prompt(ctx)
        assert "Flakiness Context" in prompt
        assert "0.78" in prompt
        assert "change_independence" in prompt
