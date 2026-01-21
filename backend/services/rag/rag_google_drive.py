import json
import logging
import os
import time

from backend.models.user_config import UserConfig
from backend.utils.metadata import normalize_metadata

logger = logging.getLogger(__name__)


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
    candidates = [
        os.getenv("GOOGLE_OAUTH_CLIENT_PATH"),
        os.path.join(os.getcwd(), "backend", "credentials", "client_secrets.json"),
        os.path.join(os.getcwd(), "backend", "credentials", "credentials.json"),
        os.path.join(os.getcwd(), "client_secrets.json"),
    ]

    for path in candidates:
        if path and os.path.exists(path):
            return sanitize_oauth_credentials_file(path)
    return None


def get_google_drive_reader():
    try:
        import logging
        import tempfile
        from pathlib import Path
        from llama_index.core import SimpleDirectoryReader
        from llama_index.readers.google import (
            GoogleDriveReader as BaseGoogleDriveReader,
        )
        from backend.services.rag import ocr_readers
        from backend.services.rag.ocr_utils import get_ocr_config

        logger = logging.getLogger(__name__)

        class PatchedGoogleDriveReader(BaseGoogleDriveReader):
            def _download_with_retries(self, fileid, filepath, attempts=3):
                last_error = None
                for attempt in range(1, attempts + 1):
                    try:
                        return self._download_file(fileid, filepath)
                    except Exception as exc:
                        last_error = exc
                        logger.warning(
                            "Drive download failed (attempt %s/%s) for %s: %s",
                            attempt,
                            attempts,
                            fileid,
                            exc,
                        )
                        if attempt < attempts:
                            backoff = min(2**attempt, 8)
                            time.sleep(backoff)
                if last_error:
                    raise last_error
                return None

            def _load_data_fileids_meta(self, fileids_meta):
                if not fileids_meta:
                    return []
                try:
                    retry_attempts = int(
                        os.getenv("GOOGLE_DRIVE_DOWNLOAD_RETRIES", "3")
                    )
                    with tempfile.TemporaryDirectory() as temp_dir:

                        def get_metadata(filename):
                            return metadata[filename]

                        temp_dir = Path(temp_dir)
                        os.makedirs(temp_dir, exist_ok=True)
                        metadata = {}
                        ocr_documents = []
                        standard_files = []
                        ocr_config = get_ocr_config()

                        for fileid_meta in fileids_meta:
                            filename = fileid_meta[2]
                            if not filename:
                                continue
                            safe_filename = os.path.basename(filename).strip()
                            if not safe_filename:
                                continue
                            altsep = os.path.altsep
                            if os.path.sep in safe_filename or (
                                altsep and altsep in safe_filename
                            ):
                                safe_filename = safe_filename.replace(os.path.sep, "_")
                                if altsep:
                                    safe_filename = safe_filename.replace(altsep, "_")
                            filepath = os.path.join(temp_dir, safe_filename)
                            os.makedirs(os.path.dirname(filepath), exist_ok=True)
                            fileid = fileid_meta[0]
                            final_filepath = self._download_with_retries(
                                fileid, filepath, attempts=retry_attempts
                            )
                            if not final_filepath:
                                continue

                            file_metadata = normalize_metadata(
                                {
                                    "file_id": fileid_meta[0],
                                    "author": fileid_meta[1],
                                    "file_name": fileid_meta[2],
                                    "mime_type": fileid_meta[3],
                                    "created_at": fileid_meta[4],
                                    "modified_at": fileid_meta[5],
                                }
                            )
                            metadata[final_filepath] = file_metadata

                            mime_type = file_metadata.get("mime type")
                            if ocr_readers.is_pdf_mime_type(
                                mime_type
                            ) or ocr_readers.is_image_mime_type(mime_type):
                                ocr_docs = ocr_readers.load_documents_for_file(
                                    final_filepath, file_metadata, config=ocr_config
                                )
                                if ocr_docs:
                                    ocr_documents.extend(ocr_docs)
                                elif ocr_readers.is_pdf_mime_type(mime_type):
                                    standard_files.append(final_filepath)
                            else:
                                standard_files.append(final_filepath)

                        documents = []
                        if standard_files:
                            loader = SimpleDirectoryReader(
                                input_files=standard_files, file_metadata=get_metadata
                            )
                            documents = loader.load_data()
                            for doc in documents:
                                file_id = doc.metadata.get(
                                    "file_id"
                                ) or doc.metadata.get("file id")
                                if file_id:
                                    doc.id_ = file_id

                        documents = ocr_documents + documents

                    return documents
                except Exception as e:
                    logger.error("Patched loader error: %s", e)
                    return []

        return PatchedGoogleDriveReader
    except Exception as exc:
        raise RuntimeError("Google Drive reader is unavailable.") from exc


