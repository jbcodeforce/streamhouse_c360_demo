"""Generate realistic back-dated transactions on existing cards and accounts.

Pure logic (no DB / Kafka). About 90% of transactions are card transactions
(``card_id`` set, no ``account_id``); the rest are direct transactions on a
checking account (online bill payments / purchases and transfers between
accounts). Timestamps start at ``now - 7 days`` and advance by 15 minutes per
transaction, independent of how fast the batch is produced, so the data looks
like a week of organic activity.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from accounts.models import Account
from cards.models import Card
from transactions.models import Transaction

DEFAULT_COUNT = 200
CARD_SHARE = 0.9
START_OFFSET = timedelta(days=7)
STEP = timedelta(minutes=15)

# (description, merchant_name, merchant_category, channel) — modelled on the
# values in data/transactions.csv.
# Card purchases (POS or online).
_CARD_DEBIT_PROFILES = [
    ("Online purchase", "Amazon", "RETAIL", "ONLINE"),
    ("Team breakfast", "Starbucks", "FOOD", "POS"),
    ("Fuel", "Shell", "FUEL", "POS"),
    ("Streaming subscription", "Netflix", "ENTERTAINMENT", "ONLINE"),
    ("Groceries", "Whole Foods", "GROCERY", "POS"),
    ("Ride", "Uber", "TRANSPORT", "ONLINE"),
]
# Cards only see purchases and refunds.
_CARD_CREDIT_PROFILES = [("Refund", "Amazon", "RETAIL", "ONLINE")]
# Direct account transactions: online bill payments and transfers between accounts.
_DIRECT_DEBIT_PROFILES = [
    ("Online bill payment", "Con Edison", "UTILITIES", "ONLINE"),
    ("Online purchase", "Amazon", "RETAIL", "ONLINE"),
    ("Transfer to savings", "Account transfer", "TRANSFER", "ONLINE"),
    ("Transfer to account", "Account transfer", "TRANSFER", "MOBILE"),
]
_DIRECT_CREDIT_PROFILES = [
    ("Salary", "Acme Payroll", "INCOME", "ONLINE"),
    ("Transfer from savings", "Account transfer", "TRANSFER", "ONLINE"),
    ("Transfer from account", "Account transfer", "TRANSFER", "MOBILE"),
]

# (merchant_city, merchant_state, zip) — domestic locations (account currency).
_DOMESTIC_LOCATIONS = [
    ("Seattle", "WA", "98109"),
    ("Austin", "TX", "78703"),
    ("Portland", "OR", "97204"),
    ("Houston", "TX", "77002"),
    ("New York", "NY", "10001"),
    ("Chicago", "IL", "60601"),
    ("Denver", "CO", "80202"),
    ("Miami", "FL", "33131"),
]
# (merchant_city, merchant_state/region, postal code, currency) — foreign
# merchants, charged in the local currency.
_FOREIGN_LOCATIONS = [
    ("London", "ENG", "SW1A 2AA", "GBP"),
    ("Paris", "IDF", "75001", "EUR"),
    ("Berlin", "BE", "10115", "EUR"),
    ("Madrid", "MD", "28013", "EUR"),
    ("Toronto", "ON", "M5V 2T6", "CAD"),
    ("Tokyo", "13", "100-0001", "JPY"),
    ("Sydney", "NSW", "2000", "AUD"),
    ("Zurich", "ZH", "8001", "CHF"),
    ("Mexico City", "CMX", "06000", "MXN"),
]
FOREIGN_SHARE = 0.2


class NoEligibleAccountsError(Exception):
    """Raised when there is no ACTIVE, open account (or card) to attach transactions to."""


def _use_chip(channel: str, card: Card) -> str | None:
    if channel == "ONLINE":
        return "Online Transaction"
    if channel == "POS":
        return "Chip Transaction" if card.has_chip else "Swipe Transaction"
    return None


def generate(
    accounts: list[Account],
    cards: list[Card] | None = None,
    count: int = DEFAULT_COUNT,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> list[Transaction]:
    """Return *count* transactions, oldest first.

    ~70% go on an unexpired card of an eligible account (customer derived from
    the card's account); the rest go on an eligible checking account. With no
    eligible card, every transaction is account-based.
    """
    rng = rng or random.Random()
    now = now or datetime.now(tz=timezone.utc)
    start = (now - START_OFFSET).replace(microsecond=0)

    eligible = {a.account_id: a for a in accounts if a.status == "ACTIVE" and a.closed_date is None}
    today = now.date() if isinstance(now, datetime) else date.today()
    eligible_cards = [
        c for c in (cards or []) if c.account_id in eligible and c.expires >= today
    ]
    checking = [a for a in eligible.values() if a.account_type == "CHECKING"] or list(eligible.values())
    if not checking and not eligible_cards:
        raise NoEligibleAccountsError("no active accounts available")

    result: list[Transaction] = []
    for i in range(count):
        use_card = bool(eligible_cards) and (not checking or rng.random() < CARD_SHARE)
        card = rng.choice(eligible_cards) if use_card else None
        account = eligible[card.account_id] if card else rng.choice(checking)
        currency = account.currency
        city, state, zip_code = rng.choice(_DOMESTIC_LOCATIONS)
        if rng.random() < 0.85:
            txn_type = "DEBIT"
            description, merchant, category, channel = rng.choice(
                _CARD_DEBIT_PROFILES if card else _DIRECT_DEBIT_PROFILES
            )
            amount = round(rng.uniform(3, 400), 2)
            if card and rng.random() < FOREIGN_SHARE:
                city, state, zip_code, currency = rng.choice(_FOREIGN_LOCATIONS)
        else:
            txn_type = "CREDIT"
            profiles = _CARD_CREDIT_PROFILES if card else _DIRECT_CREDIT_PROFILES
            description, merchant, category, channel = rng.choice(profiles)
            amount = round(rng.uniform(50, 2500), 2)
        transacted_at = start + i * STEP
        result.append(
            Transaction(
                transaction_id=uuid4(),
                account_id=None if card else account.account_id,
                card_id=card.card_id if card else None,
                use_chip=_use_chip(channel, card) if card else None,
                customer_id=account.customer_id,
                transaction_type=txn_type,
                amount=amount,
                currency=currency,
                description=description,
                merchant_name=merchant,
                merchant_category=category,
                channel=channel,
                merchant_city=city,
                merchant_state=state,
                zip=zip_code,
                status="COMPLETED",
                transacted_at=transacted_at,
                posted_at=transacted_at,
                created_at=now,
            )
        )
    return result
