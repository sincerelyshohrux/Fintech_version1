"""Bank API adapter.

In production this interface connects to the partner bank's API or an open-banking gateway.
For the prototype, MockBank simulates latency and occasional failures.
"""
import asyncio
import random
import uuid
from abc import ABC, abstractmethod

from app.config import settings


class BankError(Exception):
    pass


class BankAPI(ABC):
    @abstractmethod
    async def open_deposit(self, account_id: str, instrument_id: str, amount: int, return_date: str) -> dict: ...

    @abstractmethod
    async def close_deposit(self, deposit_ref: str) -> dict: ...

    @abstractmethod
    async def set_card_merchant_limit(self, card_last4: str, merchant: str, monthly_limit: int) -> dict: ...

    @abstractmethod
    async def remove_card_merchant_limit(self, limit_ref: str) -> dict: ...

    @abstractmethod
    async def block_merchant(self, card_last4: str, merchant: str) -> dict: ...

    @abstractmethod
    async def unblock_merchant(self, block_ref: str) -> dict: ...

    @abstractmethod
    async def create_standing_order(self, from_account: str, to_account: str, amount: int, day: int) -> dict: ...

    @abstractmethod
    async def prepay_loan(self, loan_id: str, amount: int) -> dict: ...

    @abstractmethod
    async def get_transactions(self, account_id: str, days: int) -> list[dict]: ...


class MockBank(BankAPI):
    def __init__(self, failure_rate: float | None = None, rng: random.Random | None = None):
        self.failure_rate = settings.mock_bank_failure_rate if failure_rate is None else failure_rate
        self.rng = rng or random.Random()

    async def _call(self, op: str, **data) -> dict:
        await asyncio.sleep(self.rng.uniform(0.3, 0.8))
        if self.rng.random() < self.failure_rate:
            raise BankError(f"Bank javob bermadi ({op})")
        return {"ref": f"{op[:3].upper()}-{uuid.uuid4().hex[:8].upper()}", "op": op, **data}

    async def open_deposit(self, account_id, instrument_id, amount, return_date):
        return await self._call("open_deposit", account_id=account_id, instrument_id=instrument_id,
                                amount=amount, auto_return_date=return_date)

    async def close_deposit(self, deposit_ref):
        return await self._call("close_deposit", deposit_ref=deposit_ref)

    async def set_card_merchant_limit(self, card_last4, merchant, monthly_limit):
        return await self._call("set_limit", card_last4=card_last4, merchant=merchant, monthly_limit=monthly_limit)

    async def remove_card_merchant_limit(self, limit_ref):
        return await self._call("remove_limit", limit_ref=limit_ref)

    async def block_merchant(self, card_last4, merchant):
        return await self._call("block_merchant", card_last4=card_last4, merchant=merchant)

    async def unblock_merchant(self, block_ref):
        return await self._call("unblock_merchant", block_ref=block_ref)

    async def create_standing_order(self, from_account, to_account, amount, day):
        return await self._call("standing_order", from_account=from_account, to_account=to_account,
                                amount=amount, day=day)

    async def prepay_loan(self, loan_id, amount):
        return await self._call("prepay_loan", loan_id=loan_id, amount=amount)

    async def get_transactions(self, account_id, days):
        await asyncio.sleep(0.2)
        return []


async def with_retry(fn, *args, attempts: int = 3, **kwargs) -> dict:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await fn(*args, **kwargs)
        except BankError as e:
            last = e
            await asyncio.sleep(0.2 * (i + 1))
    raise last  # type: ignore[misc]


bank: BankAPI = MockBank()
