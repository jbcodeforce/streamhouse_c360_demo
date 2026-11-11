"""Build Data Products graph descriptors from a dbt ``manifest.json``.

This is the pure, side-effect-free core: :func:`build_descriptors` takes a
parsed dbt manifest dict plus a ``statement_name_fn`` and returns one
descriptor dict per data product, ready to serialize as ``<product>.json``.
It imports only the backend ``GraphNode``/``GraphEdge``/``Graph`` models, so
every descriptor it emits is validated against exactly what
``descriptor.get_graph`` will later parse — the generator can never drift from
the reader's schema.

The dbt-specific bits (the real Flink statement-name sanitizer, the profile
prefix, reading/writing files) live in ``scripts/build_descriptors.py`` so this
module stays importable and testable in the backend venv alone.

Mapping (dbt manifest -> descriptor):

* data product = the first path segment of a model (the top-level folder under
  ``models/``); one descriptor per product.
* statement node (one per model): ``id``/``label``/``topic`` = model name;
  ``table_type`` = ``config.materialized`` when it is ``materialized_table`` or
  ``streaming_table`` (any other materialization carries no table_type);
  ``statement_name`` = ``statement_name_fn(model_name)``; ``is_product`` =
  the model lives under a ``facts/`` subfolder.
* source node (one per referenced dbt source): ``id`` = ``topic_<source.name>``,
  ``label``/``topic`` = the source ``identifier`` (the Kafka topic).
* edges = each model's ``depends_on.nodes``, mapped to the node ids above.
"""

from __future__ import annotations

from collections.abc import Callable

from data_products.models import Graph, GraphEdge, GraphNode

# Materializations that map to a descriptor table_type; anything else (view,
# table, ...) is still a statement node but carries no table_type.
_TABLE_TYPES = {"materialized_table", "streaming_table"}


def _product_of(path: str) -> str:
    """The data product a model belongs to: the top-level folder under models/."""
    return path.split("/", 1)[0]


def _is_product(path: str) -> bool:
    """A model is the product output when it lives under a ``facts/`` subfolder
    (``<product>/facts/...``)."""
    parts = path.split("/")
    return len(parts) > 2 and parts[1] == "facts"


def _humanize(product_id: str) -> str:
    """A display name derived from the folder, e.g. ``c360`` -> ``C360``."""
    return product_id.replace("_", " ").replace("-", " ").title()


def _pool_from_config(model: dict) -> str | None:
    """Default ``pool_for``: the per-model ``compute_pool_id`` from dbt config."""
    return model.get("config", {}).get("compute_pool_id")


def _serialize_node(node: GraphNode) -> dict:
    """Validated node -> compact descriptor dict: drop None fields and the false
    ``is_product``/``external`` flags so source nodes stay ``{id,type,label,topic}``
    and only the nodes that need a flag carry it (matching the hand-authored
    descriptor style)."""
    data = node.model_dump(exclude_none=True)
    for flag in ("is_product", "external"):
        if not data.get(flag):
            data.pop(flag, None)
    return data


def build_descriptors(
    manifest: dict,
    statement_name_fn: Callable[[str], str],
    *,
    pool_for: Callable[[dict], str | None] = _pool_from_config,
    default_pool: str | None = None,
) -> dict[str, dict]:
    """Return ``{product_id: descriptor_dict}`` built from a dbt manifest.

    ``statement_name_fn`` maps a model name to its Flink statement name; it is
    injected so this core needs neither the confluent adapter nor a dbt profile.
    ``pool_for(model)`` returns the model's Flink compute pool (defaults to the
    dbt ``config.compute_pool_id``); ``default_pool`` is the fallback when a model
    pins no pool (the connection-default pool, e.g. ``FLINK_COMPUTE_POOL_ID``).
    """
    models_by_uid = {
        uid: node
        for uid, node in manifest.get("nodes", {}).items()
        if node.get("resource_type") == "model"
    }
    sources = manifest.get("sources", {})

    products: dict[str, dict] = {}
    for product_id in sorted({_product_of(m["path"]) for m in models_by_uid.values()}):
        owned_models = [m for m in models_by_uid.values() if _product_of(m["path"]) == product_id]

        # Traverse upstream dependencies to build the full lineage closure.
        visited_model_uids: set[str] = set()
        needed_source_uids: set[str] = set()
        queue = [m.get("unique_id", uid) for uid, m in models_by_uid.items() if _product_of(m["path"]) == product_id]

        while queue:
            uid = queue.pop(0)
            if uid in visited_model_uids:
                continue
            visited_model_uids.add(uid)
            model = models_by_uid[uid]
            for dep_uid in model.get("depends_on", {}).get("nodes", []):
                if dep_uid in models_by_uid:
                    if dep_uid not in visited_model_uids:
                        queue.append(dep_uid)
                elif dep_uid in sources:
                    needed_source_uids.add(dep_uid)

        def _stmt_node(model: dict, *, external: bool) -> GraphNode:
            name = model["name"]
            materialized = model.get("config", {}).get("materialized")
            return GraphNode(
                id=name,
                type="statement",
                label=name,
                statement_name=statement_name_fn(name),
                topic=name,
                is_product=False if external else _is_product(model["path"]),
                table_type=materialized if materialized in _TABLE_TYPES else None,
                compute_pool_id=pool_for(model) or default_pool,
                external=external,
            )

        source_nodes: list[GraphNode] = []
        for src_uid in sorted(needed_source_uids, key=lambda u: f"topic_{sources[u]['name']}"):
            src = sources[src_uid]
            src_id = f"topic_{src['name']}"
            source_nodes.append(
                GraphNode(
                    id=src_id,
                    type="source",
                    label=src["identifier"],
                    topic=src["identifier"],
                )
            )

        owned_statement_nodes: list[GraphNode] = []
        for uid in sorted(
            [u for u in visited_model_uids if _product_of(models_by_uid[u]["path"]) == product_id],
            key=lambda u: models_by_uid[u]["path"],
        ):
            owned_statement_nodes.append(_stmt_node(models_by_uid[uid], external=False))

        external_statement_nodes: list[GraphNode] = []
        for uid in sorted(
            [u for u in visited_model_uids if _product_of(models_by_uid[u]["path"]) != product_id],
            key=lambda u: models_by_uid[u]["path"],
        ):
            external_statement_nodes.append(_stmt_node(models_by_uid[uid], external=True))

        edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str]] = set()

        for uid in visited_model_uids:
            model = models_by_uid[uid]
            target_name = model["name"]
            for dep_uid in model.get("depends_on", {}).get("nodes", []):
                if dep_uid in visited_model_uids:
                    src_name = models_by_uid[dep_uid]["name"]
                    if (src_name, target_name) not in seen_edges:
                        seen_edges.add((src_name, target_name))
                        edges.append(GraphEdge(source=src_name, target=target_name))
                elif dep_uid in sources:
                    src_id = f"topic_{sources[dep_uid]['name']}"
                    if (src_id, target_name) not in seen_edges:
                        seen_edges.add((src_id, target_name))
                        edges.append(GraphEdge(source=src_id, target=target_name))

        edges.sort(key=lambda e: (e.source, e.target))

        # Validate the whole graph as the backend would load it.
        graph = Graph(
            nodes=[*source_nodes, *owned_statement_nodes, *external_statement_nodes],
            edges=edges,
        )

        name = _humanize(product_id)
        products[product_id] = {
            "id": product_id,
            "name": name,
            "description": f"{name} data product, generated from dbt models.",
            "nodes": [_serialize_node(n) for n in graph.nodes],
            "edges": [e.model_dump() for e in graph.edges],
        }

    return products
