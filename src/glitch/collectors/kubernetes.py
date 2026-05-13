"""Collect telemetry from a Kubernetes cluster."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from glitch.collectors.base import Collector, CollectorResult, register, run_tool

logger = logging.getLogger(__name__)


@register
class KubernetesCollector(Collector):
    """Collect cluster events, pod descriptions, and logs for troubled pods.

    Args:
        namespace: Optional Kubernetes namespace.  Defaults to all namespaces.
    """

    name = "kubernetes"
    priority = 20

    def __init__(self, *, namespace: str | None = None) -> None:
        self.namespace = namespace

    def detect(self) -> bool:
        return shutil.which("kubectl") is not None

    def collect(self, output_dir: Path) -> CollectorResult:
        base = output_dir / "k8s"
        base.mkdir(parents=True, exist_ok=True)

        artifacts: list[Path] = []

        _collect_events(base, artifacts, self.namespace)
        _collect_troubled_pods(base, artifacts, self.namespace)

        return CollectorResult(status="ok", artifacts=artifacts)


def _collect_events(base: Path, artifacts: list[Path], namespace: str | None) -> None:
    scope = ["-n", namespace] if namespace else ["-A"]
    try:
        result = run_tool(
            ["kubectl", "get", "events", *scope, "--sort-by=.lastTimestamp", "-o", "json"],
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("kubectl get events failed: %s", result.stderr[:200])
            return
        data = json.loads(result.stdout)
        path = base / "events.json"
        path.write_text(json.dumps(data, indent=2))
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("kubectl get events timed out")
    except json.JSONDecodeError as exc:
        logger.warning("kubectl get events returned invalid JSON: %s", exc)
    except Exception:
        logger.exception("Unexpected error collecting kubernetes events")


def filter_failed_pods(pods_data: dict) -> list[dict]:
    """Return pods with non-Running phase or containers with restart_count > 0."""
    failed: list[dict] = []
    for item in pods_data.get("items", []):
        status = item.get("status", {})
        phase = status.get("phase", "Unknown")
        if phase != "Running":
            failed.append(item)
            continue
        for container_status in status.get("containerStatuses", []):
            if container_status.get("restartCount", 0) > 0:
                failed.append(item)
                break
        else:
            if "containerStatuses" not in status:
                failed.append(item)
    return failed


def _collect_troubled_pods(
    base: Path, artifacts: list[Path], namespace: str | None
) -> None:
    scope = ["-n", namespace] if namespace else ["-A"]
    try:
        result = run_tool(["kubectl", "get", "pods", *scope, "-o", "json"], timeout=30)
        if result.returncode != 0:
            logger.warning("kubectl get pods failed: %s", result.stderr[:200])
            return
        pods_data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("kubectl get pods timed out")
        return
    except json.JSONDecodeError as exc:
        logger.warning("kubectl get pods returned invalid JSON: %s", exc)
        return
    except Exception:
        logger.exception("Unexpected error listing kubernetes pods")
        return

    for item in filter_failed_pods(pods_data):
        metadata = item.get("metadata", {})
        pod_name = metadata.get("name", "")
        pod_ns = metadata.get("namespace", "default")
        status = item.get("status", {})

        container_restarts: dict[str, int] = {}
        for container_status in status.get("containerStatuses", []):
            restart_count = container_status.get("restartCount", 0)
            if restart_count > 0:
                container_restarts[container_status.get("name", "")] = restart_count

        _collect_pod_describe(base, artifacts, pod_name, pod_ns)
        for c_name, rc in container_restarts.items():
            if rc > 0:
                _collect_pod_logs(base, artifacts, pod_name, pod_ns, c_name)


def _collect_pod_describe(
    base: Path, artifacts: list[Path], pod: str, namespace: str
) -> None:
    pods_dir = base / "pods"
    pods_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_tool(
            ["kubectl", "describe", "pod", pod, "-n", namespace],
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "kubectl describe pod %s/%s failed: %s", namespace, pod, result.stderr[:200]
            )
            return
        path = pods_dir / f"{pod}-describe.txt"
        path.write_text(result.stdout)
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("kubectl describe pod %s/%s timed out", namespace, pod)
    except Exception:
        logger.exception("Unexpected error describing pod %s/%s", namespace, pod)


def _collect_pod_logs(
    base: Path,
    artifacts: list[Path],
    pod: str,
    namespace: str,
    container: str,
) -> None:
    pods_dir = base / "pods"
    pods_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_tool(
            ["kubectl", "logs", pod, "-c", container, "--previous", "-n", namespace],
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "kubectl logs %s/%s (%s) failed: %s",
                namespace,
                pod,
                container,
                result.stderr[:200],
            )
            return
        path = pods_dir / f"{pod}-{container}.txt"
        path.write_text(result.stdout)
        artifacts.append(path)
    except subprocess.TimeoutExpired:
        logger.warning("kubectl logs %s/%s (%s) timed out", namespace, pod, container)
    except Exception:
        logger.exception(
            "Unexpected error collecting logs for %s/%s (%s)", namespace, pod, container
        )
