"""Alembic env.py — async migration runner for the core service.

CRITICAL: core shares the ``skyrict_identity`` Postgres database with the
identity service, so it MUST migrate under its own Alembic version table
(``alembic_version_core``). Both ``run_migrations_offline`` and
``run_migrations_online`` pass ``version_table="alembic_version_core"`` to
``context.configure``; without this, the two services would clobber each
other's migration bookkeeping in the single database.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

from core.core.config import settings

# Feature ORM models — imported for autogenerate/``target_metadata`` so the full
# schema is reflected. Models share the same ``core.models.base`` Base; import
# order matters only for FK resolution (models use string table refs, so none).
from core.features.ai_hr.models import (  # noqa: F401
    AttritionScoreModel,
    ComplianceCheckModel,
    EmployeeDocumentModel,
    HrEvalRunModel,
    LeaveAnomalyModel,
    LeaveSuggestionModel,
    PayrollAnomalyModel,
    QualityScoreModel,
    UtilizationAlertModel,
)
from core.features.crm.models import (  # noqa: F401
    ErpCrmCustomerModel,
    ErpCrmLeadModel,
    ErpCrmOpportunityModel,
)
from core.features.finance.models import (  # noqa: F401
    ErpChartOfAccountModel,
    ErpFiscalPeriodModel,
    ErpInvoiceLineModel,
    ErpInvoiceModel,
    ErpJournalEntryModel,
    ErpJournalLineModel,
    ErpPaymentModel,
)
from core.features.hr.models import (  # noqa: F401
    DepartmentModel,
    EmployeeModel,
    LeaveBalanceModel,
    LeaveMovementModel,
    LeaveRequestModel,
    LeaveTypeModel,
)
from core.features.inventory.models.product import ErpProductModel  # noqa: F401
from core.features.inventory.models.stock_level import ErpStockLevelModel  # noqa: F401
from core.features.inventory.models.stock_movement import ErpStockMovementModel  # noqa: F401
from core.features.inventory.models.warehouse import ErpWarehouseModel  # noqa: F401
from core.features.payroll.models import (  # noqa: F401
    CompensationModel,
    PayrollEntryModel,
    PayrollRunModel,
    PayrollSettingsModel,
)
from core.features.sales.models import (  # noqa: F401
    ErpSalesOrderLineModel,
    ErpSalesOrderModel,
)
from core.models import (  # noqa: F401  # registers every ORM model
    CorePermissionModel,
    CoreRoleModel,
    CoreUserRoleModel,
    ErpCurrencyModel,
    TenantModel,
)
from core.models.base import Base

config = context.config
# Escape "%" so configparser interpolation does not choke on URL-encoded
# credentials (e.g. "%40" in a password); get_main_option restores the "%".
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Core migrates the SHARED skyrict_identity database under its own Alembic
# version table so identity and core never clobber each other's bookkeeping.
VERSION_TABLE = "alembic_version_core"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generate SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode — connect to the database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
