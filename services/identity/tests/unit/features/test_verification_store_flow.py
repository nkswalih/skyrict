"""Unit tests for the signup flow proof's Redis primitives.

The service tests drive these through a hand-written double, which cannot catch
a mistake in how the real client is actually called - a non-transactional
pipeline, a counter read as zero, a TTL that refreshes itself. Those are the
failure modes this file exists for, so it drives a small in-memory client that
records the commands the store issues.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from identity.core.config import settings
from identity.features.auth.verification_store import (
    VerificationStore,
    generate_signup_flow_token,
)


class FakePipeline:
    """Records the commands a transaction is meant to apply atomically."""

    def __init__(self, client: FakeRedis, transaction: bool) -> None:
        self._client = client
        self._transaction = transaction
        self._queued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._queued.append(("set", (key, value), {"ex": ex}))

    async def __aenter__(self) -> FakePipeline:
        self._client.pipeline_calls.append(self._transaction)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def execute(self) -> list[Any]:
        if not self._transaction:
            # A non-transactional pipeline applies each command as it arrives and
            # has no all-or-nothing to lose, so a fault between them is not a
            # thing this branch can express. `fail_on` is a transactional-only
            # fault; the half-written state it would produce is asserted on
            # directly by test_a_proof_missing_its_budget_is_refused instead.
            for cmd, args, kwargs in self._queued:
                self._client.apply(cmd, args, kwargs)
            return []
        # A connection lost before EXEC applies none of them. Both commands are
        # well-formed SETs of a string with a TTL, so a per-command error is not
        # reachable here - the realistic fault is the connection.
        if self._client.fail_on is not None and any(
            self._client.fail_on in str(arg) for _cmd, args, _kwargs in self._queued for arg in args
        ):
            raise RuntimeError("connection lost before EXEC")
        return [self._client.apply(cmd, args, kwargs) for cmd, args, kwargs in self._queued]


class FakeRedis:
    """The slice of Redis the verification store uses."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.pipeline_calls: list[bool] = []
        # Every command the store issues, so a test can assert on the shape of
        # the traffic and not just its effect.
        self.commands: list[str] = []
        # Set to a key fragment to make the next transactional pipeline abort,
        # standing in for a connection lost mid-write.
        self.fail_on: str | None = None

    def apply(self, cmd: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if cmd == "set":
            key, value = str(args[0]), str(args[1])
            self.values[key] = value
            ex = kwargs.get("ex")
            self.expiries[key] = int(ex) if ex is not None else -1
            return True
        raise AssertionError(f"unexpected command {cmd}")

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self, transaction)

    async def get(self, key: str) -> str | None:
        self.commands.append(f"get {key}")
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        self.commands.append(f"incr {key}")
        count = int(self.values.get(key, "0")) + 1
        self.values[key] = str(count)
        return count

    async def ttl(self, key: str) -> int:
        self.commands.append(f"ttl {key}")
        return self.expiries.get(key, -2)

    async def expire(self, key: str, seconds: int) -> bool:
        self.commands.append(f"expire {key}")
        self.expiries[key] = seconds
        return True


@pytest.fixture
def client() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def store(client: FakeRedis) -> VerificationStore:
    return VerificationStore(client=client)  # type: ignore[arg-type]


