"""Permission enforcement for agent tool invocation (SKY-59).

The runtime resolves a caller's grants from ``core_roles``/``core_user_roles``
(shared-database read-only projections, see ``db/permission_repository.py``)
and refuses any tool whose required key is not granted. This mirrors the core
monolith's ``RbacRepository`` semantics exactly: the wildcard ``"*"`` (tenant
owner) satisfies every key, otherwise an exact match is required - and it fails
closed.

The keys ARE the cross-service contract: they must equal the strings core seeds
into ``core_roles.permissions``
(``services/core/src/core/core/permissions.py``). The ai-agent runtime holds
its own copies deliberately - permission strings travel as plain values and
there is no shared library between the two services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Tenant-owner wildcard grant - must match core.core.permissions.WILDCARD.
WILDCARD = "*"

# ERP permission keys the runtime checks (mirrors the core catalog).
PERM_AI_INVOKE = "erp.ai.invoke"
PERM_INVENTORY_READ = "erp.inventory.read"
PERM_INVENTORY_AI_APPROVE = "erp.inventory.ai.approve"
PERM_FINANCE_WRITE = "erp.finance.write"
PERM_CRM_READ = "erp.crm.read"
PERM_CRM_COACHING_APPROVE = "erp.crm.coaching.approve"


def grants_permission(granted: Iterable[str], required: str) -> bool:
    """True when *granted* satisfies *required* (wildcard-aware, fail-closed).

    The wildcard ``"*"`` (owner role) grants every catalogued permission;
    otherwise an exact key match is required. Fails closed: no match -> False.
    """
    keys = set(granted)
    return WILDCARD in keys or required in keys
