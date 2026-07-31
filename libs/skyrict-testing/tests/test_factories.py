from __future__ import annotations

from skyrict_testing.factories import SessionFactory, TenantFactory, UserFactory


class TestTenantFactory:
    def test_defaults(self):
        tenant = TenantFactory()
        assert tenant["is_active"] is True
        assert tenant["name"].startswith("Test Org")
        assert "id" in tenant


class TestUserFactory:
    def test_defaults(self):
        user = UserFactory()
        assert user["is_active"] is True
        assert user["email"].endswith("@test.skyrict.io")
        assert "id" in user


class TestSessionFactory:
    def test_defaults(self):
        session = SessionFactory()
        assert session["is_active"] is True
        assert session["ip_address"] == "127.0.0.1"
