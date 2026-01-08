from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext, StorageContext
from llama_index.llms import OpenAI, Ollama
from backend.models.config import SystemConfig
import os
import json

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

    @staticmethod
    def get_pinecone_dimension(embed_model):
        dimension = os.getenv("PINECONE_DIMENSION")
        if dimension:
            try:
                return int(dimension)
            except ValueError:
                raise ValueError("PINECONE_DIMENSION must be an integer.")

        try:
            return len(embed_model.get_text_embedding("dimension probe"))
        except Exception as exc:
            raise ValueError(
                "Unable to infer embedding dimension. "
                "Set PINECONE_DIMENSION in the environment."
            ) from exc

    @classmethod
    def get_pinecone_vector_store(cls, service_context):
        api_key = os.getenv("PINECONE_API_KEY")
        environment = os.getenv("PINECONE_ENVIRONMENT") or os.getenv("PINECONE_ENV")
        index_name = os.getenv("PINECONE_INDEX_NAME")
        metric = os.getenv("PINECONE_METRIC", "cosine")

        if not api_key or not environment or not index_name:
            return None

        import pinecone
        from llama_index.vector_stores import PineconeVectorStore

        pinecone.init(api_key=api_key, environment=environment)

        if index_name not in pinecone.list_indexes():
            dimension = cls.get_pinecone_dimension(service_context.embed_model)
            pinecone.create_index(index_name, dimension=dimension, metric=metric)

        pinecone_index = pinecone.Index(index_name)
        return PineconeVectorStore(pinecone_index)

    @classmethod
    def ensure_client_secrets(cls):
        """Creates client_secrets.json from DB config if it doesn't exist."""
        config = SystemConfig.get_config()
        client_id = config.get('google_client_id')
        client_secret = config.get('google_client_secret')

        if client_id and client_secret:
            secrets_path = os.path.join(os.getcwd(), 'backend', 'credentials', 'client_secrets.json')
            os.makedirs(os.path.dirname(secrets_path), exist_ok=True)

            import json
            secrets_data = {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["http://localhost"]
                }
            }
            with open(secrets_path, 'w') as f:
                json.dump(secrets_data, f)
            return secrets_path
        return None

    @classmethod
    def resolve_credentials_path(cls):
        candidates = []
        config_path = cls.ensure_client_secrets()
        if config_path:
            candidates.append(config_path)

        candidates.extend([
            os.path.join(os.getcwd(), 'backend', 'credentials', 'client_secrets.json'),
            os.path.join(os.getcwd(), 'backend', 'credentials', 'credentials.json'),
            os.path.join(os.getcwd(), 'client_secrets.json'),
        ])

        for path in candidates:
            if path and os.path.exists(path):
                return cls.sanitize_oauth_credentials_file(path)
        return None

    @staticmethod
    def get_google_drive_reader():
        try:
            import logging
            import tempfile
            from pathlib import Path
            from llama_index import SimpleDirectoryReader
            from llama_index.download.llamahub_modules.google_drive.base import GoogleDriveReader as BaseGoogleDriveReader

            logger = logging.getLogger(__name__)

            class PatchedGoogleDriveReader(BaseGoogleDriveReader):
                def _load_data_fileids_meta(self, fileids_meta):
                    if not fileids_meta:
                        return []
                    try:
                        with tempfile.TemporaryDirectory() as temp_dir:

                            def get_metadata(filename):
                                return metadata[filename]

                            temp_dir = Path(temp_dir)
                            metadata = {}

                            for fileid_meta in fileids_meta:
                                filename = fileid_meta[2]
                                if not filename:
                                    continue
                                filepath = os.path.join(temp_dir, filename)
                                fileid = fileid_meta[0]
                                final_filepath = self._download_file(fileid, filepath)
                                if not final_filepath:
                                    continue

                                metadata[final_filepath] = {
                                    "file id": fileid_meta[0],
                                    "author": fileid_meta[1],
                                    "file name": fileid_meta[2],
                                    "mime type": fileid_meta[3],
                                    "created at": fileid_meta[4],
                                    "modified at": fileid_meta[5],
                                }

                            loader = SimpleDirectoryReader(temp_dir, file_metadata=get_metadata)
                            documents = loader.load_data()
                            for doc in documents:
                                doc.id_ = doc.metadata.get("file id", doc.id_)

                        return documents
                    except Exception as e:
                        logger.error("Patched loader error: %s", e)
                        return []

            return PatchedGoogleDriveReader
        except Exception:
            from llama_index import download_loader
            return download_loader('GoogleDriveReader')

    @classmethod
    def sanitize_oauth_credentials_file(cls, path):
        if not path or not os.path.exists(path):
            return None

        try:
            with open(path, 'r') as handle:
                data = json.load(handle)
        except Exception:
            return path

        if not isinstance(data, dict):
            return path

        if data.get('type') == 'service_account':
            return path

        oauth_key = None
        if 'web' in data:
            oauth_key = 'web'
        elif 'installed' in data:
            oauth_key = 'installed'

        if not oauth_key:
            return path

        if list(data.keys()) == [oauth_key]:
            return path

        sanitized_path = os.path.join(
            os.getcwd(), 'backend', 'credentials', 'oauth_client_sanitized.json'
        )
        os.makedirs(os.path.dirname(sanitized_path), exist_ok=True)
        with open(sanitized_path, 'w') as handle:
            json.dump({oauth_key: data[oauth_key]}, handle)
        return sanitized_path

    @classmethod
    def ensure_pydrive_client_secrets(cls, creds_path):
        """Ensure a valid client_secrets.json exists in CWD for PyDrive."""
        config = SystemConfig.get_config()
        client_id = config.get('google_client_id')
        client_secret = config.get('google_client_secret')

        oauth_data = None
        if creds_path and os.path.exists(creds_path):
            try:
                with open(creds_path, 'r') as handle:
                    data = json.load(handle)
            except Exception:
                data = None

            if isinstance(data, dict) and data.get('type') != 'service_account':
                if 'web' in data:
                    oauth_data = {'web': data['web']}
                elif 'installed' in data:
                    oauth_data = {'installed': data['installed']}
        if not oauth_data and client_id and client_secret:
            oauth_data = {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
                }
            }

        if not oauth_data:
            return None

        key = 'web' if 'web' in oauth_data else 'installed'
        client_section = oauth_data.get(key, {})
        if not client_section.get('redirect_uris'):
            client_section['redirect_uris'] = ["http://localhost"]
            oauth_data[key] = client_section

        dest_path = os.path.join(os.getcwd(), 'client_secrets.json')
        try:
            with open(dest_path, 'w') as handle:
                json.dump(oauth_data, handle)
        except Exception:
            return None
        return dest_path

    @classmethod
    def ensure_pydrive_creds_from_token(cls, token_path, pydrive_creds_path):
        if not token_path or not os.path.exists(token_path):
            return None

        try:
            with open(token_path, 'r') as handle:
                data = json.load(handle)
        except Exception:
            return None

        token = data.get('token')
        refresh_token = data.get('refresh_token')
        client_id = data.get('client_id')
        client_secret = data.get('client_secret')
        token_uri = data.get('token_uri')
        expiry = data.get('expiry')

        if not all([token, refresh_token, client_id, client_secret, token_uri]):
            return None

        token_expiry = None
        if expiry:
            try:
                from datetime import datetime, timezone
                token_expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if token_expiry.tzinfo is None:
                    token_expiry = token_expiry.replace(tzinfo=timezone.utc)
            except Exception:
                token_expiry = None

        try:
            from oauth2client.client import OAuth2Credentials
            creds = OAuth2Credentials(
                access_token=token,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                token_expiry=token_expiry,
                token_uri=token_uri,
                user_agent="internal-knowledge-assistant",
                revoke_uri="https://oauth2.googleapis.com/revoke",
                scopes=data.get("scopes"),
            )
            os.makedirs(os.path.dirname(pydrive_creds_path), exist_ok=True)
            with open(pydrive_creds_path, 'w') as handle:
                handle.write(creds.to_json())
            return pydrive_creds_path
        except Exception:
            return None

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
        creds_path = cls.resolve_credentials_path()
        token_path = cls.get_google_token_data()

        if (token_path and os.path.exists(token_path)) or (creds_path and os.path.exists(creds_path)):
            try:
                GoogleDriveReader = cls.get_google_drive_reader()

                if token_path and os.path.exists(token_path):
                    cls.ensure_pydrive_client_secrets(creds_path)
                    pydrive_creds_path = os.path.join(
                        os.getcwd(), "backend", "credentials", "pydrive_creds.txt"
                    )
                    cls.ensure_pydrive_creds_from_token(token_path, pydrive_creds_path)
                    loader_kwargs = {
                        "token_path": token_path,
                        "pydrive_creds_path": pydrive_creds_path,
                    }
                    if creds_path and os.path.exists(creds_path):
                        loader_kwargs["credentials_path"] = creds_path
                    loader = GoogleDriveReader(**loader_kwargs)
                    print("Using User OAuth Token from DB.")
                elif creds_path and os.path.exists(creds_path):
                    loader = GoogleDriveReader(credentials_path=creds_path)
                    print("Using File-based Google credentials.")
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
            vector_store = cls.get_pinecone_vector_store(service_context)
            storage_context = None
            if vector_store:
                storage_context = StorageContext.from_defaults(vector_store=vector_store)

            cls.index = VectorStoreIndex.from_documents(
                documents,
                service_context=service_context,
                storage_context=storage_context,
            )
            print("Index initialized successfully.")
        except Exception as e:
            print(f"Index initialization error: {e}")

    @classmethod
    def get_drive_file_list(cls):
        """
        Connects to Drive using current config and returns a list of filenames
        from the configured folders for verification.
        """
        creds_path = cls.resolve_credentials_path()
        token_path = cls.get_google_token_data()

        loader = None
        auth_type = "None"

        if token_path and os.path.exists(token_path):
            try:
                GoogleDriveReader = cls.get_google_drive_reader()
                cls.ensure_pydrive_client_secrets(creds_path)
                pydrive_creds_path = os.path.join(
                    os.getcwd(), "backend", "credentials", "pydrive_creds.txt"
                )
                cls.ensure_pydrive_creds_from_token(token_path, pydrive_creds_path)
                loader_kwargs = {
                    "token_path": token_path,
                    "pydrive_creds_path": pydrive_creds_path,
                }
                if creds_path and os.path.exists(creds_path):
                    loader_kwargs["credentials_path"] = creds_path
                loader = GoogleDriveReader(**loader_kwargs)
                auth_type = "User OAuth (from DB)"
            except Exception as e:
                return {'success': False, 'message': f"Failed to init User OAuth loader: {e}"}

        elif creds_path and os.path.exists(creds_path):
            try:
                GoogleDriveReader = cls.get_google_drive_reader()
                loader = GoogleDriveReader(credentials_path=creds_path)
                auth_type = "File-based Google credentials"
            except Exception as e:
                 return {'success': False, 'message': f"Failed to init credentials loader: {e}"}

        if not loader:
             return {'success': False, 'message': "No OAuth token or credentials file found."}

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
