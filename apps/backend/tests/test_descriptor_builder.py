"""Tests for the pure dbt-manifest -> data-product-descriptor builder.

The builder is deterministic and side-effect-free: it takes a parsed dbt
``manifest.json`` dict plus a ``statement_name_fn`` (injected so these tests
don't need the real confluent adapter) and returns one descriptor dict per
data product. The CLI in ``scripts/build_descriptors.py`` wires in the real
adapter sanitizer and writes the files; that thin layer is not covered here.
"""

from __future__ import annotations

from data_products import descriptor_builder


def _manifest() -> dict:
    """A trimmed manifest shaped like dbt's, exercising every mapping rule:
    a source->model edge, a model->model edge, a facts (product) node, and a
    streaming_table alongside materialized_table."""
    return {
        "metadata": {"project_name": "streamhouse"},
        "nodes": {
            "model.streamhouse.src_customers": {
                "resource_type": "model", "name": "src_customers",
                "path": "c360/sources/src_customers.sql",
                "config": {"materialized": "materialized_table"},
                "depends_on": {"nodes": ["source.streamhouse.cdc.customers"]},
            },
            "model.streamhouse.stream_orders": {
                "resource_type": "model", "name": "stream_orders",
                "path": "c360/sources/stream_orders.sql",
                "config": {"materialized": "streaming_table"},
                "depends_on": {"nodes": []},
            },
            "model.streamhouse.dim_customers": {
                "resource_type": "model", "name": "dim_customers",
                "path": "c360/dimensions/dim_customers.sql",
                "config": {"materialized": "materialized_table"},
                "depends_on": {"nodes": ["model.streamhouse.src_customers"]},
            },
            "model.streamhouse.fct_c360_profile": {
                "resource_type": "model", "name": "fct_c360_profile",
                "path": "c360/facts/fct_c360_profile.sql",
                "config": {"materialized": "materialized_table"},
                "depends_on": {"nodes": ["model.streamhouse.dim_customers"]},
            },
            # A non-MT/non-streaming materialization (e.g. a plain view): still a
            # statement node, but it carries no table_type.
            "model.streamhouse.helper_view": {
                "resource_type": "model", "name": "helper_view",
                "path": "c360/dimensions/helper_view.sql",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": []},
            },
            # A seed/other resource type must be ignored entirely.
            "seed.streamhouse.some_seed": {
                "resource_type": "seed", "name": "some_seed",
                "path": "c360/some_seed.csv", "config": {}, "depends_on": {"nodes": []},
            },
        },
        "sources": {
            "source.streamhouse.cdc.customers": {
                "resource_type": "source", "name": "customers",
                "identifier": "cdc.public.customers",
            },
        },
    }


def _build() -> dict:
    return descriptor_builder.build_descriptors(_manifest(), lambda name: f"dbt-{name}")


def _nodes_by_id(descriptor: dict) -> dict[str, dict]:
    return {n["id"]: n for n in descriptor["nodes"]}


def test_groups_by_top_level_models_folder():
    result = _build()
    assert set(result) == {"c360"}
    assert result["c360"]["id"] == "c360"


def test_statement_and_source_node_counts():
    nodes = _build()["c360"]["nodes"]
    statements = [n for n in nodes if n["type"] == "statement"]
    sources = [n for n in nodes if n["type"] == "source"]
    # 5 models (seed ignored), 1 source.
    assert len(statements) == 5 and len(sources) == 1


def test_table_type_mirrors_dbt_materialized():
    byid = _nodes_by_id(_build()["c360"])
    assert byid["src_customers"]["table_type"] == "materialized_table"
    assert byid["stream_orders"]["table_type"] == "streaming_table"
    # A 'view' materialization is neither MT nor streaming -> no table_type key.
    assert "table_type" not in byid["helper_view"]


def test_statement_name_comes_from_injected_fn():
    byid = _nodes_by_id(_build()["c360"])
    assert byid["src_customers"]["statement_name"] == "dbt-src_customers"


def test_only_facts_models_are_product_nodes():
    byid = _nodes_by_id(_build()["c360"])
    assert byid["fct_c360_profile"]["is_product"] is True
    # Non-product statement nodes omit the flag rather than carry false.
    assert "is_product" not in byid["src_customers"]


def test_source_node_shape():
    byid = _nodes_by_id(_build()["c360"])
    src = byid["topic_customers"]
    assert src["type"] == "source"
    assert src["label"] == "cdc.public.customers" and src["topic"] == "cdc.public.customers"
    # Source nodes have no statement_name/table_type/is_product noise.
    assert "statement_name" not in src and "table_type" not in src and "is_product" not in src


def test_edges_reconstruct_source_and_model_dependencies():
    edges = {(e["source"], e["target"]) for e in _build()["c360"]["edges"]}
    assert ("topic_customers", "src_customers") in edges  # source -> model
    assert ("src_customers", "dim_customers") in edges     # model -> model
    assert ("dim_customers", "fct_c360_profile") in edges
    # stream_orders/helper_view have no deps -> contribute no edges.
    assert len(edges) == 3


