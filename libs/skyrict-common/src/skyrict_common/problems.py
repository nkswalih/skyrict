"""RFC 7807 problem-type URIs - the public error contract.

The ``type`` member of an ``application/problem+json`` body is a stable public
identifier. Clients branch on it, so unlike the ``title``/``detail`` members it
must not change casually, and every service that emits problems must agree on
it.

That agreement used to be maintained by hand. Each of identity, core, ai-agent
and the service template defined its own ``PROBLEM_BASE_URL`` literal *and* a
second one in its own ``exceptions.py``, plus a family of derived
``PROBLEM_*`` constants that nothing outside the file ever read. The public
domain then moved three times - ``.com`` to ``.io`` to ``.in`` - and only the
first was caught by review. Two of the three are visible in the recorded audit
(``docs/runbooks/pre-release-audit-2026-09.md``, finding 16): the services
emitted ``api.skyrict.io`` while the deployed host was ``api.skyrict.in``, and
the Next.js invite page compared against a third hardcoded copy of the same
string in a different language.

One literal, in the shared library every service already depends on, is the
fix. The per-service ``PROBLEM_*`` constants were deleted rather than
re-pointed: they were a second, unused copy of the same contract, and keeping
them would preserve the exact failure mode.

This is deliberately a constant and not configuration. A per-environment
``PROBLEM_BASE_URL`` would let the published error contract drift between
staging and production, which is worse than a value that requires a code change
to get wrong.
"""

from __future__ import annotations

from typing import Final

PROBLEM_BASE_URL: Final[str] = "https://api.skyrict.in/problems"

__all__ = ["PROBLEM_BASE_URL"]
