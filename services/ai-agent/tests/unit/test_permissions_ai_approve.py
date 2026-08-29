"""Tests for erp.inventory.ai.approve permission constant existence.

Core permission tests are skipped in ai-agent unit context because core's
``__init__.py`` eagerly instantiates ``Settings()`` which requires env vars
not available here. Identity module-level constants are readable directly.
"""

from __future__ import annotations


class TestAiApprovePermission:
    def test_identity_permissions_has_constant(self) -> None:
        from identity.core.permissions import ERP_INVENTORY_AI_APPROVE

        assert ERP_INVENTORY_AI_APPROVE == "erp.inventory.ai.approve"

    def test_identity_org_admin_grants_ai_approve(self) -> None:
        from identity.core.constants import SYSTEM_ROLE_DEFINITIONS

        org_admin_perms = next(
            perms for name, perms in SYSTEM_ROLE_DEFINITIONS if name == "organization_admin"
        )
        assert "erp.inventory.ai.approve" in org_admin_perms

    def test_identity_dept_manager_grants_ai_approve(self) -> None:
        from identity.core.constants import SYSTEM_ROLE_DEFINITIONS

        dept_mgr_perms = next(
            perms for name, perms in SYSTEM_ROLE_DEFINITIONS if name == "department_manager"
        )
        assert "erp.inventory.ai.approve" in dept_mgr_perms
