import threading
import time
from backend.services.rag import RAGService


class SchedulerService:
    @staticmethod
    def start_polling(interval=60):
        def poll():
            while True:
                print("Polling for new documents...")
                try:
                    # In a real app, check for changes before re-indexing
                    RAGService.initialize_index()
                except Exception as e:
                    print(f"Polling error: {e}")
                time.sleep(interval)

        thread = threading.Thread(target=poll, daemon=True)
        thread.start()
