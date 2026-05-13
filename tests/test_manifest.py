"""Tests for Pydantic manifest models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from glitch.collectors.manifest import CollectorEntry, Manifest


class TestCollectorEntry:
    def test_valid_construction(self) -> None:
        entry = CollectorEntry(status="ok")
        assert entry.status == "ok"
        assert entry.reason is None
        assert entry.extra == {}

    def test_valid_with_reason(self) -> None:
        entry = CollectorEntry(status="skipped", reason="tool not found")
        assert entry.status == "skipped"
        assert entry.reason == "tool not found"

    def test_valid_with_extra(self) -> None:
        entry = CollectorEntry(status="ok", extra={"units": 3})
        assert entry.extra == {"units": 3}

    def test_serialization(self) -> None:
        entry = CollectorEntry(status="ok", reason="all good", extra={"count": 5})
        data = entry.model_dump()
        assert data == {"status": "ok", "reason": "all good", "extra": {"count": 5}}

    def test_model_dump_json(self) -> None:
        entry = CollectorEntry(status="error", reason="timeout")
        raw = entry.model_dump_json()
        assert '"status"' in raw
        assert '"error"' in raw
        assert '"timeout"' in raw

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            CollectorEntry(status="invalid_status")

    def test_extra_defaults_to_empty_dict(self) -> None:
        entry = CollectorEntry(status="ok")
        assert entry.extra == {}

    def test_model_validate_json_round_trip(self) -> None:
        entry = CollectorEntry(status="skipped", reason="not available")
        raw = entry.model_dump_json()
        restored = CollectorEntry.model_validate_json(raw)
        assert restored.status == entry.status
        assert restored.reason == entry.reason


class TestManifest:
    def test_valid_construction(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={"juju": CollectorEntry(status="ok")},
        )
        assert manifest.glitch_version == "0.1.0"
        assert manifest.collected_at == now
        assert "juju" in manifest.collectors

    def test_multiple_collectors(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={
                "juju": CollectorEntry(status="ok"),
                "k8s": CollectorEntry(status="skipped", reason="no kubectl"),
                "lxd": CollectorEntry(status="error", reason="timeout"),
            },
        )
        assert len(manifest.collectors) == 3
        assert manifest.collectors["juju"].status == "ok"
        assert manifest.collectors["k8s"].status == "skipped"
        assert manifest.collectors["lxd"].status == "error"

    def test_model_dump_json_includes_all_fields(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={"juju": CollectorEntry(status="ok", extra={"units": 2})},
        )
        raw = manifest.model_dump_json()
        assert '"glitch_version"' in raw
        assert '"collected_at"' in raw
        assert '"collectors"' in raw
        assert '"juju"' in raw

    def test_model_validate_json_round_trips(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={
                "juju": CollectorEntry(status="ok"),
                "ceph": CollectorEntry(status="skipped", reason="no ceph"),
            },
        )
        raw = manifest.model_dump_json()
        restored = Manifest.model_validate_json(raw)
        assert restored.glitch_version == manifest.glitch_version
        assert isinstance(restored.collected_at, datetime)
        assert len(restored.collectors) == 2
        assert restored.collectors["ceph"].reason == "no ceph"

    def test_collector_values_are_typed(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={"juju": CollectorEntry(status="ok")},
        )
        assert isinstance(manifest.collectors["juju"], CollectorEntry)

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(glitch_version="0.1.0", processors={})  # noqa: F841

    def test_empty_collectors(self) -> None:
        now = datetime.now(timezone.utc)
        manifest = Manifest(
            glitch_version="0.1.0",
            collected_at=now,
            collectors={},
        )
        assert len(manifest.collectors) == 0
        assert manifest.model_dump()["collectors"] == {}