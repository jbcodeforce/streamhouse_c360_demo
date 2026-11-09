"""C360 analytics: a snapshot-query dashboard over ``fct_c360_profile``.

The ``fct_c360_profile`` materialized table (one upserted row per customer,
demographics joined to account/transaction aggregates) is the serving layer a
real-time context engine reads. This package exposes a single snapshot of that
table as pre-aggregated analytics for the frontend dashboard.

The provider runs bounded Flink SQL *snapshot queries* against the tables on
Confluent Cloud.
"""
