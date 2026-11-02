"""Registry of hard-coded CEP scenario definitions.

Each scenario is a fully scripted transaction sequence guaranteed to fire its
associated MATCH_RECOGNIZE Flink query.  The UUIDs are the committed seed values
from the CSV files so the rows resolve against real customer/account rows in
Postgres.

Account IDs are NOT stored in the accounts CSV — only account_number is.  The
runner resolves the actual account_id UUID via the accounts inventory at
execution time using account_number as the lookup key.
"""

from __future__ import annotations

from uuid import UUID

from scenarios.models import ScenarioDefinition, ScenarioTransaction

# ---------------------------------------------------------------------------
# Seed UUIDs (match customers.csv and accounts.csv exactly)
# ---------------------------------------------------------------------------
_CARTER   = UUID("00000000-0000-0000-0000-ef1234567890")
_GONZALEZ = UUID("00000000-0000-0000-0000-f01234567891")
_OKAFOR   = UUID("00000000-0000-0000-0000-234567890124")

# account_number strings — resolved to UUIDs at runtime by the runner
CARTER_CHK  = "CHK-39958838"
CARTER_SAV  = "SAV-39958839"
GONZALEZ_CHK = "CHK-83197857"
OKAFOR_CHK  = "CHK-39587039"

# ---------------------------------------------------------------------------
# Pattern 1 — Fraud Probe
# A micro-charge (card verification) immediately followed by large charges on
# Carter's CHECKING account.  Carter's SAVINGS gets a benign charge at the same
# time to show the query fires per-account, not per-customer.
# ---------------------------------------------------------------------------
_FRAUD_PROBE = ScenarioDefinition(
    scenario_id="fraud-probe",
    pattern="fct_fraud_probe",
    label="Fraud Probe",
    description=(
        "Card-cloning telltale: a $2.99 verification charge on Carter's CHECKING "
        "account is immediately followed by two large charges ($899 + $749). "
        "Carter's SAVINGS account gets a benign $45 grocery charge that must NOT "
        "trigger the pattern — demonstrating per-account isolation."
    ),
    transactions=[
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),  # placeholder; runner resolves
            customer_id=_CARTER,
            transaction_type="DEBIT",
            amount=2.99,
            description="Card verification",
            merchant_name="Amazon",
            merchant_category="RETAIL",
            channel="ONLINE",
            offset_seconds=0,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_CARTER,
            transaction_type="DEBIT",
            amount=899.00,
            description="Electronics",
            merchant_name="Amazon",
            merchant_category="RETAIL",
            channel="ONLINE",
            offset_seconds=30,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_CARTER,
            transaction_type="DEBIT",
            amount=749.00,
            description="Gift cards",
            merchant_name="Amazon",
            merchant_category="RETAIL",
            channel="ONLINE",
            offset_seconds=60,
        ),
        # benign charge on Carter's SAVINGS — must NOT match
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_CARTER,
            transaction_type="DEBIT",
            amount=45.00,
            description="Groceries",
            merchant_name="Whole Foods",
            merchant_category="GROCERY",
            channel="POS",
            offset_seconds=15,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Pattern 2 — Merchant Streak
# Gonzalez makes 3 consecutive FOOD charges on her CHECKING account, signalling
# a habit or loyalty opportunity.
# ---------------------------------------------------------------------------
_MERCHANT_STREAK = ScenarioDefinition(
    scenario_id="merchant-streak",
    pattern="fct_merchant_streak",
    label="Merchant Streak",
    description=(
        "Loyalty signal: Maria Gonzalez makes 3 consecutive FOOD transactions "
        "within 10 minutes — coffee, team lunch, client dinner — triggering the "
        "merchant-streak pattern. Useful for personalised offers."
    ),
    transactions=[
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_GONZALEZ,
            transaction_type="DEBIT",
            amount=12.50,
            description="Coffee",
            merchant_name="Starbucks",
            merchant_category="FOOD",
            channel="POS",
            offset_seconds=0,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_GONZALEZ,
            transaction_type="DEBIT",
            amount=34.00,
            description="Team lunch",
            merchant_name="Chipotle",
            merchant_category="FOOD",
            channel="POS",
            offset_seconds=300,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_GONZALEZ,
            transaction_type="DEBIT",
            amount=89.00,
            description="Client dinner",
            merchant_name="Nobu",
            merchant_category="FOOD",
            channel="POS",
            offset_seconds=600,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_GONZALEZ,
            transaction_type="DEBIT",
            amount=100.00,
            description="Gaz",
            merchant_name="Shell",
            merchant_category="GAZ",
            channel="POS",
            offset_seconds=900,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Pattern 3 — SMB Spike
# Okafor (SMB segment) makes 3 large DEBIT charges followed by a CREDIT
# reversal — signalling a business-expense dispute or anomalous spike.
# ---------------------------------------------------------------------------
_SMB_SPIKE = ScenarioDefinition(
    scenario_id="smb-spike",
    pattern="fct_smb_spike",
    label="SMB Spike",
    description=(
        "Business expense anomaly: David Okafor (SMB) makes three large charges "
        "($420 office supplies, $380 cloud software, $610 hardware) followed by "
        "a $1,200 expense reversal — all within 15 minutes. Flags the account for "
        "relationship-manager review."
    ),
    transactions=[
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_OKAFOR,
            transaction_type="DEBIT",
            amount=420.00,
            description="Office supplies",
            merchant_name="Staples",
            merchant_category="RETAIL",
            channel="POS",
            offset_seconds=0,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_OKAFOR,
            transaction_type="DEBIT",
            amount=380.00,
            description="Cloud software",
            merchant_name="AWS",
            merchant_category="RETAIL",
            channel="ONLINE",
            offset_seconds=300,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_OKAFOR,
            transaction_type="DEBIT",
            amount=610.00,
            description="Hardware",
            merchant_name="Apple",
            merchant_category="RETAIL",
            channel="ONLINE",
            offset_seconds=600,
        ),
        ScenarioTransaction(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            customer_id=_OKAFOR,
            transaction_type="CREDIT",
            amount=1200.00,
            description="Expense reversal",
            merchant_name="Acme Corp",
            merchant_category="INCOME",
            channel="ONLINE",
            offset_seconds=900,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------
SCENARIOS: dict[str, ScenarioDefinition] = {
    s.scenario_id: s
    for s in [_FRAUD_PROBE, _MERCHANT_STREAK, _SMB_SPIKE]
}

# Account-number → scenario transactions mapping
# Used by runner.py to look up the account_number for each ScenarioTransaction.
# key = (scenario_id, customer_id) is not enough because one customer can have
# multiple accounts.  We store account_number per-entry in a parallel structure.
ACCOUNT_NUMBERS: dict[str, list[str]] = {
    "fraud-probe":       [CARTER_CHK, CARTER_CHK, CARTER_CHK, CARTER_SAV, CARTER_CHK],
    "merchant-streak":   [GONZALEZ_CHK, GONZALEZ_CHK, GONZALEZ_CHK, GONZALEZ_CHK],
    "smb-spike":         [OKAFOR_CHK, OKAFOR_CHK, OKAFOR_CHK, OKAFOR_CHK],
}
