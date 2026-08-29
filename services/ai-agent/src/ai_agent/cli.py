"""Typer CLI for the AI agent service."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

# services/ai-agent - the alembic.ini lives here; the CLI is invoked via
# `uv run --directory services/ai-agent ai-agent ...`, so never resolve
# relative to the process CWD (which is already services/ai-agent, making a
# nested path). cli.py lives at services/ai-agent/src/ai_agent/, so
# parents[2] is services/ai-agent.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

app = typer.Typer(name="ai-agent", help="Skyrict AI agent service CLI", no_args_is_help=True)


@app.command()
def serve(
    port: int = typer.Option(8002, help="Port to bind."),
    reload: bool = typer.Option(False, help="Enable auto-reload (dev only)."),
) -> None:
    """Run the AI agent service with uvicorn."""
    import uvicorn

    uvicorn.run(
        "ai_agent.main:app",
        host="0.0.0.0",  # dev server bind; containers bind anyway
        port=port,
        reload=reload,
    )


@app.command()
def migrate(head: str = typer.Option("head", help="Alembic target revision")) -> None:
    """Run database migrations (version table: alembic_version_ai)."""
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", head],
        cwd=_PACKAGE_ROOT,
        check=True,
    )


@app.command()
def attrition_train(
    dataset: str = typer.Option(
        "", "--dataset", help="optional CSV (see features/attrition/cli.py)"
    ),
    version: str = typer.Option("v1-gbc-2026-08", "--version"),
    output: str = typer.Option(
        "", "--output", help="artifact path (default: bundled artifacts dir)"
    ),
    max_depth: int = typer.Option(3, "--max-depth"),
    estimators: int = typer.Option(40, "--estimators"),
) -> None:
    """Manually train + export the HR attrition GBC model (spec §6 cadence)."""
    from ai_agent.features.attrition.cli import train as attrition_train_cmd

    out = output or str(
        _PACKAGE_ROOT / "src" / "ai_agent" / "features" / "attrition" / "artifacts" / "model.joblib"
    )
    attrition_train_cmd(
        dataset=dataset,
        version=version,
        output=out,
        max_depth=max_depth,
        estimators=estimators,
    )


@app.command()
def eval_hr_models(
    config: str = typer.Option(
        str(_PACKAGE_ROOT / "tests" / "eval" / "hr_models.yaml"),
        "--config",
        help="path to the HR model eval registry (YAML)",
    ),
    model_path: str = typer.Option(
        "", "--model-path", help="model artifact path (default: bundled default)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="compute + print only; do not persist to core"
    ),
    core_url: str = typer.Option(
        "", "--core-url", envvar="SKYRICT_CORE_URL", help="core service base URL"
    ),
    token: str = typer.Option(
        "", "--token", envvar="SKYRICT_CORE_TOKEN", help="bearer token with erp.hr.ai.eval"
    ),
    tenant_slug: str = typer.Option(
        "", "--tenant-slug", envvar="SKYRICT_TENANT_SLUG", help="tenant slug for the eval run"
    ),
) -> None:
    """Evaluate the deployed HR models against the labeled seed sets (SKY-72).

    Prints one line per metric, WARNS (never fails) when precision is below
    the documented 0.70 threshold, and posts the results to core's
    ``/api/v1/ai/hr/eval-runs`` endpoint for the historical record. Redact-safe:
    seed rows carry features + labels only, never employee PII.
    """
    import asyncio

    from ai_agent.eval.harness import post_eval_runs, run_registry, to_payload

    results = run_registry(config, model_path=model_path or None)
    for metric in results:
        verdict = "PASS" if metric.met_threshold else "WARN"
        typer.echo(
            f"[{verdict}] {metric.model_name}:{metric.metric} "
            f"precision={metric.precision:.4f} "
            f"(considered={metric.considered}, abstained={metric.abstained}, "
            f"threshold={metric.threshold:.2f}, source={metric.model_source}, "
            f"version={metric.model_version})"
        )
    underperforming = [m for m in results if not m.met_threshold]
    for metric in underperforming:
        typer.echo(
            f"WARNING {metric.model_name}:{metric.metric} precision "
            f"{metric.precision:.4f} < {metric.threshold:.2f}",
            err=True,
        )

    if dry_run:
        typer.echo("dry-run: results not persisted")
        return
    if not (core_url and token and tenant_slug):
        typer.echo(
            "SKIPPED persistence: pass --core-url/--token/--tenant-slug "
            "(or SKYRICT_CORE_URL/TOKEN/TENANT_SLUG) to record results",
            err=True,
        )
        return

    rows = [to_payload(metric) for metric in results]
    try:
        asyncio.run(post_eval_runs(core_url, token, tenant_slug, rows))
    except Exception as exc:  # warn-not-fail: an eval is never a hard gate
        typer.echo(f"WARNING failed to persist eval results: {exc}", err=True)
        return
    typer.echo(f"recorded {len(rows)} eval metric(s) -> {core_url}")


if __name__ == "__main__":
    app()
