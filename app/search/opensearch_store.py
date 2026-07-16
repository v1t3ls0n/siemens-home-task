"""OpenSearch-backed vector store (kNN index, cosine similarity)."""

import hashlib

from opensearchpy import OpenSearch, helpers

from app.config import OPENSEARCH_URL, cfg


class OpenSearchStore:
    def __init__(self) -> None:
        self.client = OpenSearch(OPENSEARCH_URL, timeout=30)
        self.index = cfg()["search"]["index"]

    # -- setup --------------------------------------------------------------
    def ensure_ready(self, dim: int) -> None:
        if self.client.indices.exists(self.index):
            return
        self.client.indices.create(
            self.index,
            body={
                "settings": {"index": {"knn": True}},
                "mappings": {
                    "properties": {
                        "doc_type":     {"type": "keyword"},
                        "group_id":     {"type": "keyword"},
                        "title":        {"type": "text"},
                        "source_url":   {"type": "keyword"},
                        "chunk":        {"type": "text"},
                        "chunk_no":     {"type": "integer"},
                        "checksum":     {"type": "keyword"},
                        "fetched_at":   {"type": "date"},
                        "last_checked": {"type": "date"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": dim,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",
                            },
                        },
                    }
                },
            },
        )

    # -- freshness ----------------------------------------------------------
    def source_checksum(self, source_url: str) -> str | None:
        res = self.client.search(index=self.index, body={
            "size": 1, "_source": ["checksum"],
            "query": {"term": {"source_url": source_url}},
        })
        hits = res["hits"]["hits"]
        return hits[0]["_source"]["checksum"] if hits else None

    def touch_source(self, source_url: str, when: str) -> None:
        self.client.update_by_query(index=self.index, body={
            "query": {"term": {"source_url": source_url}},
            "script": {"source": "ctx._source.last_checked = params.t",
                       "params": {"t": when}},
        }, refresh=True)

    def replace_source(self, source_url: str, chunks: list[dict]) -> None:
        self.client.delete_by_query(index=self.index, body={
            "query": {"term": {"source_url": source_url}}}, refresh=True,
            ignore_unavailable=True)
        base = hashlib.sha1(source_url.encode()).hexdigest()
        helpers.bulk(self.client, [
            {"_index": self.index, "_id": f"{base}#{c['chunk_no']}", **c}
            for c in chunks
        ], refresh=True)

    # -- query --------------------------------------------------------------
    def search(self, vector, doc_type=None, group_id=None, k=8) -> list[dict]:
        filters = []
        if doc_type:
            filters.append({"term": {"doc_type": doc_type}})
        if group_id:
            filters.append({"term": {"group_id": group_id}})
        res = self.client.search(index=self.index, body={
            "size": k,
            "query": {"bool": {
                "must": [{"knn": {"embedding": {"vector": vector, "k": k}}}],
                "filter": filters,
            }},
            "_source": {"excludes": ["embedding"]},
        })
        return [{"score": h["_score"], **h["_source"]}
                for h in res["hits"]["hits"]]

    def get_chunks(self, doc_type=None, group_id=None, with_vectors=False):
        filters = []
        if doc_type:
            filters.append({"term": {"doc_type": doc_type}})
        if group_id:
            filters.append({"term": {"group_id": group_id}})
        res = self.client.search(index=self.index, body={
            "size": 500,
            "query": {"bool": {"filter": filters}} if filters
                     else {"match_all": {}},
            "_source": {} if with_vectors else {"excludes": ["embedding"]},
        })
        return [h["_source"] for h in res["hits"]["hits"]]
