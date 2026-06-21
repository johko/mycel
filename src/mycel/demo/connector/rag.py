"""
Qdrant RAG connector backend.

Loads a JSON document file into an in-memory Qdrant collection and exposes it
over MCP as a semantic-search surface: `list_documents`, `search`, and
`get_document`. It demonstrates a connector whose data source is a vector index
rather than a flat file or table — the agent retrieves by meaning, not by id.

Embeddings are produced locally on CPU by fastembed (the default
`BAAI/bge-small-en-v1.5` ONNX model), so no GPU or external embedding API is
needed. The model is downloaded on first use and cached thereafter.

For OPA governance it implements `policy_view`: each search hit / fetched
document is a record carrying its original metadata (e.g. `name`,
`date_of_birth`, `source`), so record-oriented egress policies apply unchanged.

The document file maps id -> {"label", "text", ...metadata}; `text` is embedded,
everything else is kept as the record payload.
"""

import json
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mycel.demo.connector.policy import policy_view_tool

_COLLECTION = "documents"
_MODEL = "BAAI/bge-small-en-v1.5"
# Qdrant point ids must be int/UUID, so original ids are stored in the payload.
_DOC_ID = "doc_id"


class RagStore:
    """An in-memory Qdrant index over a JSON document file."""

    def __init__(self, path: str | Path):
        from qdrant_client import QdrantClient, models

        self._models = models
        self._docs: dict[str, dict] = json.loads(Path(path).read_text())
        self._lock = threading.Lock()
        self._client = QdrantClient(":memory:")

        self._client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=models.VectorParams(
                size=self._client.get_embedding_size(_MODEL),
                distance=models.Distance.COSINE,
            ),
        )
        self._client.upsert(
            collection_name=_COLLECTION,
            points=[
                models.PointStruct(
                    id=i,
                    vector=models.Document(text=rec.get("text", ""), model=_MODEL),
                    payload={**rec, _DOC_ID: doc_id},
                )
                for i, (doc_id, rec) in enumerate(self._docs.items())
            ],
        )

    def list_documents(self) -> list[dict]:
        return [
            {"id": doc_id, "label": rec.get("label", doc_id)}
            for doc_id, rec in self._docs.items()
        ]

    def get_document(self, id: str) -> dict:
        rec = self._docs.get(id)
        if rec is None:
            return {"error": f"document {id!r} not found"}
        return {"id": id, **rec}

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        with self._lock:
            hits = self._client.query_points(
                collection_name=_COLLECTION,
                query=self._models.Document(text=query, model=_MODEL),
                limit=top_k,
                with_payload=True,
            ).points
        results: list[dict] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            doc_id = payload.pop(_DOC_ID, None)
            results.append({"id": doc_id, "score": hit.score, **payload})
        return results


def _records_from_observations(observations: list[dict]) -> dict[str, dict]:
    """Map `search` hits and `get_document` results to {id: record} for OPA.

    Each hit/document carries its original metadata (name, date_of_birth,
    source, ...), so the egress policies see the same fields they would from a
    flat-file record.
    """
    records: dict[str, dict] = {}
    n = 0
    for obs in observations:
        tool, result = obs.get("tool"), obs.get("result")
        if tool not in ("search", "get_document"):
            continue
        # a single search hit is reduced to one dict; many hits arrive as a list
        items = result if isinstance(result, list) else [result]
        for item in items:
            if not isinstance(item, dict) or "error" in item:
                continue
            rec_id = item.get("id")
            key = str(rec_id) if rec_id is not None else f"rag:{n}"
            records[key] = item
            n += 1
    return records


def build_rag_server(
    name: str, store: RagStore, *, host: str = "0.0.0.0", port: int = 9000
) -> FastMCP:
    mcp = FastMCP(name, host=host, port=port)

    @mcp.tool(description="List all document IDs with a short label.")
    def list_documents() -> list[dict]:
        return store.list_documents()

    @mcp.tool(
        description=(
            "Semantically search the documents for a query and return the top "
            "matches with their contents and relevance score."
        )
    )
    def search(query: str, top_k: int = 3) -> list[dict]:
        return store.search(query, top_k)

    @mcp.tool(description="Fetch the full contents of a document by ID.")
    def get_document(id: str) -> dict:
        return store.get_document(id)

    policy_view_tool(mcp, _records_from_observations)
    return mcp
