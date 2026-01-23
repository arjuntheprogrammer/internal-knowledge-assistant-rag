# ✅ Task: Split Prompts into Separate Files + JSON Structured Output + Opik Prompt Library Storage (CasualQueryEngine + LazyRAGQueryEngine)

## Repository
- Repo: `arjuntheprogrammer/internal-knowledge-assistant-rag`
- Branch: `dev`
- Goal: Move all LLM prompts into **separate prompt files**, enforce **structured JSON outputs** for RAG answers, add **structured outputs for casual chat**, and ensure **all prompts are stored/tracked in Opik** (Prompt Library + per-run attribution).

---

## Summary of Required Changes

### A) Prompts as separate files
Create a `prompts/` directory at repo root with one prompt per file, for:
- **CasualQueryEngine** (casual chat)
- **LazyRAGQueryEngine / RAG query engine** (default, list, refine)

### B) JSON structured output from the LLM
- **RAG engine** must return strict JSON following a schema for deterministic eval checks.
- **Casual engine** should also return structured JSON (simpler schema), so routing output is consistently machine-checkable.

### C) Opik prompt storage/tracking
- Every prompt file must be:
  1) Loaded at runtime via a PromptLoader
  2) Hashed (sha256)
  3) Tagged with a prompt name + version
  4) **Registered/stored in Opik Prompt Library** on startup (or first use)
  5) Attached to traces/spans so runs can be compared by prompt version/hash

---

## Directory Layout (must implement)

Create:

```

prompts/
README.md
versions.json
rag_default_json.md
rag_list_json.md
rag_refine_json.md
casual_json.md
shared_json_schema.md

````

Notes:
- Prompts must be plain text files in `.md`.
- `shared_json_schema.md` contains schema + allowed enums used by both engines.
- `versions.json` defines version strings per prompt file (human-controlled).
  - Example:
    ```json
    {
      "rag_default_json": "v1",
      "rag_list_json": "v1",
      "rag_refine_json": "v1",
      "casual_json": "v1",
      "shared_json_schema": "v1"
    }
    ```

---

## 1) JSON Schemas (must follow exactly)

### 1.1 RAG JSON Schema (for knowledge_base_retrieval)

LLM must output **valid JSON only** (no markdown, no backticks, no extra text):

```json
{
  "answer": "string",
  "refused": false,
  "refusal_reason": "not_in_docs | out_of_scope | unsafe | unknown",
  "answer_style": "bullets | sections | paragraph",
  "entities": ["string"],
  "citations": [
    {
      "file_id": "string",
      "file_name": "string",
      "snippets": ["string"]
    }
  ]
}
````

Rules:

* Always include all keys.
* If `refused=false`, must include at least 1 citation unless the system chooses to fallback to catalog (system-level override).
* `citations[*].file_id` should match `source_nodes[*].metadata.file_id` values (do not invent sources).
* `snippets` should be short excerpts drawn from context (optional but recommended).

### 1.2 Casual JSON Schema (for casual_chat)

Casual engine must also output JSON-only:

```json
{
  "answer": "string",
  "refused": false,
  "refusal_reason": "unknown",
  "answer_style": "paragraph",
  "entities": [],
  "citations": []
}
```

Rules:

* Casual answers must not hallucinate “sources”.
* Always return citations empty.

---

## 2) Prompt Content Requirements (Domain-Agnostic)

### 2.1 `prompts/shared_json_schema.md`

Contains:

* The full schema text for both RAG and Casual
* Allowed enum values
* “JSON only” rule
* Grounding principles:

  * Use only provided context for RAG
  * Don’t invent sources
  * If not in context, refuse

### 2.2 `prompts/rag_default_json.md`

Must instruct:

* Use ONLY `{context_str}` to answer `{query_str}`
* Output valid JSON per shared schema
* If answer not found in context, set `refused=true` and appropriate `refusal_reason`
* For multi-entity questions:

  * separate facts per entity (avoid mixing)
  * set `answer_style="sections"`
  * fill `entities` list
