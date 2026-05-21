"""LangGraph ReasoningState — the state dataclass flowing through all 8 nodes."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningState:
    # Input
    query: str = ""
    session_id: str = ""
    format: str = "markdown"  # markdown | pdf | latex_report

    # Decomposition output
    sub_questions: list[str] = field(default_factory=list)
    search_queries: list[dict] = field(default_factory=list)
    retrieval_strategy: str = ""
    complexity_per_subquestion: dict = field(default_factory=dict)
    merge_strategy: str = ""

    # Retrieval output
    retrieval_context: list[dict] = field(default_factory=list)
    retrieval_confidence: float = 0.0
    web_results: list[dict] = field(default_factory=list)
    web_research_used: bool = False

    # Analysis output
    extracted_claims: list[dict] = field(default_factory=list)
    claim_evidence_map: list[dict] = field(default_factory=list)
    contradiction_flags: list[dict] = field(default_factory=list)

    # Synthesis output
    synthesis_markdown: str = ""

    # Critic output
    critic_result: dict = field(default_factory=dict)
    critic_pass: bool = False
    retry_count: int = 0
    max_retries: int = 2

    # Output
    final_markdown: str = ""
    confidence_map: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    produced_by: str = ""

    # Budget tracking
    budget_snapshot: dict = field(default_factory=dict)
    model_trace: dict[str, str] = field(default_factory=dict)
    total_tokens_used: dict[str, int] = field(default_factory=dict)
    model_used: str = ""

    # Status
    status: str = "PENDING"  # PENDING | PROCESSING | COMPLETE | FAILED
    current_node: str = ""
    error: str = ""