class TestSetSignupFlow:
    async def test_writes_the_proof_and_its_budget(self, store: VerificationStore) -> None:
        await store.set_signup_flow("tok", "owner@neworg.com")

        assert await store.get_signup_flow("tok") == "owner@neworg.com"

    async def test_both_keys_carry_the_flow_ttl(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """A budget outliving its proof, or the reverse, is a hole either way."""
        await store.set_signup_flow("tok", "owner@neworg.com")

        ttls = set(client.expiries.values())
        assert ttls == {settings.SIGNUP_FLOW_TTL_SECONDS}
        assert len(client.expiries) == 2

    async def test_the_two_writes_are_one_transaction(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """A proof without a budget reads as unlimited, so they must not split.

        The pipeline was asked to be transactional, which is what decides whether
        a fault between the two leaves half a flow behind. `FakeRedis` has no
        `set` at all, so the pair also cannot have been written as bare commands -
        that is what the fake enforces, not an assertion here. The next test is
        the one that actually demonstrates the transaction pays off.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")

        assert client.pipeline_calls == [True]

    async def test_a_failed_write_leaves_no_usable_proof(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """Half a flow is not a flow. A lost write must refuse, not allow."""
        client.fail_on = "owner@neworg.com"

        with pytest.raises(RuntimeError):
            await store.set_signup_flow("tok", "owner@neworg.com")

        assert await store.get_signup_flow("tok") is None


class TestGetSignupFlow:
    async def test_returns_the_address_it_was_solved_for(self, store: VerificationStore) -> None:
        await store.set_signup_flow("tok", "owner@neworg.com")

        assert await store.get_signup_flow("tok") == "owner@neworg.com"

    async def test_unknown_proof_is_none(self, store: VerificationStore) -> None:
        assert await store.get_signup_flow("never-issued") is None

    async def test_a_proof_missing_its_budget_is_refused(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """Fail closed.

        The counter is what caps sends. If it is gone, the proof must be
        unusable - reading it as zero would make the proof unlimited for the rest
        of its TTL, which is the wrong way round for an abuse control.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.values.pop("signup_flow_sends:tok")

        assert await store.get_signup_flow("tok") is None

    async def test_a_proof_missing_its_address_is_refused(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.values["signup_flow:tok"] = json.dumps({"address": "owner@neworg.com"})

        assert await store.get_signup_flow("tok") is None

    @pytest.mark.parametrize("raw", ["", "not json", "[]", '"a string"', "null"])
    async def test_unreadable_payloads_are_refused(
        self, store: VerificationStore, client: FakeRedis, raw: str
    ) -> None:
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.values["signup_flow:tok"] = raw

        assert await store.get_signup_flow("tok") is None


class TestConsumeSignupFlowSend:
    async def test_counts_up_from_zero(self, store: VerificationStore) -> None:
        await store.set_signup_flow("tok", "owner@neworg.com")

        assert [await store.consume_signup_flow_send("tok") for _ in range(3)] == [1, 2, 3]

    async def test_one_charge_is_one_incr(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """The count is settled by Redis, so it has to be read-modify-written there.

        A GET followed by a computed SET is the race this design exists to
        avoid. Asserting on the commands rather than the result catches that even
        though this fake cannot interleave - it is the shape of the traffic that
        gives INCR its atomicity, and Redis is what supplies the guarantee.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.commands.clear()

        await store.consume_signup_flow_send("tok")

        reads = [c for c in client.commands if c.startswith("get ")]
        assert reads == []
        assert [c for c in client.commands if c.startswith("incr ")] == [
            "incr signup_flow_sends:tok"
        ]

    async def test_concurrent_charges_never_return_the_same_count(
        self, store: VerificationStore
    ) -> None:
        """The returned count is the decision, so it has to be unique per charge.

        The caller branches on this value to decide whether the send may proceed.
        If two charges could return the same number, two sends would both be
        admitted against one budget slot. The uniqueness comes from Redis - see
        `test_one_charge_is_one_incr` for the part this side is responsible for.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")

        counts = await asyncio.gather(*(store.consume_signup_flow_send("tok") for _ in range(8)))

        assert sorted(counts) == list(range(1, 9))

    async def test_does_not_extend_the_window(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """Sending must not buy more time.

        A refreshed TTL would let a caller that keeps sending hold a proof open
        indefinitely, which turns a bounded window into an unbounded one.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.expiries["signup_flow_sends:tok"] = 120

        await store.consume_signup_flow_send("tok")

        assert client.expiries["signup_flow_sends:tok"] == 120

    async def test_restores_a_ttl_on_a_counter_that_lost_one(
        self, store: VerificationStore, client: FakeRedis
    ) -> None:
        """A counter Redis knows nothing about must not live forever.

        INCR creates the key with no TTL. Left that way it outlives the proof and
        the next proof that somehow reused the token would inherit a stale count
        or none at all.
        """
        await store.set_signup_flow("tok", "owner@neworg.com")
        client.values.pop("signup_flow_sends:tok")
        client.expiries.pop("signup_flow_sends:tok", None)

        assert await store.consume_signup_flow_send("tok") == 1
        assert client.expiries["signup_flow_sends:tok"] == settings.SIGNUP_FLOW_TTL_SECONDS


def test_generated_proofs_do_not_repeat() -> None:
    """Two proofs must never collide, or one user spends another's budget.

    That is the only property here this side owns: unpredictability and the
    URL-safe alphabet are `secrets.token_urlsafe(32)`'s contract, not something a
    test here can establish. Sampling 200 from 2**256 cannot demonstrate it, and
    does not pretend to - it only catches a generator that repeats itself.
    """
    tokens = {generate_signup_flow_token() for _ in range(200)}

    assert len(tokens) == 200
