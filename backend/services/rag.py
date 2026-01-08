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
        creds_path = os.path.join(os.getcwd(), 'backend', 'credentials', 'credentials.json')
        if os.path.exists(creds_path):
            try:
                from llama_index import download_loader
                GoogleDriveReader = download_loader('GoogleDriveReader')
                loader = GoogleDriveReader(credentials_path=creds_path)

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
    def query(cls, question):
        if not cls.index:
            cls.initialize_index()

        if not cls.index:
             # Fallback if still no index
             return "Knowledge base is empty. Please add documents."

        query_engine = cls.index.as_query_engine()
        response = query_engine.query(question)
        return str(response)
