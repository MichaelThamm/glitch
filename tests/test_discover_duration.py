"""Tests for the duration string parser (ADR 0009)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from glitch.discover._duration import parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1h", timedelta(hours=1)),
        ("12h", timedelta(hours=12)),
        ("30d", timedelta(days=30)),
        ("2w", timedelta(weeks=2)),
        ("0d", timedelta(0)),
        ("100w", timedelta(weeks=100)),
    ],
)
def test_parse_duration_accepts_valid_forms(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "1.5d",
        "30 d",
        "1d2h",
        "30",
        "30days",
        "1m",
        "1M",
        "-1d",
        "d",
        "",
        "  30d  ",
    ],
)
def test_parse_duration_rejects_invalid_forms(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)


def test_parse_duration_error_message_shape() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_duration("30days")
    msg = str(excinfo.value)
    assert "invalid duration" in msg
    assert "Expected <N><h|d|w>" in msg
    assert "'30days'" in msg
