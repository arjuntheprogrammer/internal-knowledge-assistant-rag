from typing import Any
import re

from llama_index.core.base.response.schema import Response


class RAGFormatter:
    @classmethod
    def format_markdown_response(cls, response: Any) -> str:
        response_text = cls._extract_response_text(response) or ""
        response_text = response_text.strip()

        answer_text, sources_text = cls._split_sources(response_text)
        answer_text = cls._strip_answer_label(answer_text)
        answer_text = cls._strip_leading_markdown_noise(answer_text)
        answer_text, _ = cls._split_sources(answer_text)
        if not answer_text:
            answer_text = "I'm sorry, I couldn't find any information about that in your connected documents."

        sources_block = cls._format_sources(response, sources_text)
        if re.search(r"(?m)^\s*([-*]|\d+\.)\s+", answer_text):
            formatted_answer = f"**Answer:**\n{answer_text}"
        else:
            formatted_answer = f"**Answer:** {answer_text}"
        return f"{formatted_answer}\n\n{sources_block}"

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        if isinstance(response, Response):
            return response.response or ""
        return str(response)

    @staticmethod
    def _split_sources(text: str) -> tuple[str, str]:
        if not text:
            return "", ""
        match = re.search(
            r"(?im)^[\s>*-]*\**sources\**\s*[:\-]\s*",
            text,
        )
        if not match:
            return text, ""
        return text[: match.start()].strip(), text[match.end() :].strip()

    @staticmethod
    def _strip_answer_label(text: str) -> str:
        if not text:
            return ""
        return re.sub(
            r"(?is)^(?:\s*[-*>]*\s*\**answer\**\s*[:\-]\s*)+",
            "",
            text,
        ).strip()

    @staticmethod
    def _strip_leading_markdown_noise(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"^(?:\*{1,2}|_{1,2})\s+", "", text).strip()

    @staticmethod
    def _format_sources(response: Any, sources_text: str) -> str:
        sources = []
        seen = set()
        source_nodes = getattr(response, "source_nodes", None)
        if source_nodes:
            for node_with_score in source_nodes:
                node = getattr(node_with_score, "node", None)
                if not node:
                    continue
                metadata = getattr(node, "metadata", {}) or {}
                drive_id = metadata.get("file id") or metadata.get("file_id")
                page_number = metadata.get("page_number")
                source_type = metadata.get("source")
                mime_type = metadata.get("mime_type") or metadata.get("mime type")
                label = (
                    metadata.get("file name")
                    or metadata.get("file_name")
                    or metadata.get("filename")
                )
                if not label or label in {drive_id, node.node_id}:
                    label = "Google Drive document"

                page_suffix = f" (page {page_number})" if page_number else ""
                label_with_page = f"{label}{page_suffix}"

                source_parts = [drive_id or label_with_page or node.node_id]
                if page_number:
                    source_parts.append(str(page_number))
                if source_type:
                    source_parts.append(str(source_type))
                source_key = ":".join(source_parts)
                if not source_key or source_key in seen:
                    continue
                seen.add(source_key)
                if drive_id and label_with_page:
                    url = f"https://drive.google.com/file/d/{drive_id}/view"
                    if mime_type == "application/pdf" and page_number:
                        url = f"{url}#page={page_number}"
                    sources.append(f"[{label_with_page}]({url})")
                else:
                    sources.append(label_with_page)

        if sources:
            bullets = "\n".join(f"- {source}" for source in sources)
            return f"**Sources:**\n{bullets}"

        cleaned_sources = sources_text.strip()
        if cleaned_sources:
            cleaned_sources = re.sub(
                r"(?i)^\s*\**sources\**\s*[:\-]\s*",
                "",
                cleaned_sources,
            ).strip()
            cleaned_sources = re.sub(
                r"\s*\(id:\s*[^)]+\)\s*",
                "",
                cleaned_sources,
            ).strip()
            if re.search(r"(?m)^\s*[-*]\s+", cleaned_sources):
                return f"**Sources:**\n{cleaned_sources}"
            if "," in cleaned_sources:
                items = [item.strip() for item in cleaned_sources.split(",") if item.strip()]
                bullets = "\n".join(f"- {item}" for item in items)
                return f"**Sources:**\n{bullets}" if bullets else "**Sources:** None"
            return f"**Sources:** {cleaned_sources}"

        return "**Sources:** None"
