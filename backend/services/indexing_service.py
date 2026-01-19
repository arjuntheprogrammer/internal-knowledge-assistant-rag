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
from backend.utils.time_utils import format_dt


class IndexingStatus(str, Enum):
    """Status of the indexing process for a user."""

    PENDING = "PENDING"  # Initial state, never indexed
    PROCESSING = "PROCESSING"  # Currently processing documents
    COMPLETED = "COMPLETED"  # Indexing complete, ready for queries
    FAILED = "FAILED"  # Indexing failed with an error


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
    def get_status(cls, user_id: str, user: Optional[dict] = None) -> dict:
        """
        Get the current indexing status for a user.

        Returns:
            dict with status, message, progress, and timestamps
        """
        if user is None:
            user = UserConfig.get_user(user_id) or {}
        status = user.get("indexing_status", IndexingStatus.PENDING)

        # Check if there's an active job running
        with cls._job_lock:
            is_active = (
                user_id in cls._active_jobs and cls._active_jobs[user_id].is_alive()
            )

        # If status says PROCESSING but no active thread, it may have crashed
        if status == IndexingStatus.PROCESSING and not is_active:
            # Check if it's been stuck for more than 10 minutes
            started_at = user.get("indexing_started_at")
            if started_at:
                try:
                    if hasattr(started_at, "timestamp"):
                        elapsed = time.time() - started_at.timestamp()
                    else:
                        elapsed = 0
                    if elapsed > 1800:  # 30 minutes
                        status = IndexingStatus.FAILED
                        cls._update_status(
                            user_id, IndexingStatus.FAILED, "Indexing timed out"
                        )
                except Exception:
                    pass

        return {
            "status": status,
            "message": user.get("indexing_message", ""),
            "progress": user.get("indexing_progress", 0),
            "document_count": user.get("indexed_document_count", 0),
            "file_count": (
                user.get("indexed_file_count")
                if user.get("indexed_file_count") is not None
                else user.get("drive_file_count", 0)
            ),
            "started_at": format_dt(user.get("indexing_started_at")),
            "completed_at": format_dt(user.get("indexing_completed_at")),
            "is_active": is_active,
        }

    @classmethod
    def start_indexing(
        cls,
        user_context: dict,
        force: bool = False,
        silent: bool = False,
        inline: bool = False,
    ) -> dict:
        """
        Start background indexing for a user.

        Args:
            user_context: Dict containing uid, openai_api_key, drive_folder_id, google_token
            force: If True, re-index even if already COMPLETED.
            silent: If True, don't update status to PROCESSING if already COMPLETED.
            inline: If True, run indexing on the request thread.
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
                    "status": IndexingStatus.PROCESSING,
                }

        # Check if already indexed and not forced
        current_status = cls.get_status(user_id)
        if current_status["status"] == IndexingStatus.COMPLETED and not force:
            if not silent:
                # Manual request shouldn't re-index if already done
                return {
                    "success": True,
                    "message": "Documents already connected",
                    "status": IndexingStatus.COMPLETED,
                }
            # Silent background sync: Proceed to cross-check files without updating status

        # Validate required fields
        if not user_context.get("openai_api_key"):
            return {"success": False, "message": "OpenAI API key is required"}
        if not user_context.get("drive_folder_id"):
            return {"success": False, "message": "Drive folder ID is required"}
        if not user_context.get("google_token"):
            return {"success": False, "message": "Google Drive is not authorized"}

        if inline and silent:
            # Inline runs should always update status for the user-facing flow.
            silent = False

        # Update status to PROCESSING (unless silent and already completed)
        if not (silent and current_status["status"] == IndexingStatus.COMPLETED):
            cls._update_status(
                user_id,
                IndexingStatus.PROCESSING,
                "Getting your documents ready...",
                progress=0,
            )

        from backend.utils.time_utils import utc_now

        UserConfig.update_config(user_id, {"indexing_started_at": utc_now()})

        if inline:
            with cls._job_lock:
                cls._active_jobs[user_id] = threading.current_thread()
            cls.logger.info("Started inline indexing for user %s", user_id)
            cls._run_indexing(user_context.copy(), silent)
            final_status = cls.get_status(user_id)
            success = final_status["status"] == IndexingStatus.COMPLETED
            return {
                "success": success,
                "message": final_status.get("message") or "Indexing finished",
                "status": final_status["status"],
            }

        # Start background thread
        thread = threading.Thread(
            target=cls._run_indexing,
            args=(user_context.copy(), silent),
            daemon=True,
            name=f"indexing-{user_id}",
        )

        with cls._job_lock:
            cls._active_jobs[user_id] = thread

        thread.start()
        cls.logger.info(
            "Started %s indexing for user %s",
            "silent" if silent else "standard",
            user_id,
        )

        return {
            "success": True,
            "message": "Indexing started",
            "status": IndexingStatus.PROCESSING,
        }

    @classmethod
    def _run_indexing(cls, user_context: dict, silent: bool = False):
        """
        Run the indexing process in a background thread by calling RAGService.
        """
        user_id = user_context.get("uid")
        from backend.utils.time_utils import utc_now

        try:
            from backend.services.rag import RAGService

            def on_progress(msg, progress):
                if not silent:
                    cls._update_status(
                        user_id, IndexingStatus.PROCESSING, msg, progress=progress
                    )
                else:
                    cls.logger.info(
                        f"Silent indexing user {user_id}: {msg} ({progress}%)"
                    )

            # Run the actual indexing core
            documents = RAGService.initialize_index(
                user_context, on_progress=on_progress
            )

            if documents:
                total_docs = len(documents)
                file_count = cls._count_unique_files(documents)

                cls._update_status(
                    user_id,
                    IndexingStatus.COMPLETED,
                    "Indexing complete! You can now chat with your documents.",
                    progress=100,
                )
                UserConfig.update_config(
                    user_id,
                    {
                        "indexing_completed_at": utc_now(),
                        "indexed_document_count": total_docs,
                        "indexed_file_count": file_count,
                        "drive_file_count": file_count,
                    },
                )
            else:
                # initialize_index handles its own status if no docs found,
                # but we ensure consistency here.
                cls._update_status(
                    user_id,
                    IndexingStatus.COMPLETED,
                    "No documents found or already indexed.",
                    progress=100,
                )

            cls.logger.info("Indexing completed successfully for user %s", user_id)

        except Exception as e:
            cls.logger.error("Indexing failed for user %s: %s", user_id, str(e))
            cls._update_status(
                user_id, IndexingStatus.FAILED, f"Indexing failed: {str(e)}"
            )
        finally:
            with cls._job_lock:
                cls._active_jobs.pop(user_id, None)

    @classmethod
    def _update_status(
        cls,
        user_id: str,
        status: IndexingStatus,
        message: str,
        progress: Optional[int] = None,
    ):
        """Update the indexing status in Firestore."""
        update_data = {
            "indexing_status": status,
            "indexing_message": message,
        }
        if progress is not None:
            update_data["indexing_progress"] = progress

        UserConfig.update_config(user_id, update_data)

    @staticmethod
    def _count_unique_files(documents) -> int:
        file_ids = set()
        for doc in documents:
            metadata = getattr(doc, "metadata", {}) or {}
            file_id = (
                metadata.get("file id")
                or metadata.get("file_id")
                or metadata.get("file_name")
                or metadata.get("filename")
                or metadata.get("file_path")
            )
            if file_id:
                file_ids.add(str(file_id))
        return len(file_ids)

    @classmethod
    def is_ready(cls, user_id: str) -> bool:
        """Check if indexing is complete and ready for queries."""
        status_info = cls.get_status(user_id)
        return status_info["status"] == IndexingStatus.COMPLETED

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
                    user_id, IndexingStatus.FAILED, "Indexing was cancelled"
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
            user_id, IndexingStatus.PENDING, "Database not built.", progress=0
        )
        UserConfig.update_config(
            user_id,
            {
                "indexing_started_at": None,
                "indexing_completed_at": None,
                "indexed_document_count": 0,
                "indexed_file_count": 0,
            },
        )
