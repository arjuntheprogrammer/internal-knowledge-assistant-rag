import json
import os

from backend.models.config import SystemConfig


def ensure_client_secrets():
    """Creates client_secrets.json from DB config if it doesn't exist."""
    config = SystemConfig.get_config()
    client_id = config.get("google_client_id")
    client_secret = config.get("google_client_secret")

    if client_id and client_secret:
        secrets_path = os.path.join(
            os.getcwd(), "backend", "credentials", "client_secrets.json"
        )
        os.makedirs(os.path.dirname(secrets_path), exist_ok=True)

        secrets_data = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost"],
            }
        }
        with open(secrets_path, "w") as f:
            json.dump(secrets_data, f)
        return secrets_path
    return None


def sanitize_oauth_credentials_file(path):
    if not path or not os.path.exists(path):
        return None

    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except Exception:
        return path

    if not isinstance(data, dict):
        return path

    if data.get("type") == "service_account":
        return path

    oauth_key = None
    if "web" in data:
        oauth_key = "web"
    elif "installed" in data:
        oauth_key = "installed"

    if not oauth_key:
        return path

    if list(data.keys()) == [oauth_key]:
        return path

    sanitized_path = os.path.join(
        os.getcwd(), "backend", "credentials", "oauth_client_sanitized.json"
    )
    os.makedirs(os.path.dirname(sanitized_path), exist_ok=True)
    with open(sanitized_path, "w") as handle:
        json.dump({oauth_key: data[oauth_key]}, handle)
    return sanitized_path


def resolve_credentials_path():
    candidates = []
    config_path = ensure_client_secrets()
    if config_path:
        candidates.append(config_path)

    candidates.extend(
        [
            os.path.join(os.getcwd(), "backend", "credentials", "client_secrets.json"),
            os.path.join(os.getcwd(), "backend", "credentials", "credentials.json"),
            os.path.join(os.getcwd(), "client_secrets.json"),
        ]
    )

    for path in candidates:
        if path and os.path.exists(path):
            return sanitize_oauth_credentials_file(path)
    return None


def get_google_drive_reader():
    try:
        import logging
        import tempfile
        from pathlib import Path
        from llama_index import SimpleDirectoryReader
        from llama_index.download.llamahub_modules.google_drive.base import (
            GoogleDriveReader as BaseGoogleDriveReader,
        )

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

                        loader = SimpleDirectoryReader(
                            temp_dir, file_metadata=get_metadata
                        )
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

        return download_loader("GoogleDriveReader")


def ensure_pydrive_client_secrets(creds_path):
    """Ensure a valid client_secrets.json exists in CWD for PyDrive."""
    config = SystemConfig.get_config()
    client_id = config.get("google_client_id")
    client_secret = config.get("google_client_secret")

    oauth_data = None
    if creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path, "r") as handle:
                data = json.load(handle)
        except Exception:
            data = None

        if isinstance(data, dict) and data.get("type") != "service_account":
            if "web" in data:
                oauth_data = {"web": data["web"]}
            elif "installed" in data:
                oauth_data = {"installed": data["installed"]}
    if not oauth_data and client_id and client_secret:
        oauth_data = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            }
        }

    if not oauth_data:
        return None

    key = "web" if "web" in oauth_data else "installed"
    client_section = oauth_data.get(key, {})
    if not client_section.get("redirect_uris"):
        client_section["redirect_uris"] = ["http://localhost"]
        oauth_data[key] = client_section

    dest_path = os.path.join(os.getcwd(), "client_secrets.json")
    try:
        with open(dest_path, "w") as handle:
            json.dump(oauth_data, handle)
    except Exception:
        return None
    return dest_path


def ensure_pydrive_creds_from_token(token_path, pydrive_creds_path):
    if not token_path or not os.path.exists(token_path):
        return None

    try:
        with open(token_path, "r") as handle:
            data = json.load(handle)
    except Exception:
        return None

    token = data.get("token")
    refresh_token = data.get("refresh_token")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    token_uri = data.get("token_uri")
    expiry = data.get("expiry")

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
        with open(pydrive_creds_path, "w") as handle:
            handle.write(creds.to_json())
        return pydrive_creds_path
    except Exception:
        return None


