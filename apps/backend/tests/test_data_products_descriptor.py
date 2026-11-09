from __future__ import annotations

from data_products import descriptor


def test_c360_graph_has_9_statements_3_sources():
    graph = descriptor.get_graph("c360")
    statements = [n for n in graph.nodes if n.type == "statement"]
    sources = [n for n in graph.nodes if n.type == "source"]
    assert len(statements) == 9 and len(sources) == 3


def test_fct_c360_profile_and_streak_are_product_nodes():
    graph = descriptor.get_graph("c360")
    product = [n for n in graph.nodes if n.is_product]
    assert sorted(n.id for n in product) == ["fct_c360_profile", "fct_merchant_streak"]


def test_c360_statements_table_types():
    graph = descriptor.get_graph("c360")
    statements = [n for n in graph.nodes if n.type == "statement"]
    sources = [n for n in graph.nodes if n.type == "source"]
    assert statements and all(n.table_type in ("materialized_table", "streaming_table") for n in statements)
    assert all(n.table_type is None for n in sources)


def test_unknown_product_returns_none():
    assert descriptor.get_graph("nope") is None


def test_list_summaries_reports_statement_count_9():
    summaries = descriptor.list_summaries()
    c360 = next(s for s in summaries if s.id == "c360")
    assert c360.statement_count == 9
