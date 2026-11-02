"""Deterministic snapshot fixture for the C360 analytics dashboard.

These rows mirror the shape of a ``SELECT`` snapshot of ``fct_c360_profile``:
one dict per customer, keyed by the materialized table's column names. They are
aligned to the ten unique customers in ``customers/data/customers.csv`` (the
seed) — real ``customer_id`` UUIDs and names so the by-name search and the
``WHERE customer_id = …`` lookup resolve against the mock exactly as they would
against the live table — with plausible account/transaction aggregates layered
on. ``missing_phone_flag`` is set for the two seed customers with a blank phone
(Susan Patel, Ashley Nguyen).
"""

from __future__ import annotations

PROFILE_SNAPSHOT: list[dict] = [
    {
        "customer_id": "00000000-0000-0000-0000-ef1234567890",
        "first_name": "James", "last_name": "Carter",
        "customer_segment": "PRIVATE", "gender": "M", "country": "US",
        "city": "Springfield", "state": "IL", "customer_since": "2022-06-01",
        "generation_segment": "Gen X", "age_years": 40, "days_since_registration": 1608,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 2, "total_balance": 18400.50, "txn_count": 84, "txn_total": 42310.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-f01234567891",
        "first_name": "Maria", "last_name": "Gonzalez",
        "customer_segment": "SMB", "gender": "F", "country": "US",
        "city": "Los Angeles", "state": "CA", "customer_since": "2021-03-15",
        "generation_segment": "Millennial", "age_years": 35, "days_since_registration": 2052,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 4, "total_balance": 126750.00, "txn_count": 310, "txn_total": 512900.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-012345678902",
        "first_name": "Robert", "last_name": "Kim",
        "customer_segment": "PRIVATE", "gender": "M", "country": "US",
        "city": "New York", "state": "NY", "customer_since": "2020-09-10",
        "generation_segment": "Gen X", "age_years": 47, "days_since_registration": 2237,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 3, "total_balance": 54200.25, "txn_count": 156, "txn_total": 98450.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-123456789013",
        "first_name": "Susan", "last_name": "Patel",
        "customer_segment": "PRIVATE", "gender": "F", "country": "US",
        "city": "San Francisco", "state": "CA", "customer_since": "2023-01-22",
        "generation_segment": "Millennial", "age_years": 32, "days_since_registration": 1373,
        "missing_email_flag": 0, "missing_phone_flag": 1,
        "account_count": 1, "total_balance": 6300.00, "txn_count": 41, "txn_total": 15720.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-234567890124",
        "first_name": "David", "last_name": "Okafor",
        "customer_segment": "SMB", "gender": "M", "country": "US",
        "city": "Chicago", "state": "IL", "customer_since": "2019-07-04",
        "generation_segment": "Gen X", "age_years": 43, "days_since_registration": 2671,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 5, "total_balance": 203100.00, "txn_count": 428, "txn_total": 788250.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-345678901235",
        "first_name": "Jennifer", "last_name": "Walsh",
        "customer_segment": "PRIVATE", "gender": "F", "country": "US",
        "city": "Boston", "state": "MA", "customer_since": "2022-11-30",
        "generation_segment": "Millennial", "age_years": 37, "days_since_registration": 1426,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 2, "total_balance": 31500.75, "txn_count": 97, "txn_total": 54300.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-456789012346",
        "first_name": "Michael", "last_name": "Torres",
        "customer_segment": "PRIVATE", "gender": "M", "country": "US",
        "city": "Miami", "state": "FL", "customer_since": "2018-04-17",
        "generation_segment": "Gen X", "age_years": 50, "days_since_registration": 3114,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 3, "total_balance": 72900.00, "txn_count": 203, "txn_total": 141600.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-567890123457",
        "first_name": "Ashley", "last_name": "Nguyen",
        "customer_segment": "PRIVATE", "gender": "F", "country": "US",
        "city": "Ann Arbor", "state": "MI", "customer_since": "2023-08-09",
        "generation_segment": "Millennial", "age_years": 30, "days_since_registration": 1174,
        "missing_email_flag": 0, "missing_phone_flag": 1,
        "account_count": 1, "total_balance": 4850.00, "txn_count": 28, "txn_total": 9210.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-678901234568",
        "first_name": "Thomas", "last_name": "Brennan",
        "customer_segment": "SMB", "gender": "M", "country": "US",
        "city": "Seattle", "state": "WA", "customer_since": "2017-12-01",
        "generation_segment": "Boomer+", "age_years": 56, "days_since_registration": 3251,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 6, "total_balance": 318400.00, "txn_count": 512, "txn_total": 1024700.00,
    },
    {
        "customer_id": "00000000-0000-0000-0000-789012345679",
        "first_name": "Linda", "last_name": "Sharma",
        "customer_segment": "SMB", "gender": "F", "country": "US",
        "city": "Austin", "state": "TX", "customer_since": "2021-10-03",
        "generation_segment": "Millennial", "age_years": 38, "days_since_registration": 1849,
        "missing_email_flag": 0, "missing_phone_flag": 0,
        "account_count": 4, "total_balance": 95600.00, "txn_count": 287, "txn_total": 436800.00,
    },
]