* Numeric exactness:

  * copy numbers/dates/requirements exactly from context
* Citations rules:

  * citations must reference file_id + file_name
  * include snippet(s) from context

### 2.3 `prompts/rag_list_json.md`

Must instruct:

* User asked for a list; enumerate ALL unique items from context (don’t stop early)
* Output JSON only
* `answer_style="bullets"`
* If context incomplete, include phrase “(List may be incomplete)” inside `answer`

### 2.4 `prompts/rag_refine_json.md` (only if refine used)

Must instruct:

* Given `{existing_answer}` and `{context_str}`, refine answer
* Keep JSON schema valid
* Only add info supported by new context
* Maintain citations consistency

### 2.5 `prompts/casual_json.md`

Must instruct:

* Handle greetings/small talk briefly
* Output JSON only using casual schema
* No citations

---

## 3) Prompt Loading & Versioning

### 3.1 Create a PromptLoader utility

Add a module, e.g.:

* `backend/utils/prompt_loader.py`

Responsibilities:

1. Load prompt files from `prompts/`
2. Load `versions.json`
3. Provide API:

```python
PromptLoader.get(prompt_key: str) -> PromptSpec
```

Where `PromptSpec` includes:

* `name` (prompt_key)
* `version` (from versions.json)
* `text` (loaded content)
* `hash` (sha256 of text)
* `path` (file path)

Cache loaded content in memory.

### 3.2 Prompt keys

Use these exact keys:

* `shared_json_schema`
* `rag_default_json`
* `rag_list_json`
* `rag_refine_json`
* `casual_json`

---

## 4) Opik Prompt Library Integration (must implement)

### Goal

Every prompt file is stored in Opik Prompt Library and referenced in traces.

### Requirements

1. On first use of a prompt (or app startup), register it in Opik:

   * name: `prompt_key`
   * version: from `versions.json`
   * content: prompt text
   * metadata: prompt hash + repo + commit sha (if available)

2. Every query execution (casual or rag) must attach:

   * prompt_key
   * prompt_version
   * prompt_hash
     to Opik trace/span metadata.

### Implementation

Create `backend/utils/opik_prompts.py`:

* `ensure_prompt_in_opik(prompt_spec: PromptSpec) -> None`
* `attach_prompt_meta(span_or_trace, prompt_spec) -> None`

If Opik SDK supports explicit Prompt Library APIs, use them.
If not, store as standard metadata with a stable naming convention:

* `prompt.name`
* `prompt.version`
* `prompt.hash`


---

## 5) Update Engines to Use External Prompts

### 5.1 Update `backend/services/rag/engines.py`

Replace hardcoded PromptTemplate strings with text from PromptLoader.

* For default RAG: load `rag_default_json` + `shared_json_schema`
* For list RAG: load `rag_list_json` + `shared_json_schema`
* For refine: load `rag_refine_json` + `shared_json_schema` if used

Construct `PromptTemplate` by concatenating:

`shared_json_schema.text + "\n\n" + rag_default_json.text`

Same for list/refine.

Also implement:

* `prompt_hash` and `prompt_version` extraction
* pass these into metadata if LlamaIndex supports (or attach to callback_manager events)
* at minimum, log them

### 5.2 Update `backend/services/rag/engines.py` (CasualQueryEngine)

Ensure CasualQueryEngine uses:

* `casual_json` + (optionally) `shared_json_schema` subset for casual format
  Return JSON only.

---

## 6) Parsing & Validation of JSON Outputs

Create `backend/services/rag/structured_output.py`:

* `parse_rag_json(text: str) -> dict`
* `parse_casual_json(text: str) -> dict`

Validation rules:

* Must parse with strict `json.loads`
* Must contain required keys
* Must validate enums
* Must ensure `citations` is list of objects with required keys (for RAG)
* If parse fails:

  * Optionally do a single “repair JSON” call
  * Otherwise return a safe refused JSON object:

    * refused=true
    * refusal_reason="unknown"
    * citations=[]

