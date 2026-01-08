# Internal Knowledge Assistant

## ABOUT

This is a simple AI-powered internal knowledge assistant with ACL that can be used to answer questions about internal knowledge using Retrieval Augmented Generation (RAG).

## ARCHITECTURE COMPONENTS

1. UI: Chat Interface
2. Backend: Flask
3. Frontend: HTML, CSS, JS
4. RAG: LlamaIndex
5. Database: MongoDB
6. Vector Store: Pinecone
7. Chat Model: OpenAI/Ollama
8. Knowledge Base: Google Drive Folder
9. Google Drive Connector: Google Drive API
10. Analytics & Monitoring: LangSmith

## WORKFLOW

1. User Authentication & Authorization: User Signup (full name, email and password) and Login (email and password)
2. Frontend Chat Interface: User enters a question
3. Backend API Gateway & Rate Limiting: The question is sent to the backend.
4. Retrieval Layer (Vector DB + Metadata / ACL Filters): The backend fetches the knowledge base vector store with relavent documents based on ACL. If the quering user is not authorized to access the document, it is not included in the vector store.
5. Prompt Builder (Templates + Guardrails + Context Packing): The documents are sent to the chat model after building the prompt and context.
6. Chat Model (Open AI LLM API): The chat model generates a response.
7. Post Processing and Output Validator: Citations, Policy Checks, Redaction
    - Response Formatter (Markdown / Rich Cards / Links)
8. Backend: The response is sent to the frontend.
9. The frontend displays the response to the user.
10. Feedback & Rating Capture (Thumbs up/down).
11. Background: Vector store is polling Google Drive for new documents, ACL and updating the vector store every 10 seconds to make sure the vector store is always up to date.
12. Analytics & Monitoring: The analytics and monitoring are sent to LangSmith.
    - Includes: Usage, Latency, Token Usage, Accuracy, Hallucinations, Drift

## KNOWLEDGE BASE CONNECTOR

Note: For Admin only (username: admin@gmail.com, password: admin@gmail.com)

Config Google Drive Connector with UI:
1. UI: Add new google drive folder
2. UI: Provide access to google drive folder
3. Automatic: Poll google drive folder for new documents and Update vector store
4. UI: Display all the documents in the UI with ACL


Config LLM - OpenAI/Ollama with UI:
1. UI: Select LLM
2. UI: For Open AI: Provide OpenAI API Key and Model Name
3. UI: For Ollama: Provide Ollama API URL and Model Name


## LLM OPTIMISATION
1. Prompt Engineering
2. Context Window Management
3. Context History Compression
4. Caching
5. Guardrails
6. Usage Dashboard and Alerting

## SAFETY
1. Policy Checks
2. Redaction
3. Hallucination Detection
4. Drift Detection
5. PII Detection
6. Content Moderation
7. Block Prompt Injections
8. Block Harmful Content

## Notes
- User Authentication: JWT Token
- User Document Access: Retrieval from google drive. ACL is checked in the retrieval process. If the user is not authorized to access the document, it is not included in the vector store.
- Feedback & Rating Capture: The feedback and rating are sent to the backend.
- Analytics & Monitoring: The analytics and monitoring are sent to LangSmith.
- Rate Limiting: The rate limiting is done at the API Gateway level.
- Background: The background process is running in the background to update the vector store every 10 seconds.


## INSTALLATION & USAGE

### Prerequisites
- Docker & Docker Compose
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
MONGO_URI=mongodb://mongo:27017/internal_knowledge_db # or localhost if running locally
OPENAI_API_KEY=your_openai_api_key
```

### 3. Run with Docker (Recommended)
```bash
docker-compose up --build
```
The backend API will be available at `http://localhost:5000`.

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
   # Default runs on port 5000. Use PORT env var to change.
   PORT=5001 python app.py
   ```


### 6. LLM Configuration (Ollama)
To use a local LLM with Ollama:
1. **Install Ollama**: Download from [ollama.ai](https://ollama.ai).
2. **Pull a Model**: Run `ollama pull llama2` (or your preferred model).
3. **Configure .env**:
   Update your `.env` file to point to your local Ollama instance:
   ```bash
   OLLAMA_BASE_URL=http://localhost:11434
   ```
   *Note: If running with Docker, you may need to use `http://host.docker.internal:11434` to access Ollama from within the container.*

### 7. Google Drive Configuration
To enable the Google Drive connector:
1. Enable the Google Drive API in your Google Cloud Console.
2. Create a Service Account or OAuth credentials.
3. Download the JSON key file.
4. Rename `backend/credentials/credentials.template.json` to `backend/credentials/credentials.json` and paste your content there (or just save your downloaded file as `credentials.json` in that folder).
   *Note: `credentials.json` is gitignored to secure your secrets.*
5. Run the application; it will automatically detect the credentials and attempt to load documents from folders configured in the Admin Dashboard.


### 8. Analytics & Monitoring (LangSmith)
To enable tracing with LangSmith:

1. Sign up at [smith.langchain.com](https://smith.langchain.com).
2. Get your API Key.
3. Add the following to your `.env` file:
   ```bash
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LANGCHAIN_API_KEY=your_langchain_api_key
   LANGCHAIN_PROJECT=internal-knowledge-assistant
   ```
   The application will automatically logging traces to your project.

