"""Typer CLI for the AI agent service."""

from __future__ import annotations

import asyncio
import uuid
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
        ["alembic", "-c", str(_PACKAGE_ROOT / "alembic.ini"), "upgrade", head],
        cwd=_PACKAGE_ROOT,
        check=True,
    )


@app.command()
def digest(
    tenant_id: str = typer.Option(..., help="Target tenant UUID"),
    tenant_slug: str = typer.Option(..., help="Target tenant slug"),
) -> None:
    """Produce and print today's cross-module narrated digest for one tenant."""

    async def _run() -> None:
        from datetime import UTC, datetime

        from ai_agent.core.audit_service import AuditService
        from ai_agent.core.config import settings
        from ai_agent.core.llm_router import LlmRouter
        from ai_agent.core.providers import build_providers_from_settings
        from ai_agent.db.audit_repository import AiAuditLogRepository
        from ai_agent.db.digest_repository import DigestCacheRepository
        from ai_agent.db.session import async_session_factory
        from ai_agent.features.narrator.gateway import HttpCoreGateway
        from ai_agent.features.narrator.service import NarratorService

        llm_router = LlmRouter(build_providers_from_settings(settings))
        async with async_session_factory() as session:
            service = NarratorService(
                gateway=HttpCoreGateway(
                    base_url=str(settings.INVENTORY_SERVICE_URL),
                    bearer_token="",  # nosec B106 - CLI one-shot; token lands with tenant provider
                    tenant_slug=tenant_slug,
                ),
                llm_router=llm_router,
                cache=DigestCacheRepository(session),
                audit=AuditService(AiAuditLogRepository(session)),
                allow_llm=settings.NARRATOR_ALLOW_LLM,
                allow_refresh=True,
            )
            result = await service.digest(
                tenant_id=uuid.UUID(tenant_id),
                user_id=None,
                as_of=datetime.now(tz=UTC).date(),
                force_refresh=True,
            )
            await session.commit()
        typer.echo(f"status={result.status} source={result.source}")
        if result.title:
            typer.echo(result.title)
        if result.summary:
            typer.echo(result.summary)
        for point in result.points:
            typer.echo(f"- {point}")
        if result.caveat:
            typer.echo(result.caveat)

    asyncio.run(_run())


@app.command()
def ingest(
    source: str = typer.Option(
        "docs", help="source: 'docs' (markdown dir) or 'module' (core data)"
    ),
    module: str = typer.Option("docs", help="module name ('docs' or e.g. 'products')"),
    tenant: str = typer.Option(..., help="tenant slug (required)"),
    path: Path | None = None,
    mode: str = typer.Option(
        "incremental", help="'incremental' or 'full' (both replace idempotently)"
    ),
) -> None:
    """Ingest documents into the RAG vector store (SKY-58).

    --path: markdown directory root when --source=docs. Re-running a document
    is always safe (both modes replace idempotently).

    Requires an embedding provider: AI_EMBEDDING_PROVIDER + AI_EMBEDDING_API_KEY.
    """
    import asyncio

    from ai_agent.ingest import run_ingest

    asyncio.run(run_ingest(source=source, module=module, tenant=tenant, path=path, mode=mode))


@app.command(name="eval")
def evaluate(
    tenant: str = typer.Option(..., help="tenant slug or UUID (required)"),
    module: str | None = typer.Option(
        None, help="restrict eval cases to one module ('docs' or 'products')"
    ),
    faithfulness: float = typer.Option(0.80, min=0.0, max=1.0, help="minimum faithfulness"),
    answer_relevancy: float = typer.Option(0.75, min=0.0, max=1.0, help="minimum answer relevancy"),
    context_precision: float = typer.Option(
        0.70, min=0.0, max=1.0, help="minimum context precision"
    ),
    context_recall: float = typer.Option(0.70, min=0.0, max=1.0, help="minimum context recall"),
) -> None:
    """Run the nightly RAGAS retrieval-quality gate (SKY-58).

    Runs every curated eval case through the REAL retrieval pipeline, scores
    the pairs with RAGAS, persists the run to ai_eval_runs, and exits nonzero
    when any metric drops below its threshold (CI gate).

    Requires ragas (nightly workflow installs it ephemerally):
    uv run --with "ragas>=0.2,<0.3" ai-agent eval --tenant <slug|uuid>
    """
    import asyncio

    from ai_agent.rag_eval import run_eval

    thresholds = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    outcome = asyncio.run(run_eval(tenant=tenant, module=module, thresholds=thresholds))
    means = ", ".join(f"{name}={value:.4f}" for name, value in sorted(outcome.means.items()))
    status = "PASS" if outcome.passed else f"FAIL: below threshold - {', '.join(outcome.failures)}"
    typer.echo(f"RAGAS run {outcome.run_id}: {outcome.sample_count} sample(s) - {means} - {status}")
    if not outcome.passed:
        raise typer.Exit(1)


