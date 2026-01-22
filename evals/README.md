# RAG Evaluation Framework

This folder contains the evaluation framework for the Internal Knowledge Assistant RAG system.

## Overview

The evaluation framework runs a dataset of queries against the RAG system and computes deterministic metrics for:
- **Retrieval quality** (Recall@k)
- **Citation compliance**
- **Refusal correctness** (for out-of-scope queries)

Results are logged to **Opik** for tracking and visualization.

## Directory Structure

```
evals/
├── README.md              # This file
├── datasets/
│   ├── stock_eval_v1.jsonl    # Evaluation dataset
│   └── file_id_mapping.json   # File ID to filename mapping
├── runner/
│   ├── __init__.py
│   ├── run_eval.py        # Main CLI runner
│   ├── metrics.py         # Metric computation
│   ├── adapters.py        # RAG and Opik adapters
│   └── schema.py          # Data schemas
└── runs/                  # Output directory for results
    └── <timestamp>_results.jsonl
    └── <timestamp>_summary.json
```

## Setup

### Prerequisites

1. Ensure you have the conda environment activated:
   ```bash
   conda activate internal-knowledge-assistant
   ```

2. Required environment variables in `.env`:
   ```bash
   # OpenAI API key for LLM and embeddings
   OPENAI_API_KEY=sk-...

   # Milvus/Zilliz configuration
   MILVUS_URI=https://...
   MILVUS_TOKEN=...
   MILVUS_COLLECTION=internal_knowledge_assistant

   # Opik configuration
   OPIK_API_KEY=...
   OPIK_EVAL_PROJECT_NAME=internal-knowledge-assistant-eval  # Default for evaluations
   OPIK_ENABLED=true

   # Optional: Default User for evals
   EVAL_USER_ID=NUsot0aGhVMGEEnu9RujAPSRXtv2
   ```

3. The user must have indexed documents. Use the default `EVAL_USER_ID` or provide your own.

## Running Evaluation

### Basic Usage

Running with default user and dataset:
```bash
python -m evals.runner.run_eval
```

Running a specific dataset for a specific user:
```bash
python -m evals.runner.run_eval \
  --dataset evals/datasets/stock_eval_v1.jsonl \
  --user-id <firebase_user_id>
```

### Full Options

