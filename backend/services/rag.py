from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.llms import OpenAI, Ollama
from backend.models.config import SystemConfig
import os

class RAGService:
    index = None

    @classmethod
    def get_service_context(cls):
        config = SystemConfig.get_config()
        if config['llm_provider'] == 'openai':
            # Ensure API key is set
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API Key not found")
            llm = OpenAI(model=config.get('openai_model', 'gpt-3.5-turbo'))
        else:
            llm = Ollama(
                base_url=config.get('ollama_url', 'http://localhost:11434'),
                model=config.get('ollama_model', 'llama2')
            )

        return ServiceContext.from_defaults(llm=llm)

    @classmethod
    def get_google_token_data(cls):
        """Helper to get google token from DB."""
        from backend.services.db import Database
        db = Database.get_db()
        # Find the first user (likely the admin) who has a google_token
        user = db.users.find_one({'google_token': {'$exists': True, '$ne': None}})
        if user:
            # Create a temporary file or pass the data if the reader supports it.
            # LlamaIndex GoogleDriveReader currently prefers a file path.
            # We'll write to a temporary location or use a fixed name.
            token_data = user.get('google_token')
            token_path = os.path.join(os.getcwd(), 'backend', 'credentials', 'token_db.json')
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, 'w') as f:
                f.write(token_data)
            return token_path
        return None

    @classmethod
    def initialize_index(cls):
        documents = []

        # 1. Load Local Documents
        data_dir = os.path.join(os.getcwd(), 'backend', 'data')
        os.makedirs(data_dir, exist_ok=True)
        try:
            local_docs = SimpleDirectoryReader(data_dir).load_data()
            documents.extend(local_docs)
            print(f"Loaded {len(local_docs)} local documents.")
        except Exception:
            pass

        # 2. Load Google Drive Documents
        creds_dir = os.path.join(os.getcwd(), 'backend', 'credentials')
        creds_path = os.path.join(creds_dir, 'credentials.json')
        token_path = cls.get_google_token_data()

        if (token_path and os.path.exists(token_path)) or os.path.exists(creds_path):
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')

                if token_path and os.path.exists(token_path):
                     loader = GoogleDriveReader(token_path=token_path)
                     print("Using User OAuth Token from DB.")
                elif os.path.exists(creds_path):
                     loader = GoogleDriveReader(credentials_path=creds_path)
                     print("Using Service Account Credentials.")
                else:
                    loader = None

                if loader:
                    config = SystemConfig.get_config()
                    folder_ids = [f['id'] for f in config.get('drive_folders', [])]

                    for f_id in folder_ids:
                        if f_id:
                            drive_docs = loader.load_data(folder_id=f_id)
                            documents.extend(drive_docs)
                            print(f"Loaded {len(drive_docs)} documents from Drive folder {f_id}.")
            except Exception as e:
                print(f"Failed to load from Drive: {e}")


        if not documents:
            print("No documents found. Index will be empty.")
            return

        try:
            service_context = cls.get_service_context()
            cls.index = VectorStoreIndex.from_documents(documents, service_context=service_context)
            print("Index initialized successfully.")
        except Exception as e:
            print(f"Index initialization error: {e}")

    @classmethod
    def get_drive_file_list(cls):
        """
        Connects to Drive using current config and returns a list of filenames
        from the configured folders for verification.
        """
        creds_dir = os.path.join(os.getcwd(), 'backend', 'credentials')
        creds_path = os.path.join(creds_dir, 'credentials.json')
        token_path = cls.get_google_token_data()

        loader = None
        auth_type = "None"

        if token_path and os.path.exists(token_path):
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')
                loader = GoogleDriveReader(token_path=token_path)
                auth_type = "User OAuth (from DB)"
            except Exception as e:
                return {'success': False, 'message': f"Failed to init User OAuth loader: {e}"}

        elif os.path.exists(creds_path):
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')
                loader = GoogleDriveReader(credentials_path=creds_path)
                auth_type = "Service Account"
            except Exception as e:
                 return {'success': False, 'message': f"Failed to init Service Account loader: {e}"}

        if not loader:
             return {'success': False, 'message': "No credentials found via OAuth or credentials.json"}

        # Get folder IDs
        config = SystemConfig.get_config()
        folder_ids = [f['id'] for f in config.get('drive_folders', []) if f.get('id')]

        if not folder_ids:
            return {'success': True, 'files': [], 'message': f"Connected via {auth_type}, but no folders configured."}

        found_files = []
        try:
            # Check up to first 3 folders to verify access
            for f_id in folder_ids[:3]:
                # load_data might be slow; strictly speaking we should use google api client directly for 'list'
                # but let's see if we can get by with just checking trust.
                # Since the user asked for "list of documents", we'll do load_data().
                docs = loader.load_data(folder_id=f_id)
                count = len(docs)
                if count > 0:
                    # Provide snippet info
                    found_files.append(f"Folder {f_id}: Found {count} document chunks.")
                else:
                    found_files.append(f"Folder {f_id}: Empty or no access.")

            return {'success': True, 'files': found_files, 'message': f"Verified with {auth_type}"}

        except Exception as e:
            return {'success': False, 'message': f"Error accessing Drive folders: {e}"}



    @classmethod
    def query(cls, question):
        if not cls.index:
            cls.initialize_index()

        if not cls.index:
             # Fallback if still no index
             return "Knowledge base is empty. Please add documents."

        query_engine = cls.index.as_query_engine()
        response = query_engine.query(question)
        return str(response)
