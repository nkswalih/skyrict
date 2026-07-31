from __future__ import annotations

from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    SkyrictError,
    UserNotFoundError,
)


class TestSkyrictError:
    def test_default_message(self):
        err = SkyrictError()
        assert err.message == "An unexpected error occurred"
        assert err.code == "SKYRICT_ERROR"

    def test_custom_message(self):
        err = SkyrictError("something broke")
        assert err.message == "something broke"

    def test_custom_code(self):
        err = SkyrictError(code="CUSTOM_CODE")
        assert err.code == "CUSTOM_CODE"


class TestAuthenticationError:
    def test_defaults(self):
        err = AuthenticationError()
        assert err.message == "Authentication failed"
        assert err.code == "AUTHENTICATION_ERROR"


class TestAuthorizationError:
    def test_defaults(self):
        err = AuthorizationError()
        assert err.message == "You do not have permission to perform this action"
        assert err.code == "AUTHORIZATION_ERROR"


class TestInheritance:
    def test_subclass_of_skyrict_error(self):
        assert issubclass(UserNotFoundError, SkyrictError)

    def test_raised_and_caught(self):
        try:
            raise UserNotFoundError("alice@test.com")
        except SkyrictError as e:
            assert e.code == "USER_NOT_FOUND"
