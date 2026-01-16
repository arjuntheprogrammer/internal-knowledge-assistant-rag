# Local Setup & Development

This guide will help you set up the **Internal Knowledge Assistant** for local development.

## Prerequisites

- **Python 3.9+**
- **A Zilliz Cloud account** (for Vector Storage)
- **A Firebase project** (for Auth & Database)
- **An OpenAI API key**

## 1. Configuration

Create a `.env` file in the root directory by copying the `.env.template` file and filling in the required values:

```bash
cp .env.template .env
```

### Note: Firebase Admin vs Client Config
- **Firebase Admin Credentials** (`FIREBASE_ADMIN_CREDENTIALS_PATH`): A service account private key used by the Python backend for token verification and Firestore access. This is a secret and must never be exposed.
- **Firebase Client Config** (`FIREBASE_API_KEY`, etc.): Public identifiers used by the JavaScript frontend to initialize Firebase Auth for Google Sign-In. These are designed to be public and are safe to include in client-side code.

## 2. Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

The app will be available at `http://localhost:5001`.

---

## Troubleshooting

- **OCR Dependencies**: If you are testing OCR features locally, ensure you have `Tesseract` installed on your machine (`brew install tesseract` on macOS).
- **Zilliz Connection**: Ensure your `MILVUS_URI` and `MILVUS_TOKEN` are correct in your `.env` file.
- **Firebase Auth**: If Google Sign-In fails, check if `localhost:5001` is added to the "Authorized Domains" in your Firebase Console.
