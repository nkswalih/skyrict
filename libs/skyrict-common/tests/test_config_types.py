"""`NonEmptyStr` must reject exactly what it claims to, and nothing more.

The bug this type exists to prevent was not a type error - it was a blank value
passing validation and detonating inside a third-party driver. So the tests
here are about which inputs survive the field, not about the field existing.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

# NonEmptyStr is a runtime type here: pydantic builds the field validator while
# creating the class, so moving it into a TYPE_CHECKING block would fail at
# import.
from skyrict_common.config_types import NonEmptyStr  # noqa: TC001


class _Model(BaseModel):
    url: NonEmptyStr


def test_a_real_url_passes_through_unchanged() -> None:
    # Guards against the constraint being written so tightly that it mangles
    # legitimate values. Nothing is rewritten but surrounding whitespace.
    assert _Model(url="rediss://:pw@host.cache.windows.net:6380/0").url == (
        "rediss://:pw@host.cache.windows.net:6380/0"
    )


def test_empty_string_is_rejected() -> None:
    # The case that reached redis-py and SQLAlchemy as a library error.
    with pytest.raises(ValidationError) as excinfo:
        _Model(url="")
    assert "url" in str(excinfo.value)


@pytest.mark.parametrize("blank", [" ", "\t", "\n", "   \r\n  "])
def test_whitespace_only_is_rejected(blank: str) -> None:
    # A shell exporting an unset variable under `set -u` can produce these, and
    # they are exactly as broken as "". Stripping before the length check is
    # what makes them fail here rather than at the driver.
    with pytest.raises(ValidationError):
        _Model(url=blank)


def test_surrounding_whitespace_is_stripped_not_rejected() -> None:
    # A trailing newline is a very common artefact of reading a value out of a
    # file. Rejecting it would be hostile; keeping it would break the URL.
    assert _Model(url="  redis://localhost:6379/0\n").url == "redis://localhost:6379/0"


def test_missing_is_still_rejected() -> None:
    # Orthogonal to emptiness: a field that is absent must still fail, so
    # NonEmptyStr can be combined with Field(...) without loosening anything.
    with pytest.raises(ValidationError):
        _Model()  # type: ignore[call-arg]


def test_the_type_does_not_opine_on_url_shape() -> None:
    # Deliberate: validity of the scheme/host is the driver's business, and a
    # shape check here would reject valid driver-specific forms and give a
    # misleading error about a setting that is in fact fine.
    assert _Model(url="not-a-url-at-all").url == "not-a-url-at-all"


def test_error_names_the_field_so_the_operator_knows_what_to_set() -> None:
    # The whole point of moving this check into settings. A driver error says
    # "must specify a scheme"; a field error says which variable is wrong.
    with pytest.raises(ValidationError) as excinfo:
        _Model(url="")
    message = str(excinfo.value)
    assert "url" in message
    assert "at least 1" in message or "greater than" in message
