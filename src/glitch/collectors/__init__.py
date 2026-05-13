"""Collection phase – gathers telemetry from the active deployment environment."""

from glitch.collectors.base import Collector, CollectorResult, get_collectors, run_tool
from glitch.collectors.ceph import CephCollector
from glitch.collectors.juju import JujuCollector
from glitch.collectors.kubernetes import KubernetesCollector
from glitch.collectors.lxd import LXDCollector
from glitch.collectors.runner import run_collectors
from glitch.collectors.test_artifacts import TestArtifactsCollector

__all__ = [
    "CephCollector",
    "Collector",
    "CollectorResult",
    "JujuCollector",
    "KubernetesCollector",
    "LXDCollector",
    "TestArtifactsCollector",
    "get_collectors",
    "run_collectors",
    "run_tool",
]