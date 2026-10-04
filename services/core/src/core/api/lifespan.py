"""Application lifespan - startup verification and graceful shutdown.

Extracted from main.py for testability and separation of concerns.

Startup: configures structured logging and verifies every required dependency
ONCE (database, JWT public key) and refuses to boot on failure - the
orchestrator sees the non-zero exit and restarts the pod instead of serving
traffic with a dead dependency. The readiness gate only opens after
verification succeeds; ``GET /ready`` reports it (with lightweight live
probes) but never re-runs this verification.

Shutdown: closes the gate so probes drain the pod, then disposes the DB
engine.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from core.api import readiness
from core.core.config import Environment, settings
from core.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and graceful shutdown."""
    configure_logging(log_level=settings.LOG_LEVEL, json_output=settings.LOG_JSON)

    logger = get_logger("core.startup")
    logger.info(
        "service.starting",
        environment=settings.ENVIRONMENT.value,
        debug=settings.DEBUG,
        log_level=settings.LOG_LEVEL,
    )

    # Outbound HTTP client for /api/v1/ai/* proxying to the ai-agent
    # microservice - one pooled client for the process lifetime.
    app.state.ai_client = httpx.AsyncClient(
        base_url=settings.AI_AGENT_URL,
        timeout=settings.AI_AGENT_TIMEOUT_SECONDS,
    )

    # Startup verification - fail-fast: any failure raises StartupError and
    # the process exits immediately (orchestrator restarts the pod).
    await readiness.verify_startup_dependencies()

    # Sync user→role grants from identity's tables into core's RBAC tables.
    # Bridges the gap where identity's seed creates user_roles rows but
    # core's seed only creates the role catalog - never the user→role grants
    # that require_permission resolves through.
    from core.seed import sync_rbac_from_identity

    try:
        await sync_rbac_from_identity()
    except Exception:
        # Best-effort bootstrap sync: identity may be unready or unreachable at
        # boot, and a grants divergence must not take the monolith down. Any
        # failure (DB, network, seed mismatch) is logged; the grants reconcile
        # on the next startup and operators are alerted via logs.
        logger.warning("rbac_sync.failed", exc_info=True)

    readiness.mark_ready()
    logger.info("service.started", environment=settings.ENVIRONMENT.value)

    # Payroll automation worker (HR-AUT-001): a background asyncio loop that
    # drains the queue. Disabled under the test environment so integration
    # tests drive process_once() directly through POST /ai/payroll/tick.
    if settings.PAYROLL_AUTO_WORKER_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.payroll_automation.worker import PayrollAutomationWorker

        app.state.payroll_automation_worker = PayrollAutomationWorker(
            async_session_factory,
            poll_seconds=settings.PAYROLL_AUTO_POLL_SECONDS,
            max_retries=settings.PAYROLL_AUTO_MAX_RETRIES,
            items_per_tick=settings.PAYROLL_AUTO_ITEMS_PER_TICK,
        )
        app.state.payroll_automation_worker.start()
    else:
        app.state.payroll_automation_worker = None

    # Report snapshot retention worker (RPT-BE-001): a background asyncio loop
    # that prunes each definition's snapshots beyond REPORTING_RETENTION_LIMIT.
    # Disabled under the test environment so integration tests drive
    # process_all() directly (and via `core retention run`).
    if settings.REPORTING_RETENTION_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.reporting.retention_worker import SnapshotRetentionWorker

        app.state.reporting_retention_worker = SnapshotRetentionWorker(
            async_session_factory,
            poll_seconds=settings.REPORTING_RETENTION_POLL_SECONDS,
            keep_n=settings.REPORTING_RETENTION_LIMIT,
        )
        app.state.reporting_retention_worker.start()
    else:
        app.state.reporting_retention_worker = None

    # Approval SLA escalation worker (SKY-92): a background asyncio loop that
    # escalates overdue pending steps (nudge, never a decision). Disabled under
    # the test environment so integration tests drive process_all() directly
    # (and via `core approval-escalation run`).
    if settings.APPROVAL_ESCALATION_WORKER_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.approval_workflow.escalation_worker import (
            ApprovalEscalationWorker,
        )

        app.state.approval_escalation_worker = ApprovalEscalationWorker(
            async_session_factory,
            poll_seconds=settings.APPROVAL_ESCALATION_POLL_SECONDS,
            steps_per_pass=settings.APPROVAL_ESCALATION_STEPS_PER_PASS,
        )
        app.state.approval_escalation_worker.start()
    else:
        app.state.approval_escalation_worker = None

    # Notification batching worker (SKY-93): a background asyncio loop that
    # collapses bursts of low/medium notifications into digests. Disabled
    # under the test environment so integration tests drive process_all()
    # directly (and via `core notification batch`).
    if settings.NOTIF_BATCH_WORKER_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.notifications.worker import NotificationBatchingWorker

        app.state.notification_batching_worker = NotificationBatchingWorker(
            async_session_factory,
        )
        app.state.notification_batching_worker.start()
    else:
        app.state.notification_batching_worker = None

    # Budget overrun notification worker (SKY-85): a background asyncio loop
    # that emits a notification per active-budget line whose posted activity
    # exceeds its plan. Disabled under the test environment so integration
    # tests drive process_all() directly (and via `core budget-overrun run`).
    if settings.FINANCE_BUDGET_OVERRUN_WORKER_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.finance.budget_overrun_worker import BudgetOverrunWorker

        app.state.budget_overrun_worker = BudgetOverrunWorker(
            async_session_factory,
            poll_seconds=settings.FINANCE_BUDGET_OVERRUN_POLL_SECONDS,
        )
        app.state.budget_overrun_worker.start()
    else:
        app.state.budget_overrun_worker = None

    # RBAC projection reconciler (SKY-120): a background asyncio loop that
    # projects identity's grants into core's RBAC tables for tenants that have
    # none. Closes the window where a self-service signup tenant exists with
    # identity grants but no core projection, which 403'd its owner on every
    # permission check until core happened to restart. Disabled under the test
    # environment so integration tests drive run_once() directly.
    if settings.RBAC_PROJECTION_ENABLED and settings.ENVIRONMENT != Environment.TEST:
        from core.db.session import async_session_factory
        from core.features.rbac.projection_worker import RbacProjectionReconciler

        app.state.rbac_projection_reconciler = RbacProjectionReconciler(async_session_factory)
        app.state.rbac_projection_reconciler.start()
    else:
        app.state.rbac_projection_reconciler = None

    # Graceful shutdown: uvicorn owns SIGTERM/SIGINT handling; on signal it
    # runs this context manager's exit, closing the readiness gate, the AI
    # client and the DB engine so in-flight work can drain cleanly.
    yield

    readiness.mark_stopping()
    logger.info("service.stopping", environment=settings.ENVIRONMENT.value)

    from core.db.session import engine

    worker = getattr(app.state, "payroll_automation_worker", None)
    if worker is not None:
        await worker.stop()
    retention_worker = getattr(app.state, "reporting_retention_worker", None)
    if retention_worker is not None:
        await retention_worker.stop()
    escalation_worker = getattr(app.state, "approval_escalation_worker", None)
    if escalation_worker is not None:
        await escalation_worker.stop()
    batch_worker = getattr(app.state, "notification_batching_worker", None)
    if batch_worker is not None:
        await batch_worker.stop()
    budget_overrun_worker = getattr(app.state, "budget_overrun_worker", None)
    if budget_overrun_worker is not None:
        await budget_overrun_worker.stop()
    projection_reconciler = getattr(app.state, "rbac_projection_reconciler", None)
    if projection_reconciler is not None:
        await projection_reconciler.stop()
    await app.state.ai_client.aclose()
    await engine.dispose()
