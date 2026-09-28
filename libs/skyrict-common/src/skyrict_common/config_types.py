"""Pydantic field types shared by more than one service's settings.

These exist because `Field(...)` does **not** mean "must have a value" in
Pydantic. It means "must be *present*", and an environment variable that is set
to the empty string is very much present. Every deployment that builds a
connection URL from a parameter default can therefore hand the process `''` and
have it accepted:

    IDENTITY_REDIS_URL=     ->  Settings() validates
                            ->  redis.asyncio.Redis.from_url('') raises
                                ValueError: Redis URL must specify one of the
                                following schemes
                            ->  the container crash-loops, and the only error
                                in the logs names a redis-py scheme rather than
                                the IaC parameter that was left empty.

    IDENTITY_DATABASE_URL= ->  Settings() validates
                            ->  SQLAlchemy raises
                                ArgumentError: Could not parse SQLAlchemy URL

The container restart *is* a hard stop, so nothing runs half-configured - but
the failure surfaces as an opaque library error in pod logs, minutes after a
green pipeline run. Moving the check to settings turns it into a named
validation error at startup that points at the actual variable.

`NonEmptyStr` is deliberately about emptiness only. It does not validate that
the value is a well-formed URL or a reachable host: that is the driver's job,
and guessing at a URL's shape here would reject valid driver-specific forms.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

__all__ = ["NonEmptyStr"]

#: A required string that is not blank. Whitespace is stripped before the
#: length check, so a value of ``"   "`` is rejected too - a shell that exports
#: an unset variable under `set -u` can produce one, and it is just as broken
#: as `''`.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
