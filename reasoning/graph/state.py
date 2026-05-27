"""LangGraph ReasoningState — TypedDict flowing through all nodes."""
from typing import Any, TypedDict


class ReasoningState(TypedDict, total=False):
    # Input
    query: str
    session_id: str
    format: str  # markdown | pdf | latex_report

    # Decomposition output
    sub_questions: list[str]
    search_queries: list[dict[str, Any]]
    retrieval_strategy: str
    complexity_per_subquestion: dict[str, Any]
    merge_strategy: str

    # Retrieval output
    retrieval_context: list[dict[str, Any]]
    retrieval_confidence: float
    web_results: list[dict[str, Any]]
    web_research_used: bool

    # Analysis output
    extracted_claims: list[dict[str, Any]]
    claim_evidence_map: list[dict[str, Any]]
    contradiction_flags: list[dict[str, Any]]

    # Synthesis output
    synthesis_markdown: str

    # Critic output
    critic_result: dict[str, Any]
    critic_pass: bool
    retry_count: int
    max_retries: int

    # Output
    final_markdown: str
    confidence_map: dict[str, Any]
    sources: list[dict[str, Any]]
    knowledge_gaps: list[str]
    produced_by: str

    # Budget tracking
    budget_snapshot: dict[str, Any]
    model_trace: dict[str, str]
    total_tokens_used: dict[str, int]
    model_used: str

    # Status
    status: str  # PENDING | PROCESSING | COMPLETE | FAILED
    current_node: str
    error: str