@app.command()
def sweep_caches() -> None:
    """Purge expired ai_query_cache rows for every tenant (SKY-58)."""
    import asyncio

    from ai_agent.sweep import sweep_expired_query_cache

    deleted = asyncio.run(sweep_expired_query_cache())
    typer.echo(f"Deleted {deleted} expired query cache row(s).")


inventory_app = typer.Typer(
    name="inventory",
    help="Inventory semantic snapshot maintenance (SKY-70).",
    no_args_is_help=True,
)


@inventory_app.command("reindex")
def inventory_reindex(
    tenant: str = typer.Option(..., help="tenant slug or UUID (required)"),
    mode: str = typer.Option(
        "full", help="'full' wipes then rebuilds; 'incremental' only upserts the fetched catalog"
    ),
) -> None:
    """Rebuild one tenant's product embedding snapshot (SKY-70).

    Pulls the current catalog from core and (re)embeds every product into
    ai_inv_item_embeddings. ``full`` clears the tenant's snapshot first so
    deactivated-or-removed products disappear from semantic search.

    Requires an embedding provider (AI_EMBEDDING_PROVIDER + key) and
    AI_INGEST_TOKEN for the core pull.
    """
    import asyncio

    from ai_agent.inventory_reindex import run_inventory_reindex

    asyncio.run(run_inventory_reindex(tenant=tenant, mode=mode))


app.add_typer(inventory_app)


finance_app = typer.Typer(
    name="finance",
    help="Finance invoice-line embedding snapshot (SKY-67 C1).",
    no_args_is_help=True,
)


@finance_app.command("reindex")
def finance_reindex(
    tenant: str = typer.Option(..., help="tenant slug or UUID (required)"),
    mode: str = typer.Option(
        "full", help="'full' wipes then rebuilds; 'incremental' only upserts the fetched lines"
    ),
) -> None:
    """Rebuild one tenant's invoice-line embedding snapshot (SKY-67 C1).

    Pulls invoice line history from the core monolith (AI_INGEST_TOKEN) and
    stores one embedding per distinct line description, enabling "sensible
    line suggestions" in the invoice form. Never writes invoices itself.
    """
    import asyncio

    from ai_agent.finance_reindex import run_finance_reindex

    asyncio.run(run_finance_reindex(tenant=tenant, mode=mode))


app.add_typer(finance_app)


supplier_risk_app = typer.Typer(
    name="supplier-risk",
    help="Supplier risk grading maintenance (SKY-86 / INV-AI-004).",
    no_args_is_help=True,
)


@supplier_risk_app.command("reindex")
def supplier_risk_reindex(
    tenant: str = typer.Option(..., help="tenant slug or UUID (required)"),
) -> None:
    """Rebuild one tenant's supplier risk grades (SKY-86 / INV-AI-004).

    Pulls the current supplier catalog + grading-period facts from core and
    recomputes the deterministic risk score/band for every supplier into
    ai_supplier_risk. The band feeds the v2 restock lead-time adjustment.

    Requires AI_INGEST_TOKEN for the core pull.
    """
    import asyncio

    from ai_agent.supplier_risk_reindex import run_supplier_risk_reindex

    asyncio.run(run_supplier_risk_reindex(tenant=tenant))


app.add_typer(supplier_risk_app)


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