---

## 7) Improve RAGService Outputs (structured + sources)

### 7.1 Add `RAGService.query_structured(...)`

Implement a new method:

```python
RAGService.query_structured(question, user_context) -> dict
```

Return:

```json
{
  "selected_tool": "casual_chat | knowledge_base_retrieval | unknown",
  "selected_reason": "string|null",
  "llm_json": { ... },
  "retrieval": {
    "retrieved_file_ids": ["..."],
    "retrieved_node_ids": ["..."]
  },
  "catalog_fallback_used": true|false,
  "catalog_answer": "string|null",
  "debug": {
    "prompt_name": "string",
    "prompt_version": "string",
    "prompt_hash": "string"
  }
}
```

### 7.2 How to implement inside `query_structured`

1. Run router query exactly as today.
2. Identify selected tool & reason.
3. If selected tool is RAG:

   * keep the original LlamaIndex Response object
   * extract source_nodes (if present)
   * derive:

     * retrieved_node_ids
     * retrieved_file_ids by reading node.metadata["file_id"]
   * parse the LLM output text as RAG JSON
   * apply catalog fallback logic if your existing code triggers it:

     * if fallback is used, set `catalog_fallback_used=true` and `catalog_answer`
4. If selected tool is casual:

   * parse casual JSON output
   * no retrieval ids
5. Attach prompt metadata (name/version/hash) chosen for this query (default vs list, casual).

### 7.3 Keep `RAGService.query()` backward compatible

* `query()` can keep returning markdown/string for UI.
* Modify `query()` to call `query_structured()` and then:

  * If `catalog_fallback_used`, return catalog_answer
  * Else return a markdown-rendered version of `llm_json`:

    * `answer` as-is
    * render citations to a `**Sources:**` section using file_name

---

## 8) Update Evals to Use Structured Outputs

In `evals/runner/adapters.py`:

* Replace calls to `RAGService.query()` with `RAGService.query_structured()`
* Use:

  * `llm_json.refused` for must_refuse checks
  * `len(llm_json.citations)` for citation checks
  * `retrieval.retrieved_file_ids` for Recall@k
  * `catalog_fallback_used` to interpret list-query behavior

Ensure deterministic scoring.

---

## 9) Opik Trace/Span Attachment (prompts + outputs)

Wherever you instrument Opik (eval runner and/or backend):

* Attach prompt metadata:

  * `prompt_name`, `prompt_version`, `prompt_hash`
* Attach structured result:

  * `llm_json`
  * `retrieved_file_ids`
  * `selected_tool`
* For eval runs, attach per-sample metrics as well.

Additionally:

* Ensure prompt registration function is called before logging (Prompt Library).

---

## 10) Acceptance Criteria

1. Prompts are in **separate files** under `prompts/`.
2. CasualQueryEngine outputs valid JSON matching casual schema.
3. RAG engine outputs valid JSON matching rag schema.
4. `RAGService.query_structured()` returns `llm_json` + retrieval info.
5. `RAGService.query()` still works for UI (returns readable response).
6. Prompt loader uses versions.json + sha256 hashes.
7. Prompts are registered/stored in Opik Prompt Library (or equivalent) and prompt metadata is attached to traces.
8. Eval runner can compute metrics deterministically using structured outputs.

---

## Implementation Notes / Guidance

* Keep changes incremental and reversible;
* Prefer robust JSON parsing and safe fallback on errors.
* Make prompt registration in Opik best-effort; no hard failure when Opik is missing.
* Ensure `file_id` is present in node.metadata for citations; if missing, fallback to file_name only but keep deterministic behavior where possible.

---

## Deliverable

Implement all changes in the repo with clean commits and include the new prompt files. No additional documentation is required beyond `prompts/README.md` (optional) to explain how to edit/version prompts.

Proceed to implement now.
Don't commit or push
Use conda env internal-knowledge-assistant