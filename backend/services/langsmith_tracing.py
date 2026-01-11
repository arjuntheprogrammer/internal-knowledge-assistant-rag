import os
import logging
from typing import Any, Dict, Optional

from llama_index.core.callbacks.base import BASE_TRACE_EVENT
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.callbacks.token_counting import get_llm_token_counts
from llama_index.core.utilities.token_counting import TokenCounter
from llama_index.core.utils import get_tokenizer

try:
    from langsmith import Client
except Exception:  # pragma: no cover - optional dependency
    Client = None

logger = logging.getLogger(__name__)

ALLOWED_EVENTS = {
    CBEventType.QUERY,
    CBEventType.RETRIEVE,
    CBEventType.SYNTHESIZE,
    CBEventType.LLM,
    CBEventType.EMBEDDING,
    CBEventType.CHUNKING,
}

RUN_TYPE_MAP = {
    CBEventType.QUERY: "chain",
    CBEventType.RETRIEVE: "retriever",
    CBEventType.SYNTHESIZE: "chain",
    CBEventType.LLM: "llm",
    CBEventType.EMBEDDING: "embedding",
    CBEventType.CHUNKING: "chain",
}


def get_langsmith_callback_handler(metadata: Optional[Dict[str, Any]] = None) -> Optional["LangSmithCallbackHandler"]:
    if Client is None:
        return None
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() in {
        "1",
        "true",
        "yes",
    }
    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    if not tracing_enabled or not api_key:
        return None
    endpoint = os.getenv("LANGCHAIN_ENDPOINT") or os.getenv("LANGSMITH_ENDPOINT")
    project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT") or "internal-knowledge-assistant"
    client = Client(api_key=api_key, api_url=endpoint)
    return LangSmithCallbackHandler(client=client, project_name=project, metadata=metadata)


