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
        # Requires credentials.json in backend/credentials/
        creds_dir = os.path.join(os.getcwd(), 'backend', 'credentials')
        creds_path = os.path.join(creds_dir, 'credentials.json')
        token_path = os.path.join(creds_dir, 'token.json')

        drive_creds = None

        # Try loading user token first (OAuth)
        if os.path.exists(token_path):
             # LlamaIndex GoogleDriveReader usually expects a file path for Service Account
             # OR it can take 'credentials' object if we modify it, but standard usage
             # often points to credentials.json.
             # However, we can use the 'token_path' if the reader supports it,
             # OR we might need to use the GoogleDriveReader's logic.
             # Actually, LlamaIndex `GoogleDriveReader` uses `credentials_path` for service account
             # OR `token_path` for user creds if we check the source/docs.
             # Let's try passing the token path.
             pass

        if os.path.exists(creds_path) or os.path.exists(token_path):
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')

                # Check for token.json first (User Auth)
                if os.path.exists(token_path):
                     loader = GoogleDriveReader(token_path=token_path)
                     print("Using User OAuth Token.")
                # Fallbck to credentials.json (Service Account)
                elif os.path.exists(creds_path):
                     loader = GoogleDriveReader(credentials_path=creds_path)
                     print("Using Service Account Credentials.")
                else:
                    loader = None

                if loader:
                    # Get folder IDs from config
                    config = SystemConfig.get_config()
                    folder_ids = [f['id'] for f in config.get('drive_folders', [])]

                    if folder_ids:
                        drive_docs = loader.load_data(folder_id=folder_ids[0]) # Simplified for first folder
                        documents.extend(drive_docs)
                        print(f"Loaded {len(drive_docs)} documents from Drive.")
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
        # Load credentials setup
        creds_dir = os.path.join(os.getcwd(), 'backend', 'credentials')
        creds_path = os.path.join(creds_dir, 'credentials.json')
        token_path = os.path.join(creds_dir, 'token.json')

        loader = None
        auth_type = "None"

        # Check for token.json first (User Auth)
        if os.path.exists(token_path):
             # For simpler list/verification we might need raw Google API,
             # but to stick with llama-hub, we can try to "load" and just peek at metadata.
             # However, load_data returns Document objects which contain text.
             # For a quick check, this is "okay" but might be slow if docs are huge.
             # Given we just need verification, we can catch the success.
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')
                loader = GoogleDriveReader(token_path=token_path)
                auth_type = "User OAuth"
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
