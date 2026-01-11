import threading
import time

from backend.models.user_config import UserConfig
from backend.services.rag import RAGService


class SchedulerService:
    _is_polling = False
    _lock = threading.Lock()

    @staticmethod
    def start_polling(interval=60):
        with SchedulerService._lock:
            if SchedulerService._is_polling:
                print("Scheduler already polling. Skipping start.")
                return
            SchedulerService._is_polling = True

        def poll():
            while True:
                print("Polling for new documents...")
                try:
                    users = UserConfig.list_users_with_drive()
                    for user in users:
                        user_context = {
                            "uid": user.get("uid"),
                            "email": user.get("email"),
                            "openai_api_key": user.get("openai_api_key"),
                            "drive_folder_id": user.get("drive_folder_id"),
                            "google_token": user.get("google_token"),
                        }
                        if (
                            not user_context.get("openai_api_key")
                            or not user_context.get("drive_folder_id")
                            or not user_context.get("google_token")
                        ):
                            continue
                        RAGService.initialize_index(user_context)
                except Exception as e:
                    print(f"Polling error: {e}")
                time.sleep(interval)

        thread = threading.Thread(target=poll, daemon=True)
        thread.start()
