"""Orchestrate the collection of all telemetry and produce a manifest + summary."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from glitch import __version__
from glitch.collectors.base import CollectorResult, get_collectors
from glitch.collectors.manifest import CollectorEntry, Manifest
from glitch.collectors.summary import build_summary

if TYPE_CHECKING:
    from rich.progress import TaskID

logger = logging.getLogger(__name__)


def run_collectors(
    output_dir: Path,
    *,
    model: str | None = None,
    namespace: str | None = None,
    test_artifacts_dir: Path | None = None,
) -> None:
    """Run all registered collectors sequentially and produce manifest.json + summary.md.

    Args:
        output_dir: Directory to write all telemetry artifacts into.
        model: Juju model name passed to the Juju collector.
        namespace: Kubernetes namespace passed to the Kubernetes collector.
        test_artifacts_dir: Directory with pre-existing test output files.

    Raises:
        typer.Exit: If no collector succeeded.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    collector_classes = get_collectors()
    is_tty = sys.stdout.isatty()

    collector_results: dict[str, CollectorResult] = {}
    total_artifacts = 0

    console = Console() if is_tty else None
    progress: Progress | None = None
    task: TaskID | None = None

    def _log_collector(name: str, status: str, *, artifacts: int = 0, elapsed: float = 0.0) -> None:
        msg = f"{name}: {status}"
        if status == "ok":
            msg += f" ({artifacts} artifacts, {elapsed:.1f}s)"
        if console is not None:
            console.log(msg)
        else:
            logger.info(msg)

    rich_handler: RichHandler | None = None

    if is_tty:
        rich_handler = RichHandler(
            console=console, show_time=False, show_path=False
        )
        logging.root.addHandler(rich_handler)

        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        )
        task = progress.add_task("Collecting…", total=len(collector_classes))
        progress.start()

    try:
        for cls in collector_classes:
            if progress is not None and task is not None:
                progress.update(task, description=f"Collecting {cls.name}…")

            try:
                instance = _instantiate(cls, model, namespace, test_artifacts_dir)
            except TypeError as exc:
                msg = f"Failed to instantiate collector '{cls.name}': {exc}"
                logger.error(msg)
                collector_results[cls.name] = CollectorResult(status="error", reason=msg)
                _ci_log(cls.name, "error", console=console)
                if progress is not None and task is not None:
                    progress.advance(task)
                continue

            try:
                if not instance.detect():
                    collector_results[cls.name] = CollectorResult(
                        status="skipped",
                        reason=f"{cls.name} tool not available or source not found",
                    )
                    _log_collector(cls.name, "skipped")
                    _ci_log(cls.name, "skipped", console=console)
                    if progress is not None and task is not None:
                        progress.advance(task)
                    continue

                start = time.monotonic()
                result = instance.collect(output_dir)
                elapsed = time.monotonic() - start

                collector_results[cls.name] = result
                total_artifacts += len(result.artifacts)
                _log_collector(
                    cls.name,
                    result.status,
                    artifacts=len(result.artifacts),
                    elapsed=elapsed,
                )
                _ci_log(cls.name, result.status, console=console)
            except Exception:
                msg = f"Collector '{cls.name}' crashed"
                logger.exception(msg)
                collector_results[cls.name] = CollectorResult(status="error", reason=msg)
                _ci_log(cls.name, "error", console=console)

            if progress is not None and task is not None:
                progress.advance(task)
    finally:
        if rich_handler is not None:
            logging.root.removeHandler(rich_handler)
        if progress is not None:
            progress.stop()

    _write_manifest(output_dir, collector_results)
    _write_summary(output_dir)

    ok_count = sum(1 for r in collector_results.values() if r.status == "ok")
    if ok_count == 0:
        msg = (
            "No collectors ran successfully. "
            "Ensure at least one backend tool (juju, kubectl, lxc, ceph) "
            "is installed and accessible."
        )
        typer.echo(msg, err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Collected {total_artifacts} artifact(s) from {ok_count} collector(s) into {output_dir}"
    )


def _instantiate(
    cls: type,
    model: str | None,
    namespace: str | None,
    test_artifacts_dir: Path | None,
):
    kwargs: dict[str, object] = {}
    if cls.name == "juju":
        kwargs["model"] = model
    elif cls.name == "kubernetes":
        kwargs["namespace"] = namespace
    elif cls.name == "test_artifacts":
        kwargs["source_dir"] = test_artifacts_dir
    return cls(**kwargs)


def _ci_log(name: str, status: str, *, console: Console | None = None) -> None:
    msg = f"[COLLECT] {name}: {status}"
    if console is not None:
        console.log(msg)
    else:
        typer.echo(msg, err=True)


def _write_manifest(
    output_dir: Path, collector_results: dict[str, CollectorResult]
) -> None:
    entries: dict[str, CollectorEntry] = {}
    for name, result in collector_results.items():
        entries[name] = CollectorEntry(
            status=result.status,
            reason=result.reason,
            extra=result.extra,
        )

    manifest = Manifest(
        glitch_version=__version__,
        collected_at=datetime.now(timezone.utc),
        collectors=entries,
    )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2))
    logger.info("Manifest written to %s", manifest_path)


def _write_summary(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        logger.warning("No manifest found; skipping summary generation")
        return

    manifest = Manifest.model_validate_json(manifest_path.read_text())
    summary_md = build_summary(manifest, output_dir)

    summary_path = output_dir / "summary.md"
    summary_path.write_text(summary_md)
    logger.info("Summary written to %s", summary_path)