def ensure_pydrive_client_secrets(creds_path):
    """Ensure a valid client_secrets.json exists in CWD for PyDrive."""
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


def get_google_token_data(user_id, token_json=None):
    """Helper to get google token from Firestore, refresh it if needed, and write it to disk."""
    token_data = token_json
    if not token_data and user_id:
        token_data = UserConfig.get_google_token(user_id)
    if not token_data:
        return None

    # Refresh token if needed
    from backend.services.google_oauth import refresh_google_credentials

    creds, refreshed = refresh_google_credentials(token_data)

    if creds:
        token_str = creds.to_json()
        if refreshed and user_id:
            UserConfig.set_google_token(user_id, token_str)
        final_token_data = token_str
    else:
        # Fallback to original if refresh fails, though it likely won't work
        final_token_data = (
            json.dumps(token_data) if isinstance(token_data, dict) else token_data
        )

    token_path = os.path.join(
        os.getcwd(), "backend", "credentials", f"token_{user_id}.json"
    )
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as handle:
        handle.write(final_token_data)
    return token_path


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
            return loader, "User OAuth", None
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


def load_google_drive_documents_by_file_ids(user_id, file_ids, token_json=None):
    """
    Load documents from Google Drive by specific file IDs.
    This is used with the drive.file scope where users select individual files.

    Args:
        user_id: The user's ID
        file_ids: List of Google Drive file IDs to load
        token_json: Optional token JSON string

    Returns:
        List of loaded documents
    """
    documents = []
    if not file_ids:
        return documents

    creds_path = resolve_credentials_path()
    token_path = get_google_token_data(user_id, token_json=token_json)

    if (token_path and os.path.exists(token_path)) or (
        creds_path and os.path.exists(creds_path)
    ):
        try:
            loader, auth_type, error = _build_drive_loader(creds_path, token_path)
            if not loader:
                if error:
                    print(error)
                return documents

            # Load documents by file IDs
            drive_docs = loader.load_data(file_ids=file_ids)
            documents.extend(drive_docs)
            logger.info(
                f"Loaded {len(drive_docs)} documents from {len(file_ids)} Drive files."
            )

            if auth_type:
                logger.info(f"Using {auth_type}.")
        except Exception as e:
            logger.error(f"Failed to load from Drive by file IDs: {e}")

    return documents


def get_selected_files_info(user_id, file_ids, token_json=None):
    """
    Get file metadata for selected file IDs.
    Returns a list of file info dicts with id, name, mimeType.
    """
    if not file_ids:
        return []

    token_path = get_google_token_data(user_id, token_json=token_json)
    if not token_path or not os.path.exists(token_path):
        return []

    try:
        with open(token_path, "r") as handle:
            token_data = json.load(handle)
    except Exception:
        return []

    scopes = token_data.get("scopes") or [
        "https://www.googleapis.com/auth/drive.file",
    ]

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception:
        return []

    try:
        creds = Credentials.from_authorized_user_info(token_data, scopes=scopes)
        service = build(
            "drive",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )

        files_info = []
        for file_id in file_ids:
            try:
                file_meta = (
                    service.files()
                    .get(fileId=file_id, fields="id,name,mimeType,modifiedTime")
                    .execute()
                )
                files_info.append(file_meta)
            except Exception as e:
                logger.warning(f"Could not get metadata for file {file_id}: {e}")

        return files_info
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        return []


def get_files_checksum(user_id, file_ids, token_json=None):
    """
    Generate a checksum based on file IDs and modified times.
    This is used to detect changes without downloading files.

    Returns:
        str: A hash string representing the current state of the files.
             Returns None if files cannot be accessed.
    """
    import hashlib

    if not file_ids:
        return None

    files_info = get_selected_files_info(user_id, file_ids, token_json=token_json)
    if not files_info:
        return None

    # Sort for consistent ordering
    files_info.sort(key=lambda f: f.get("id", ""))

    # Build a string of id:modifiedTime pairs
    checksum_data = "|".join(
        f"{f.get('id')}:{f.get('modifiedTime', '')}" for f in files_info
    )

    # Return MD5 hash
    return hashlib.md5(checksum_data.encode()).hexdigest()