```bash
python -m evals.runner.run_eval \
  --dataset evals/datasets/stock_eval_v1.jsonl \
  --user-id <firebase_user_id> \
  --k 10 \
  --opik-project internal-knowledge-assistant-eval \
  --opik-dataset stock_eval_v1 \
  --limit 5  # For testing
```

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--dataset` | No | `evals/datasets/stock_eval_v1.jsonl` | Path to JSONL dataset file |
| `--user-id` | No | `EVAL_USER_ID` or `NUsot...` | Firebase user ID for retrieval context |
| `--k` | No | 10 | Top-k for retrieval metrics |
| `--opik-project` | No | `OPIK_EVAL_PROJECT_NAME` | Opik project name |
| `--opik-dataset` | No | `stock_eval_v1` | Opik dataset name |
| `--use-opik-experiment` | No | `True` | Use `opik.evaluate()` for proper Experiments |
| `--no-opik` | No | `False` | Disable Opik logging |
| `--openai-key` | No | From env | OpenAI API key |
| `--limit` | No | None | Limit samples (for testing) |

## Dataset Format

The dataset is JSONL format with one query per line:

```json
{
  "id": "q_001",
  "query": "Summarize HCL Technologies Limited in 3 bullet points.",
  "intent": "summary",
  "expected_file_ids": ["15vxlJ7LtoIzNcoLs5WzZgFN3vro4B-XI"],
  "must_cite": true,
  "required_citations_count": 1,
  "answer_style": "bullets",
  "max_entities": 1,
  "is_out_of_scope": false,
  "must_refuse": false,
  "no_external_knowledge": true,
  "allowed_uncertainty": false
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique query identifier |
| `query` | string | The query text |
| `intent` | string | Query type: list, qa, summary, pros_cons, compare, aggregate, advice |
| `expected_file_ids` | list[str] | Google Drive file IDs that should be retrieved |
| `must_cite` | bool | Whether the answer must include sources |
| `required_citations_count` | int | Minimum number of citations required |
| `answer_style` | string | Expected format: bullets, sections, paragraph |
| `max_entities` | int | Maximum entities to mention (0 = no limit) |
| `is_out_of_scope` | bool | Query is outside the knowledge base |
| `must_refuse` | bool | System should refuse to answer |
| `no_external_knowledge` | bool | Answer must be grounded in documents only |
| `allowed_uncertainty` | bool | Answer may express uncertainty |

## Metrics

The framework uses a hybrid approach: local deterministic metrics for speed and **Opik Custom Metrics** for dashboard visualization.

### Retrieval Metrics

- **Recall@5**: 1 if any expected file ID in top-5 retrieved.
- **Recall@10**: 1 if any expected file ID in top-10 retrieved.
- **Recall-All@5**: Fraction of expected file IDs in top-5 retrieved.
- **Recall-All@10**: Fraction of expected file IDs in top-10 retrieved.

### Citation & Generation Metrics

- **Has Sources Section**: Whether `**Sources:**` header exists in the answer.
- **Citation Compliance**:
  - 50% for having a Sources section.
  - 50% for meeting the minimum required citation count.
- **Refusal Correctness**:
  - Validates if the model correctly refused (for out-of-scope queries).
  - Penalizes "false positive" refusals where the model refuses to answer a valid query.

## Viewing Results in Opik

The framework uses the `opik.evaluate()` API to create **Experiments**, which allow for side-by-side comparison of different RAG configurations.

1. Go to [Opik Dashboard](https://www.comet.com/opik/arjun-gupta/projects)
2. Select your project: `internal-knowledge-assistant-eval`
3. Click on the **Experiments** tab to see all evaluation runs.
4. Drill down into an experiment to see:
   - **Summary metrics** across the whole run.
   - **Individual traces** for every query.
   - **Feedback scores** (custom metrics) for each sample.
   - **Input/Output/Expected Output** comparison.

## Debugging Common Issues

### Low Recall

- **Check indexing**: Ensure the user has indexed the expected documents
- **Check user_id**: Verify the correct user ID is being used
- **Check file_ids**: Confirm `expected_file_ids` match the actual Drive IDs

### Citation Not Detected

- **Check response format**: The RAG formatter must include `**Sources:**`
- **Check retrieval**: Sources can only cite retrieved documents

### Incorrect Refusal Detection

- **Too permissive**: Add more refusal patterns to `metrics.py`
- **Too strict**: Check if valid answers contain refusal-like phrases

### Adapter Initialization Fails

1. Check environment variables are loaded
2. Verify Milvus connection works
3. Confirm user has indexed documents previously

## Extending the Framework

### Adding New Metrics

1. Add the computation logic to `metrics.py`.
2. Add a corresponding `BaseMetric` class to `opik_metrics.py` to sync with the Opik dashboard.
3. Add the field to `EvalResult` in `schema.py`.
4. Update `compute_metrics()` in `metrics.py` to populate the new field for local summary output.
5. Add the new Opik metric to `scoring_metrics` in `adapters.py`.

### Adding New Datasets

1. Create JSONL file in `evals/datasets/`
2. Create corresponding `file_id_mapping.json`
3. Run with `--dataset evals/datasets/<new_dataset>.jsonl`

## Troubleshooting

### "Failed to initialize RAG adapter"

- Milvus connection failed
- No indexed data for the user
- Missing OpenAI API key

### "Opik logging disabled"

- `OPIK_API_KEY` not set
- `OPIK_ENABLED=false` in environment

### Slow Performance

- Each query runs through full RAG pipeline
- Use `--limit N` for quick tests
- Consider running overnight for large datasets