class LangSmithCallbackHandler(BaseCallbackHandler):
    def __init__(
        self,
        client: "Client",
        project_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            event_starts_to_ignore=[e for e in CBEventType if e not in ALLOWED_EVENTS],
            event_ends_to_ignore=[e for e in CBEventType if e not in ALLOWED_EVENTS],
        )
        self.client = client
        self.project_name = project_name
        self.metadata = metadata or {}
        self._run_ids: Dict[str, str] = {}
        self._trace_run_id: Optional[str] = None
        self._last_response_text: Optional[str] = None
        self._usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self._token_counter = TokenCounter(tokenizer=get_tokenizer())

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        if not trace_id:
            return
        self._last_response_text = None
        self._usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        try:
            # Add metadata to the root run
            run = self.client.create_run(
                name=trace_id,
                inputs={},
                run_type="chain",
                project_name=self.project_name,
                extra={"metadata": self.metadata} if self.metadata else None,
            )
            self._trace_run_id = run.id
            self._run_ids[BASE_TRACE_EVENT] = run.id
        except Exception as exc:
            logger.debug("LangSmith trace start failed: %s", exc)

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._trace_run_id:
            return
        outputs: Dict[str, Any] = {}
        if self._last_response_text is not None:
            outputs["response"] = self._last_response_text
        if self._usage_totals["total_tokens"] > 0:
            outputs["usage_metadata"] = dict(self._usage_totals)
        try:
            self.client.update_run(
                self._trace_run_id, outputs=outputs if outputs else {}
            )
        except Exception as exc:
            logger.debug("LangSmith trace end failed: %s", exc)

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        payload = payload or {}
        inputs = self._build_inputs(event_type, payload)
        parent_run_id = self._run_ids.get(parent_id)
        if parent_run_id is None and self._trace_run_id:
            parent_run_id = self._trace_run_id
        try:
            run = self.client.create_run(
                name=event_type.value,
                inputs=inputs,
                run_type=RUN_TYPE_MAP.get(event_type, "chain"),
                project_name=self.project_name,
                parent_run_id=parent_run_id,
                extra={"metadata": self.metadata} if self.metadata else None,
            )
            self._run_ids[event_id] = run.id
        except Exception as exc:
            logger.debug("LangSmith run start failed: %s", exc)
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        payload = payload or {}
        run_id = self._run_ids.get(event_id)
        if not run_id:
            return
        outputs = self._build_outputs(event_type, payload)
        error = payload.get(EventPayload.EXCEPTION)

        response_text = outputs.get("response")
        if event_type in {CBEventType.QUERY, CBEventType.SYNTHESIZE} and response_text:
            self._last_response_text = response_text
        if event_type == CBEventType.LLM and response_text:
            self._last_response_text = response_text
        if event_type == CBEventType.LLM:
            usage_metadata = outputs.get("usage_metadata")
            if usage_metadata:
                self._usage_totals["input_tokens"] += usage_metadata.get(
                    "input_tokens", 0
                )
                self._usage_totals["output_tokens"] += usage_metadata.get(
                    "output_tokens", 0
                )
                self._usage_totals["total_tokens"] += usage_metadata.get(
                    "total_tokens", 0
                )
        try:
            self.client.update_run(
                run_id, outputs=outputs, error=str(error) if error else None
            )
        except Exception as exc:
            logger.debug("LangSmith run end failed: %s", exc)

    def _build_inputs(self, event_type: CBEventType, payload: Dict[str, Any]) -> Dict[str, Any]:
        if event_type == CBEventType.LLM:
            messages = payload.get(EventPayload.MESSAGES)
            prompt = payload.get(EventPayload.PROMPT)
            if messages:
                return {"messages": self._serialize_messages(messages)}
            if prompt:
                return {"prompt": str(prompt)}
        if event_type in {CBEventType.QUERY, CBEventType.RETRIEVE}:
            query = payload.get(EventPayload.QUERY_STR)
            if query:
                return {"query": str(query)}
        if event_type == CBEventType.RETRIEVE:
            top_k = payload.get(EventPayload.TOP_K)
            if top_k is not None:
                return {"top_k": top_k}
        if event_type == CBEventType.EMBEDDING:
            chunks = payload.get(EventPayload.CHUNKS) or []
            return {"num_chunks": len(chunks), "text_samples": [str(c)[:50] for c in chunks[:3]]}
        if event_type == CBEventType.CHUNKING:
            docs = payload.get(EventPayload.DOCUMENTS) or []
            return {"num_documents": len(docs)}
        return {}

    def _build_outputs(self, event_type: CBEventType, payload: Dict[str, Any]) -> Dict[str, Any]:
        if event_type == CBEventType.LLM:
            response = payload.get(EventPayload.RESPONSE) or payload.get(
                EventPayload.COMPLETION
            )
            outputs = {"response": self._extract_response_text(response)}
            usage_metadata = self._build_usage_metadata(payload)
            if usage_metadata:
                outputs["usage_metadata"] = usage_metadata
            return outputs
        if event_type in {CBEventType.QUERY, CBEventType.SYNTHESIZE}:
            response = payload.get(EventPayload.RESPONSE)
            if response is not None:
                return {"response": self._extract_response_text(response)}
        if event_type == CBEventType.RETRIEVE:
            nodes = payload.get(EventPayload.NODES) or []
            return {"nodes": self._serialize_nodes(nodes)}
        if event_type == CBEventType.EMBEDDING:
            embeddings = payload.get(EventPayload.EMBEDDINGS) or []
            return {"num_embeddings": len(embeddings)}
        if event_type == CBEventType.CHUNKING:
            chunks = payload.get(EventPayload.CHUNKS) or []
            return {"num_chunks": len(chunks)}
        return {}

    def _build_usage_metadata(self, payload: Dict[str, Any]) -> Optional[Dict[str, int]]:
        try:
            counting_payload = dict(payload)
            if (
                EventPayload.PROMPT in counting_payload
                and EventPayload.COMPLETION not in counting_payload
                and EventPayload.RESPONSE in counting_payload
            ):
                counting_payload[EventPayload.COMPLETION] = counting_payload[
                    EventPayload.RESPONSE
                ]
            token_counts = get_llm_token_counts(
                token_counter=self._token_counter, payload=counting_payload
            )
        except Exception as exc:
            logger.debug("LangSmith token count failed: %s", exc)
            return None
        return {
            "input_tokens": token_counts.prompt_token_count,
            "output_tokens": token_counts.completion_token_count,
            "total_tokens": token_counts.total_token_count,
        }

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        if response is None:
            return ""
        message = getattr(response, "message", None)
        if message is not None and getattr(message, "content", None):
            return str(message.content)
        text = getattr(response, "text", None)
        if text:
            return str(text)
        raw = getattr(response, "response", None)
        if raw:
            return str(raw)
        return str(response)

    @staticmethod
    def _serialize_messages(messages: Any) -> list[dict[str, Any]]:
        serialized = []
        for message in messages:
            role = getattr(message, "role", None)
            role_value = getattr(role, "value", role)
            serialized.append(
                {
                    "role": str(role_value) if role_value is not None else None,
                    "content": getattr(message, "content", None),
                }
            )
        return serialized

    @staticmethod
    def _serialize_nodes(nodes: Any) -> list[dict[str, Any]]:
        serialized = []
        for node_with_score in nodes:
            node = getattr(node_with_score, "node", None)
            if not node:
                continue

            metadata = getattr(node, "metadata", {}) or {}
            score = getattr(node_with_score, "score", None)
            text = ""
            if hasattr(node, "get_content"):
                text = node.get_content()

            serialized.append(
                {
                    "id": getattr(node, "node_id", None),
                    "score": score,
                    "text_preview": text[:200] + "..." if len(text) > 200 else text,
                    "metadata": metadata,
                }
            )
        return serialized