def get_google_token_data():
    """Helper to get google token from DB."""
    from backend.services.db import Database

    db = Database.get_db()
    user = db.users.find_one({"google_token": {"$exists": True, "$ne": None}})
    if user:
        token_data = user.get("google_token")
        token_path = os.path.join(
            os.getcwd(), "backend", "credentials", "token_db.json"
        )
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(token_data)
        return token_path
    return None


def _build_drive_loader(creds_path, token_path):
    if token_path and os.path.exists(token_path):
        try:
            GoogleDriveReader = get_google_drive_reader()
            ensure_pydrive_client_secrets(creds_path)
            pydrive_creds_path = os.path.join(
                os.getcwd(), "backend", "credentials", "pydrive_creds.txt"
            )
            ensure_pydrive_creds_from_token(token_path, pydrive_creds_path)
            loader_kwargs = {
                "token_path": token_path,
                "pydrive_creds_path": pydrive_creds_path,
            }
            if creds_path and os.path.exists(creds_path):
                loader_kwargs["credentials_path"] = creds_path
            loader = GoogleDriveReader(**loader_kwargs)
            return loader, "User OAuth (from DB)", None
        except Exception as e:
            return None, None, f"Failed to init User OAuth loader: {e}"

    if creds_path and os.path.exists(creds_path):
        try:
            GoogleDriveReader = get_google_drive_reader()
            loader = GoogleDriveReader(credentials_path=creds_path)
            return loader, "File-based Google credentials", None
        except Exception as e:
            return None, None, f"Failed to init credentials loader: {e}"

    return None, None, "No OAuth token or credentials file found."


def load_google_drive_documents():
    documents = []
    creds_path = resolve_credentials_path()
    token_path = get_google_token_data()

    if (token_path and os.path.exists(token_path)) or (
        creds_path and os.path.exists(creds_path)
    ):
        try:
            loader, auth_type, error = _build_drive_loader(creds_path, token_path)
            if not loader:
                if error:
                    print(error)
                return documents

            config = SystemConfig.get_config()
            folder_ids = [f["id"] for f in config.get("drive_folders", [])]

            for folder_id in folder_ids:
                if folder_id:
                    drive_docs = loader.load_data(folder_id=folder_id)
                    documents.extend(drive_docs)
                    print(
                        f"Loaded {len(drive_docs)} documents from Drive folder {folder_id}."
                    )

            if auth_type:
                print(f"Using {auth_type}.")
        except Exception as e:
            print(f"Failed to load from Drive: {e}")

    return documents


def get_drive_file_list():
    """
    Connects to Drive using current config and returns a list of filenames
    from the configured folders for verification.
    """
    creds_path = resolve_credentials_path()
    token_path = get_google_token_data()

    loader, auth_type, error = _build_drive_loader(creds_path, token_path)
    if not loader:
        return {"success": False, "message": error}

    config = SystemConfig.get_config()
    folder_ids = [f["id"] for f in config.get("drive_folders", []) if f.get("id")]

    if not folder_ids:
        return {
            "success": True,
            "files": [],
            "message": f"Connected via {auth_type}, but no folders configured.",
        }

    found_files = []
    try:
        for folder_id in folder_ids[:3]:
            docs = loader.load_data(folder_id=folder_id)
            count = len(docs)
            if count > 0:
                found_files.append(
                    f"Folder {folder_id}: Found {count} document chunks."
                )
            else:
                found_files.append(f"Folder {folder_id}: Empty or no access.")

        return {
            "success": True,
            "files": found_files,
            "message": f"Verified with {auth_type}",
        }

    except Exception as e:
        return {"success": False, "message": f"Error accessing Drive folders: {e}"}