def _multi_manifest() -> dict:
    """Two products where a crm model depends on a c360 model — exercises the
    cross-product (external) import path and per-model compute_pool_id."""
    return {
        "metadata": {"project_name": "streamhouse"},
        "nodes": {
            "model.streamhouse.fct_c360_profile": {
                "resource_type": "model", "name": "fct_c360_profile",
                "path": "c360/facts/fct_c360_profile.sql",
                "config": {"materialized": "materialized_table", "compute_pool_id": "lfcp-c360"},
                "depends_on": {"nodes": []},
            },
            "model.streamhouse.fct_crm_summary": {
                "resource_type": "model", "name": "fct_crm_summary",
                "path": "crm/facts/fct_crm_summary.sql",
                "config": {"materialized": "streaming_table", "compute_pool_id": "lfcp-crm"},
                "depends_on": {"nodes": ["model.streamhouse.fct_c360_profile"]},
            },
        },
        "sources": {},
    }


def test_statement_node_carries_compute_pool_id():
    byid = _nodes_by_id(descriptor_builder.build_descriptors(_multi_manifest(), lambda n: f"dbt-{n}")["crm"])
    assert byid["fct_crm_summary"]["compute_pool_id"] == "lfcp-crm"


def test_statement_node_falls_back_to_default_pool():
    # _manifest() models carry no config.compute_pool_id -> use default_pool.
    byid = _nodes_by_id(
        descriptor_builder.build_descriptors(_manifest(), lambda n: f"dbt-{n}", default_pool="lfcp-default")["c360"]
    )
    assert byid["src_customers"]["compute_pool_id"] == "lfcp-default"


def test_cross_product_dependency_emits_external_node():
    crm = descriptor_builder.build_descriptors(_multi_manifest(), lambda n: f"dbt-{n}")["crm"]
    byid = _nodes_by_id(crm)
    ext = byid["fct_c360_profile"]
    assert ext["type"] == "statement"
    assert ext["external"] is True
    assert "is_product" not in ext  # false flag is dropped
    assert ext["compute_pool_id"] == "lfcp-c360"  # the owning (c360) pool
    edges = {(e["source"], e["target"]) for e in crm["edges"]}
    assert ("fct_c360_profile", "fct_crm_summary") in edges


def test_owned_statement_node_has_no_external_flag():
    byid = _nodes_by_id(descriptor_builder.build_descriptors(_multi_manifest(), lambda n: f"dbt-{n}")["crm"])
    assert "external" not in byid["fct_crm_summary"]  # owned node drops false flag


def test_source_node_has_no_pool_or_external():
    byid = _nodes_by_id(_build()["c360"])
    src = byid["topic_customers"]
    assert "compute_pool_id" not in src and "external" not in src


def test_transitive_external_dependencies_and_sources():
    """Verify that upstream sources and intermediate models for external nodes
    are fully resolved and connected in the dependent product's graph."""
    manifest = {
        "metadata": {"project_name": "streamhouse"},
        "nodes": {
            "model.streamhouse.src_accounts": {
                "resource_type": "model", "name": "src_accounts",
                "path": "crm/sources/src_accounts.sql",
                "config": {"materialized": "streaming_table"},
                "depends_on": {"nodes": ["source.streamhouse.cdc.accounts"]},
            },
            "model.streamhouse.dim_customers": {
                "resource_type": "model", "name": "dim_customers",
                "path": "crm/dimensions/dim_customers.sql",
                "config": {"materialized": "streaming_table"},
                "depends_on": {"nodes": ["model.streamhouse.src_accounts"]},
            },
            "model.streamhouse.fct_c360_profile": {
                "resource_type": "model", "name": "fct_c360_profile",
                "path": "c360/facts/fct_c360_profile.sql",
                "config": {"materialized": "materialized_table"},
                "depends_on": {"nodes": ["model.streamhouse.dim_customers"]},
            },
        },
        "sources": {
            "source.streamhouse.cdc.accounts": {
                "resource_type": "source", "name": "accounts",
                "identifier": "cdc.public.accounts",
            },
        },
    }
    c360 = descriptor_builder.build_descriptors(manifest, lambda n: f"dbt-{n}")["c360"]
    byid = _nodes_by_id(c360)
    assert "topic_accounts" in byid
    assert byid["topic_accounts"]["type"] == "source"
    assert byid["src_accounts"]["external"] is True
    assert byid["dim_customers"]["external"] is True
    assert byid["fct_c360_profile"]["is_product"] is True

    edges = {(e["source"], e["target"]) for e in c360["edges"]}
    assert ("topic_accounts", "src_accounts") in edges
    assert ("src_accounts", "dim_customers") in edges
    assert ("dim_customers", "fct_c360_profile") in edges


def test_output_validates_against_backend_graph_model():
    # The builder must emit nodes/edges the backend's Graph model accepts, so a
    # regenerated descriptor is guaranteed loadable by descriptor.get_graph.
    from data_products.models import Graph

    descriptor = _build()["c360"]
    graph = Graph(nodes=descriptor["nodes"], edges=descriptor["edges"])
    assert len(graph.nodes) == 6
