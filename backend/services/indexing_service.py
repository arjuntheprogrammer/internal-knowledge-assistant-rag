"""
Background Indexing Service

This module handles asynchronous document indexing using Python threading.
It tracks indexing status per user in Firestore and provides progress updates.
"""

import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from backend.models.user_config import UserConfig


class IndexingStatus(str, Enum):
    """Status of the indexing process for a user."""
    PENDING = "PENDING"      # Initial state, never indexed
    INDEXING = "INDEXING"    # Currently processing documents
    READY = "READY"          # Indexing complete, ready for queries
    FAILED = "FAILED"        # Indexing failed with an error


class IndexingService:
    """
    Manages background document indexing for users.

    Uses threading to run indexing in the background without blocking
    the main request. Tracks status in Firestore for persistence.
    """

    _active_jobs: dict[str, threading.Thread] = {}
    _job_lock = threading.Lock()
    logger = logging.getLogger(__name__)

    @classmethod
    def get_status(cls, user_id: str) -> dict:
        """
        Get the current indexing status for a user.

        Returns:
            dict with status, message, progress, and timestamps
        """
        user = UserConfig.get_user(user_id) or {}
        status = user.get("indexing_status", IndexingStatus.PENDING)

        # Check if there's an active job running
        with cls._job_lock:
            is_active = user_id in cls._active_jobs and cls._active_jobs[user_id].is_alive()

        # If status says INDEXING but no active thread, it may have crashed
        if status == IndexingStatus.INDEXING and not is_active:
            # Check if it's been stuck for more than 10 minutes
            started_at = user.get("indexing_started_at")
            if started_at:
                try:
                    if hasattr(started_at, 'timestamp'):
                        elapsed = time.time() - started_at.timestamp()
                    else:
                        elapsed = 0
                    if elapsed > 600:  # 10 minutes
                        status = IndexingStatus.FAILED
                        cls._update_status(
                            user_id,
                            IndexingStatus.FAILED,
                            "Indexing timed out or server restarted"
                        )
                except Exception:
                    pass

        return {
            "status": status,
            "message": user.get("indexing_message", ""),
            "progress": user.get("indexing_progress", 0),
            "document_count": user.get("indexed_document_count", 0),
            "started_at": cls._format_dt(user.get("indexing_started_at")),
            "completed_at": cls._format_dt(user.get("indexing_completed_at")),
            "is_active": is_active,
        }

    @classmethod
    def start_indexing(cls, user_context: dict) -> dict:
        """
        Start background indexing for a user.

        Args:
            user_context: Dict containing uid, openai_api_key, drive_folder_id, google_token

        Returns:
            dict with success status and message
        """
        user_id = user_context.get("uid")
        if not user_id:
            return {"success": False, "message": "User ID is required"}

        # Check if already indexing
        with cls._job_lock:
            if user_id in cls._active_jobs and cls._active_jobs[user_id].is_alive():
                return {
                    "success": False,
                    "message": "Indexing is already in progress",
                    "status": IndexingStatus.INDEXING
                }

        # Validate required fields
        if not user_context.get("openai_api_key"):
            return {"success": False, "message": "OpenAI API key is required"}
        if not user_context.get("drive_folder_id"):
            return {"success": False, "message": "Drive folder ID is required"}
        if not user_context.get("google_token"):
            return {"success": False, "message": "Google Drive is not authorized"}

        # Update status to INDEXING
        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Starting document indexing...",
            progress=0
        )
        UserConfig.update_config(user_id, {"indexing_started_at": datetime.utcnow()})

        # Start background thread
        thread = threading.Thread(
            target=cls._run_indexing,
            args=(user_context.copy(),),
            daemon=True,
            name=f"indexing-{user_id}"
        )

        with cls._job_lock:
            cls._active_jobs[user_id] = thread

        thread.start()
        cls.logger.info("Started background indexing for user %s", user_id)

        return {
            "success": True,
            "message": "Indexing started",
            "status": IndexingStatus.INDEXING
        }

    @classmethod
    def _run_indexing(cls, user_context: dict):
        """
        Run the indexing process in a background thread.

        This method handles all the heavy lifting:
        1. Load documents from Google Drive
        2. Process and chunk documents
        3. Generate embeddings
        4. Store in vector database
        """
        user_id = user_context.get("uid")

        try:
            # Import here to avoid circular imports
            from backend.services.rag import RAGService

            cls._update_status(
                user_id,
                IndexingStatus.INDEXING,
                "Connecting to Google Drive...",
                progress=10
            )

            # Run the actual indexing
            cls._run_indexing_with_progress(user_context, user_id)

            # Mark as complete
            cls._update_status(
                user_id,
                IndexingStatus.READY,
                "Indexing complete! You can now chat with your documents.",
                progress=100
            )
            UserConfig.update_config(user_id, {"indexing_completed_at": datetime.utcnow()})
            cls.logger.info("Indexing completed successfully for user %s", user_id)

        except Exception as e:
            cls.logger.error("Indexing failed for user %s: %s", user_id, str(e))
            cls._update_status(
                user_id,
                IndexingStatus.FAILED,
                f"Indexing failed: {str(e)}"
            )
        finally:
            # Clean up the job reference
            with cls._job_lock:
                cls._active_jobs.pop(user_id, None)

    @classmethod
    def _run_indexing_with_progress(cls, user_context: dict, user_id: str):
        """
        Run indexing with progress updates.
        """
        import os
        from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
        from llama_index.core.node_parser import SentenceSplitter

        from backend.services.rag import RAGService
        from backend.services.rag import rag_google_drive
        from backend.services.rag.catalog import (
            annotate_documents,
            build_document_catalog,
            log_vector_store_count,
        )

        documents = []

        # Load local documents
        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Loading local documents...",
            progress=15
        )

        data_dir = os.path.join(os.getcwd(), "backend", "data")
        os.makedirs(data_dir, exist_ok=True)
        try:
            local_docs = SimpleDirectoryReader(data_dir).load_data()
            documents.extend(local_docs)
            cls.logger.info("Loaded %d local documents", len(local_docs))
        except Exception:
            pass

        # Load Google Drive documents
        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Downloading documents from Google Drive...",
            progress=25
        )

        drive_docs = rag_google_drive.load_google_drive_documents(
            user_id=user_id,
            drive_folder_id=user_context.get("drive_folder_id"),
            token_json=user_context.get("google_token"),
        )
        documents.extend(drive_docs)

        total_docs = len(documents)
        if not documents:
            cls._update_status(
                user_id,
                IndexingStatus.READY,
                "No documents found. Add files to your Drive folder and re-index.",
                progress=100
            )
            UserConfig.update_config(user_id, {"indexed_document_count": 0})
            return

        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            f"Processing {total_docs} documents...",
            progress=40
        )

        # Annotate documents
        annotate_documents(documents, user_id=user_id)
        RAGService._document_catalog_by_user[user_id] = build_document_catalog(documents)

        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Generating embeddings...",
            progress=50
        )

        # Get service context and vector store
        settings = RAGService.get_service_context(
            user_context.get("openai_api_key"), user_id=user_id
        )
        vector_store = RAGService.get_vector_store(user_id)

        # Clear existing records for this user
        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Clearing old index data...",
            progress=55
        )

        if vector_store:
            try:
                client = getattr(vector_store, "client", None)
                collection_name = getattr(vector_store, "collection_name", None)
                if client and collection_name:
                    client.delete(
                        collection_name=collection_name,
                        filter=f"user_id == '{user_id}'"
                    )
                    cls.logger.info("Cleared existing records for user %s", user_id)
            except Exception as del_err:
                cls.logger.warning("Could not clear existing records: %s", del_err)

        storage_context = None
        if vector_store:
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Building search index...",
            progress=65
        )

        # Chunk documents
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=60)
        RAGService._bm25_nodes_by_user[user_id] = splitter.get_nodes_from_documents(documents)

        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Uploading to vector store...",
            progress=80
        )

        # Create the index
        RAGService._index_by_user[user_id] = VectorStoreIndex.from_documents(
            documents,
            callback_manager=settings.callback_manager,
            storage_context=storage_context,
            transformations=[splitter],
        )

        cls._update_status(
            user_id,
            IndexingStatus.INDEXING,
            "Finalizing...",
            progress=95
        )

        # Log vector store count
        if vector_store:
            log_vector_store_count(vector_store)

        # Update document count
        UserConfig.update_config(user_id, {"indexed_document_count": total_docs})
        cls.logger.info("Index initialized with %d documents for user %s", total_docs, user_id)

    @classmethod
    def _update_status(
        cls,
        user_id: str,
        status: IndexingStatus,
        message: str,
        progress: Optional[int] = None
    ):
        """Update the indexing status in Firestore."""
        update_data = {
            "indexing_status": status,
            "indexing_message": message,
        }
        if progress is not None:
            update_data["indexing_progress"] = progress

        UserConfig.update_config(user_id, update_data)

    @classmethod
    def _format_dt(cls, value):
        """Format datetime for JSON response."""
        if not value:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @classmethod
    def is_ready(cls, user_id: str) -> bool:
        """Check if indexing is complete and ready for queries."""
        status_info = cls.get_status(user_id)
        return status_info["status"] == IndexingStatus.READY

    @classmethod
    def cancel_indexing(cls, user_id: str) -> dict:
        """
        Cancel an in-progress indexing job.
        Note: This only prevents future work, doesn't stop current operations.
        """
        with cls._job_lock:
            if user_id in cls._active_jobs:
                # We can't really stop a thread, but we can mark it as failed
                cls._update_status(
                    user_id,
                    IndexingStatus.FAILED,
                    "Indexing was cancelled"
                )
                cls._active_jobs.pop(user_id, None)
                return {"success": True, "message": "Indexing cancelled"}

        return {"success": False, "message": "No active indexing job found"}

    @classmethod
    def reset_indexing(cls, user_id: str):
        """
        Reset indexing status and clear all indexing metadata for a user.
        """
        cls._update_status(
            user_id,
            IndexingStatus.PENDING,
            "No documents indexed.",
            progress=0
        )
        UserConfig.update_config(user_id, {
            "indexing_started_at": None,
            "indexing_completed_at": None,
            "indexed_document_count": 0
        })