@app.command()
def eval_finance(
    config: str = typer.Option(
        str(_PACKAGE_ROOT / "tests" / "eval" / "finance_prompts.yaml"),
        "--config",
        help="path to the finance prompt eval registry (YAML)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="compute + print only; do not persist ai_finance_eval_runs"
    ),
) -> None:
    """Evaluate the finance AI prompts against the labeled seed set (FIN-AI-002).

    Drives every case in ``tests/eval/finance_prompts.yaml`` through the REAL
    production prompt functions (a1_suggest / a2_draft / a7_narrate / a8_remind)
    and prints one line per feature. WARNS (never fails) when precision drops
    below the registry threshold, and persists a row per feature to
    ``ai_finance_eval_runs`` for the historical record.
    """
    import asyncio

    from ai_agent.core.config import settings
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.core.providers import build_providers_from_settings
    from ai_agent.features.finance_eval.harness import persist_metrics, run_registry

    llm_router = LlmRouter(build_providers_from_settings(settings))
    metrics = asyncio.run(run_registry(config, llm_router))
    for metric in metrics:
        verdict = "PASS" if metric.met_threshold else "WARN"
        typer.echo(
            f"[{verdict}] {metric.feature} precision={metric.precision:.4f} "
            f"(considered={metric.considered}, abstained={metric.abstained}, "
            f"threshold={metric.threshold:.2f}, model={metric.model_used or 'none'})"
        )
    underperforming = [m for m in metrics if not m.met_threshold]
    for metric in underperforming:
        typer.echo(
            f"WARNING {metric.feature} precision {metric.precision:.4f} < {metric.threshold:.2f}",
            err=True,
        )

    if dry_run:
        typer.echo("dry-run: results not persisted")
        return
    try:
        ids = asyncio.run(persist_metrics(metrics))
    except Exception as exc:  # warn-not-fail: an eval is never a hard gate
        typer.echo(f"WARNING failed to persist finance eval results: {exc}", err=True)
        return
    typer.echo(f"recorded {len(ids)} finance eval metric(s) -> ai_finance_eval_runs")


@app.command()
def documents_reindex(
    tenant_id: str = typer.Option(..., help="Target tenant UUID"),
    tenant_slug: str = typer.Option(..., help="Target tenant slug"),
    ocr_status: str = typer.Option(
        "failed", help="Re-process documents in this status: 'failed' or 'ready'"
    ),
    limit: int = typer.Option(50, help="Max documents to re-process"),
) -> None:
    """Re-process previously failed (or ready) documents' OCR/tag/embed (SKY-87).

    Fetches core documents with the given ocr_status and runs the same
    DocumentOcrService each one would get from the m2m /process endpoint.
    """
    if ocr_status not in ("failed", "ready"):
        typer.echo("--ocr-status must be 'failed' or 'ready'", err=True)
        raise typer.Exit(code=2)

    async def _run() -> None:
        from ai_agent.core.config import settings
        from ai_agent.core.llm_router import LlmRouter
        from ai_agent.core.providers import build_providers_from_settings
        from ai_agent.db.document_embedding_repository import DocumentEmbeddingRepository
        from ai_agent.db.session import async_session_factory
        from ai_agent.features.documents.gateway import HttpDocumentGateway
        from ai_agent.features.documents.service import DocumentOcrService

        llm_router = LlmRouter(build_providers_from_settings(settings))
        gateway = HttpDocumentGateway()
        docs = await gateway.list_documents_for_reindex(
            tenant_slug, ocr_status=ocr_status, limit=limit
        )
        typer.echo(f"found {len(docs)} document(s) with ocr_status='{ocr_status}'")
        async with async_session_factory() as session:
            store = DocumentEmbeddingRepository(session)
            service = DocumentOcrService(
                store=store,
                gateway=gateway,
                llm_router=llm_router,
            )
            for doc in docs:
                result = await service.process(
                    tenant_id=uuid.UUID(tenant_id),
                    tenant_slug=tenant_slug,
                    document_id=doc.document_id,
                )
                await session.commit()
                typer.echo(
                    f"- {doc.document_id} -> {result.ocr_status}"
                    + (f" (tags={len(result.ai_tags)})" if result.ai_tags else "")
                )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
