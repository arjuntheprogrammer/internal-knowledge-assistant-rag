import logging
import threading
import time

from backend.models.user_config import UserConfig
from backend.utils.user_context import build_user_context, is_user_context_ready


class SchedulerService:
    _is_polling = False
    _lock = threading.Lock()
    _last_checksums = {}  # {user_id: checksum}
    logger = logging.getLogger(__name__)

    @staticmethod
    def start_polling(interval=3600):
        """
        Start background polling for Drive changes.

        Args:
            interval: Seconds between polls. Default is 1 hour (3600 seconds).
        """
        with SchedulerService._lock:
            if SchedulerService._is_polling:
                SchedulerService.logger.info(
                    "Scheduler already polling. Skipping start."
                )
                return
            SchedulerService._is_polling = True

        def poll():
            while True:
                SchedulerService.logger.info("Polling for Drive changes...")
                try:
                    users = UserConfig.list_users_with_drive()
                    for user in users:
                        user_context = build_user_context(
                            user.get("uid"),
                            email=user.get("email"),
                            user_config=user,
                        )
                        if not is_user_context_ready(user_context):
                            continue

                        user_id = user_context.get("uid")

                        # Check if folder has changed before indexing
                        if not SchedulerService._has_folder_changed(user_context):
                            SchedulerService.logger.debug(
                                "No changes detected for user %s, skipping indexing.",
                                user_id,
                            )
                            continue

                        SchedulerService.logger.info(
                            "Changes detected for user %s, starting silent indexing.",
                            user_id,
                        )

                        # Use IndexingService to ensure status is tracked and jobs are locked
                        # We use silent=True so that if the user is already COMPLETED, it doesn't
                        # reset their progress to 0 and show the "Connecting" banner.
                        from backend.services.indexing_service import IndexingService

                        IndexingService.start_indexing(
                            user_context, silent=True)

                except Exception as e:
                    SchedulerService.logger.error("Polling error: %s", e)
                time.sleep(interval)

        thread = threading.Thread(target=poll, daemon=True)
        thread.start()
        SchedulerService.logger.info(
            "Background scheduler started. Polling every %s seconds.", interval
        )

    @classmethod
    def _has_folder_changed(cls, user_context):
        """
        Check if the user's Drive folder/files have changed since last check.

        Returns True if:
        - This is the first check for this user
        - The folder/files checksum has changed
        - We couldn't get a checksum (fail-open to avoid missing updates)
        """
        from backend.services.rag.rag_google_drive import get_files_checksum

        user_id = user_context.get("uid")
        drive_file_ids = user_context.get("drive_file_ids") or []
        token_json = user_context.get("google_token")

        if not drive_file_ids:
            # No drive files configured
            return False

        # Get current checksum for selected files
        current_checksum = get_files_checksum(
            user_id=user_id, file_ids=drive_file_ids, token_json=token_json
        )

        # If we couldn't get a checksum, assume changes (fail-open)
        if current_checksum is None:
            cls.logger.warning(
                "Could not get checksum for user %s, will re-index to be safe.", user_id
            )
            return True

        # Get last known checksum
        last_checksum = cls._last_checksums.get(user_id)

        # First time seeing this user
        if last_checksum is None:
            cls._last_checksums[user_id] = current_checksum
            cls.logger.info(
                "First checksum for user %s: %s", user_id, current_checksum[:8]
            )
            return True  # First run, need to index

        # Compare checksums
        if current_checksum != last_checksum:
            cls._last_checksums[user_id] = current_checksum
            cls.logger.info(
                "Checksum changed for user %s: %s -> %s",
                user_id,
                last_checksum[:8],
                current_checksum[:8],
            )
            return True

        # No change
        return False

    @classmethod
    def clear_user_checksum(cls, user_id):
        """Clear the cached checksum for a user (e.g., when they manually re-index)."""
        cls._last_checksums.pop(user_id, None)
