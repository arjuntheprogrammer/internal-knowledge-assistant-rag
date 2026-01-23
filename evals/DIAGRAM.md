# RAG Evaluation Pipeline Diagram

This document provides a detailed, end-to-end explanation of how the RAG evaluation system works, focusing on the flow from CLI invocation to metric reporting and Opik integration.

## End-to-End Pipeline Flow

```mermaid
flowchart TD
    Start([CLI: python -m evals.runner.run_eval]) --> Init[Initialize Environment]

    subgraph Initialization ["⚙️ Initialization Phase"]
        Init --> LoadEnv[Load .env & REPO_ROOT]
        LoadEnv --> Args[Parse CLI Arguments]
        Args --> LoadDataset[Load JSONL Dataset & File Mappings]
        LoadDataset --> Validate[Validate Dataset Path & Samples]
    end

    subgraph Adapters ["🔌 Adapter Setup"]
        Validate --> InitRAGAdapter[Initialize RAGAdapter]
        InitRAGAdapter --> RebuildIndex{Rebuild Index?}
        RebuildIndex -->|Yes| Milvus[Connect to Milvus & Rebuild VectorStoreIndex]
        RebuildIndex -->|No| RAGService[Use existing RAGService instance]

        InitRAGAdapter --> InitOpikAdapter[Initialize OpikAdapter]
        InitOpikAdapter --> OpikConfig{Opik Configured?}
        OpikConfig -->|Yes| OpikClient[Create Opik Client & Dataset]
        OpikConfig -->|No| OpikDisabled[Disable Opik Logging]
    end

    Adapters --> EvalMode{Use Opik Experiment?}

    subgraph OpikExperiment ["🔬 Opik Experiment Flow (opik.evaluate)"]
        EvalMode -->|True| UploadItems[Upload Dataset Items to Opik]
        UploadItems --> DefineTask[Define Sync Evaluation Task]
        DefineTask --> ScoringMetrics[Load Opik Custom Metrics:<br/>Recall@k, CitationCompliance, RefusalCorrect]
        ScoringMetrics --> Evaluate[Call opik.evaluate]

        subgraph InternalThread ["🔄 Parallel Execution (task_threads=10)"]
            Evaluate --> QueryRAG[RAGAdapter.query]
            QueryRAG --> RAGResult[Extract answer_md, citations, refused flag]
            RAGResult --> Score[Compute Scores per Metric]
        end

        Score --> ExperimentResult[Create Opik Experiment Dashboard]
    end

    subgraph ManualEval ["📝 Manual Evaluation Flow (Fallback/Local)"]
        EvalMode -->|False| ManualLoop[Loop through Dataset Samples]

        subgraph SampleProcessing ["🔄 Single Query Cycle"]
            ManualLoop --> RunQuery[run_single_query]
            RunQuery --> ProductionRAG[Execute Production RAG Pipeline:<br/>Retrieve -> Rerank -> LLM]
            ProductionRAG --> Capture[Capture latency, file_ids, node_ids]
            Capture --> LocalMetrics[compute_metrics]
            LocalMetrics --> Deterministic[Deterministic Checks:<br/>Recall@K, Citation Count, Refusal Detection]
        end

        Deterministic --> Accumulate[Accumulate Results & Compute Summary]
        Accumulate --> PrintSummary[Print Detailed Stats to Console]
        PrintSummary --> SaveLocal[Save JSONL/JSON Results to evals/runs/]
        SaveLocal --> LogTraces[OpikAdapter.log_evaluation_run]
        LogTraces --> TraceOpik[Log Traces & Summary to Opik Dashboard]
    end

    ExperimentResult --> End([Evaluation Complete])
    TraceOpik --> End
```

## Component Breakdown

### 1. The Runner (`run_eval.py`)
The orchestrator. It manages the two distinct evaluation branches:
- **Experiment Mode**: Modern, parallelized evaluation leveraging the Opik SDK's comparison features.
- **Manual Mode**: Classic sequential loop useful for local debugging and saving results to disk.

### 2. The RAG Adapter (`adapters.py`)
The bridge to the production system. It ensures that evaluations run against the **exact same code** that users interact with.
- It initializes the `RAGService`.
- It converts the production `SystemOutput` back into a format suitable for metric calculation.

### 3. Metric Engines (`metrics.py` & `opik_metrics.py`)
- **Deterministic Metrics**: Fast, rule-based checks for recall (are the right files found?) and citation compliance (did it cite them correctly?).
- **Refusal Correctness**: Specialized logic to verify that the system refuses exactly when it should (out-of-scope) and answers exactly when it can (grounded).

### 4. Opik Integration
- **Datasets**: Versioned collections of input queries and expected outputs.
- **Experiments**: Side-by-side comparisons of different system versions.
- **Tracing**: High-fidelity logs of internal retrieval steps and LLM intermediate outputs.
