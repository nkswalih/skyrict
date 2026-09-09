"""The L3 /refresh service gate honours the deployment flag (HR-AI-003).

Authorization for refresh lives at the core edge (erp.hr.ai.management +
erp.ai.l3.refresh). These tests pin the service-level second gate: the
L3 router must refuse to honour force-refresh when ``L3_ALLOW_REFRESH`` is
off, rather than hard-coding a True that makes the guard un-testable.
"""

from __future__ import annotations

from ai_agent.api.v1.routers import l3 as l3_router


class TestL3RefreshFlag:
    def test_refresh_allowed_by_default(self) -> None:
        assert l3_router._get_refresh_allowed() is True

    def test_refresh_denied_when_flag_disabled(self, monkeypatch) -> None:
        monkeypatch.setattr(l3_router.settings, "L3_ALLOW_REFRESH", False)
        assert l3_router._get_refresh_allowed() is False