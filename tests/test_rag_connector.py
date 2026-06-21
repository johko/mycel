"""Qdrant RAG connector backend: policy_view mapping (pure) + search (gated).

The search/get_document path needs qdrant-client + fastembed and downloads an
ONNX model on first use, so it is skipped when those are unavailable offline.
The policy_view mapping is pure and always tested.
"""

import json

import pytest

from mycel.demo.connector.rag import _records_from_observations


def test_policy_view_maps_search_hits_and_documents():
    observations = [
        {"tool": "list_documents", "arguments": {}, "result": [{"id": "D1"}]},
        {
            "tool": "search",
            "arguments": {"query": "alchemy lab head"},
            "result": [
                {"id": "PERS-0042", "score": 0.9, "name": "Morgana", "date_of_birth": "1971-03-14"},
            ],
        },
        {
            "tool": "get_document",
            "arguments": {"id": "PERS-0107"},
            "result": {"id": "PERS-0107", "name": "Bartholomew", "date_of_birth": "1958-11-02"},
        },
        {"tool": "search", "arguments": {}, "result": [{"error": "x"}]},
    ]
    records = _records_from_observations(observations)
    assert records["PERS-0042"]["name"] == "Morgana"
    assert records["PERS-0107"]["date_of_birth"] == "1958-11-02"
    # the PII fields the REDACT policy reads are present on the governed records
    assert all("name" in r and "date_of_birth" in r for r in records.values())


def test_policy_view_handles_single_hit_reduced_to_dict():
    # _reduce_result collapses a one-hit search to a dict, not a list
    observations = [
        {
            "tool": "search",
            "arguments": {},
            "result": {"id": "PERS-0042", "name": "Morgana", "date_of_birth": "1971-03-14"},
        }
    ]
    records = _records_from_observations(observations)
    assert records["PERS-0042"]["name"] == "Morgana"


def _rag_store(tmp_path):
    pytest.importorskip("qdrant_client")
    pytest.importorskip("fastembed")
    from mycel.demo.connector.rag import RagStore

    docs = {
        "PERS-0042": {
            "label": "head of Alchemy Lab",
            "name": "Morgana Hexenmeister",
            "date_of_birth": "1971-03-14",
            "text": "The head of the Alchemy Lab is Morgana Hexenmeister, born 1971-03-14.",
        },
        "EVENTS": {
            "label": "events",
            "text": "In 2021 the Alchemy Lab expansion was completed.",
        },
    }
    path = tmp_path / "docs.json"
    path.write_text(json.dumps(docs))
    try:
        return RagStore(path)
    except Exception as exc:  # model download blocked offline, etc.
        pytest.skip(f"RAG backend unavailable: {exc}")


def test_search_returns_record_shaped_hits(tmp_path):
    store = _rag_store(tmp_path)
    hits = store.search("who leads the alchemy lab", top_k=2)
    assert hits, "expected at least one hit"
    top = hits[0]
    assert top["id"] == "PERS-0042"
    assert top["name"] == "Morgana Hexenmeister"
    assert "score" in top


def test_get_document_round_trips(tmp_path):
    store = _rag_store(tmp_path)
    doc = store.get_document("PERS-0042")
    assert doc["id"] == "PERS-0042"
    assert doc["date_of_birth"] == "1971-03-14"
    assert "error" in store.get_document("NOPE")
