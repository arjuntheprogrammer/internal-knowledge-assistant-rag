# Local Setup & Development

This guide will help you set up the **Internal Knowledge Assistant** for local development.

## Prerequisites

- **Python 3.9+**
- **A Zilliz Cloud account** (Managed Milvus for Vector Storage)
- **A Firebase project** (for Authentication & Firestore Database)
- **An OpenAI API key**
- **Tesseract OCR** (Optional, for scanning images/scanned PDFs)

## 1. Environment Setup

It is highly recommended to use a virtual environment:

```bash
# Using venv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# OR using Conda
conda create -n knowledge-assistant python=3.10
conda activate knowledge-assistant
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## 2. Configuration

Create a `.env` file in the root directory by copying the `.env.template` file:

```bash
cp .env.template .env
```

Fill in the required values in your `.env`. Here are some key parts:

### Google Drive Integration
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API** and **Google Picker API**.
3. Create **OAuth 2.0 Client IDs** (Web application).
4. Add `http://localhost:5001` to **Authorized JavaScript origins**.
5. Add `http://localhost:5001/api/config/drive-oauth-callback` to **Authorized redirect URIs**.
6. Download the JSON and save it to `backend/credentials/google-credentials.json`.
7. Create an **API Key** for the Google Picker and add it as `GOOGLE_PICKER_API_KEY`.

### Firebase Setup
1. Create a project in the [Firebase Console](https://console.firebase.google.com/).
2. Enable **Google Sign-In** in the Authentication section.
3. Enable **Cloud Firestore** in the Build section.
4. Go to Project Settings > Service Accounts and download a new private key. Save it as `backend/credentials/firebase-admin.json`.
5. In Project Settings > General, find your Web App configuration and fill in the `FIREBASE_*` variables in `.env`.

### Firebase Admin vs Client Config
- **Firebase Admin Credentials** (`FIREBASE_ADMIN_CREDENTIALS_PATH`): Used by the Python backend for token verification and Firestore access. **Keep this secret.**
- **Firebase Client Config** (`FIREBASE_API_KEY`, etc.): Used by the JavaScript frontend to initialize Firebase Auth. These are safe to be public.

## 3. Run Locally

```bash
python app.py
```

The app will be available at `http://localhost:5001`.

---

## Troubleshooting

- **OCR Dependencies**: If testing OCR, install Tesseract:
  - macOS: `brew install tesseract`
  - Linux: `sudo apt-get install tesseract-ocr`
- **Port Conflict**: If 5001 is in use, change the `PORT` in your `.env`.
- **Firebase Auth**: If Google Sign-In fails, double-check that `localhost:5001` is in your Firebase Console's "Authorized Domains".
