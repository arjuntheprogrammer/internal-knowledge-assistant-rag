from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        vector_retriever,
        bm25_retriever,
        max_results,
        callback_manager,
        vector_weight=1.0,
        bm25_weight=1.0,
    ):
        super().__init__(callback_manager=callback_manager)
        self._vector_retriever = vector_retriever
        self._bm25_retriever = bm25_retriever
        self._max_results = max_results
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight

    def _get_prompt_modules(self):
        return {}

    def _retrieve(self, query_bundle: QueryBundle):
        vector_nodes = self._vector_retriever.retrieve(query_bundle)
        bm25_nodes = []
        if self._bm25_retriever is not None:
            bm25_nodes = self._bm25_retriever.retrieve(query_bundle)
        merged = {}

        def add_nodes(nodes, weight):
            for node in nodes:
                score = (node.score or 0.0) * weight
                key = getattr(node.node, "node_id", None) or getattr(
                    node.node, "hash", None
                )
                if key is None:
                    key = id(node.node)
                existing = merged.get(key)
                if existing is None or score > (existing.score or 0.0):
                    merged[key] = NodeWithScore(node=node.node, score=score)

        add_nodes(vector_nodes, self._vector_weight)
        if bm25_nodes:
            add_nodes(bm25_nodes, self._bm25_weight)

        results = sorted(
            merged.values(), key=lambda item: item.score or 0.0, reverse=True
        )
        if self._max_results:
            return results[: self._max_results]
        return results
