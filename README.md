# Internal Knowledge Assistant

## About

This is a simple AI-powered internal knowledge assistant with ACL that can be used to answer questions about internal knowledge using Retrieval Augmented Generation (RAG).

## Architecture Components

1. UI: Chat interface
2. Backend: Flask
3. Frontend: HTML, CSS, JS
4. RAG: LlamaIndex
5. Database: MongoDB
6. Vector Store: Chroma
7. Chat Model: OpenAI/Ollama
8. Knowledge Base: Google Drive folder
9. Google Drive Connector: Google Drive API
10. Analytics and Monitoring: LangSmith

## Workflow

1. User authentication and authorization: user signup (full name, email, password) and login (email, password).
2. Frontend chat interface: user enters a question.
3. Backend API gateway and rate limiting: the question is sent to the backend.
4. Retrieval layer (vector DB + metadata/ACL filters): the backend fetches relevant documents based on ACL. If the querying user is not authorized to access a document, it is not included in the vector store.
5. Prompt builder (templates + guardrails + context packing): the documents are sent to the chat model after building the prompt and context.
6. Chat model (OpenAI LLM API): the chat model generates a response.
7. Post-processing and output validation: citations, policy checks, redaction, response formatting (Markdown, rich cards, links).
8. Backend: the response is sent to the frontend.
9. Frontend: the response is displayed to the user.
10. Feedback and rating capture (thumbs up/down).
11. Background: the vector store polls Google Drive for new documents and updates every 10 seconds.
12. Analytics and monitoring (LangSmith): includes usage, latency, token usage, accuracy, hallucinations, drift.

## Knowledge Base Connector

> Note: Admin only (username: admin@gmail.com, password: admin@gmail.com).

### Configure Google Drive Connector (UI)

1. Add a new Google Drive folder.
2. Provide access to the Google Drive folder.
3. Automatic: poll the Google Drive folder for new documents and update the vector store.
4. Display all the documents in the UI with ACL.

### Configure LLM (OpenAI/Ollama) in UI

1. Select LLM.
2. For OpenAI: provide OpenAI API key and model name.
3. For Ollama: provide Ollama API URL and model name.

## LLM Optimization

1. Prompt engineering
2. Context window management
3. Context history compression
4. Caching
5. Guardrails
6. Usage dashboard and alerting

## Safety

1. Policy checks
2. Redaction
3. Hallucination detection
4. Drift detection
5. PII detection
6. Content moderation
7. Block prompt injections
8. Block harmful content

## Notes

- User authentication: JWT token.
- User document access: retrieval from Google Drive. ACL is checked in the retrieval process. If the user is not authorized to access the document, it is not included in the vector store.
- Feedback and rating capture: the feedback and rating are sent to the backend.
- Analytics and monitoring: the analytics and monitoring are sent to LangSmith.
- Rate limiting: the rate limiting is done at the API gateway level.
- Background: the background process updates the vector store every 10 seconds.

## Installation and Usage

### Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)
- MongoDB (if running locally without Docker)

### 1. Clone the repository


```bash
git clone <repository_url>
cd internal-knowledge-assistant
```

### 2. Configuration

Create a `.env` file in the root directory and add the following variables:


```bash
SECRET_KEY=your_secret_key
PORT=5001
FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=1
MONGO_URI=mongodb://mongo:27017/internal_knowledge_db # use localhost when running without Docker
OPENAI_API_KEY=your_openai_api_key
CHROMA_HOST=chroma # use localhost when running without Docker
CHROMA_PORT=8000
CHROMA_COLLECTION=internal-knowledge-assistant
```

### 3. Run with Docker (Recommended)

```bash
docker compose up --build
```

The backend API will be available at `http://localhost:${PORT}`.

### 4. Run Locally (with Conda) - Recommended for Local Dev

1. Create and activate the Conda environment:

   ```bash
   conda env create -f environment.yml
   conda activate internal-knowledge-assistant
   ```

2. Start MongoDB (ensure it's running on port 27017).
3. Run the application:

   ```bash
   python app.py
   ```

### 5. Run Locally (with pip)

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Start MongoDB (ensure it's running on port 27017).
3. Run the application:

   ```bash
   PORT=5001 python app.py
   ```

### 6. LLM Configuration (Ollama)

To use a local LLM with Ollama:

1. **Install Ollama**: download from [ollama.ai](https://ollama.ai).
2. **Pull a model**: run `ollama pull llama2` (or your preferred model).
3. **Configure `.env`**:
   update your `.env` file to point to your local Ollama instance:

   ```bash
   OLLAMA_BASE_URL=http://localhost:11434
   ```

   Note: if running with Docker, you may need to use `http://host.docker.internal:11434` to access Ollama from within the container.

### 7. Chroma Vector Store (Docker)

Chroma runs as a local service. The `docker-compose.yml` includes a `chroma` container that the backend connects to.

To use Chroma with Docker:

1. Ensure the `chroma` service is running via `docker compose up --build`.
2. Set the following in your `.env` file:

   ```bash
   CHROMA_HOST=chroma
   CHROMA_PORT=8000
   CHROMA_COLLECTION=internal-knowledge-assistant
   ```

To use Chroma locally (outside Docker), run a server and point the backend at it:

```bash
docker run -p 8000:8000 chromadb/chroma:latest
```

```bash
CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION=internal-knowledge-assistant
```

### 8. Google Drive Configuration

To enable the Google Drive connector:

1. Enable the Google Drive API in your Google Cloud Console.
2. Create a Service Account or OAuth credentials.
3. Download the JSON key file.
4. Rename `backend/credentials/credentials.template.json` to `backend/credentials/credentials.json` and paste your content there (or just save your downloaded file as `credentials.json` in that folder).
   Note: `credentials.json` is gitignored to secure your secrets.
5. Run the application; it will automatically detect the credentials and attempt to load documents from folders configured in the Admin Dashboard.

### 9. Analytics and Monitoring (LangSmith)

To enable tracing with LangSmith:

1. Sign up at [smith.langchain.com](https://smith.langchain.com).
2. Get your API key.
3. Add the following to your `.env` file:

   ```bash
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LANGCHAIN_API_KEY=your_langchain_api_key
   LANGCHAIN_PROJECT=internal-knowledge-assistant
   ```

   The application will automatically log traces to your project.
