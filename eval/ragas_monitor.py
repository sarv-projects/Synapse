"""RAGAS monitoring — evaluates retrieval quality and answer accuracy per session."""
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

RAGAS_AVAILABLE = False
try:
    from ragas import evaluate, EvaluationDataset, SingleTurnSample
    from ragas.metrics import (
        Faithfulness,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        FactualCorrectness,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    RAGAS_AVAILABLE = True
except ImportError:
    logger.info("ragas not installed; evaluation metrics unavailable")


def _get_ragas_llm():
    from langchain_groq import ChatGroq
    from schema.config import get_settings
    settings = get_settings()
    key = settings.groq_api_keys.split(",")[0].strip() if settings.groq_api_keys else settings.groq_api_key
    if not key:
        raise RuntimeError("No Groq API key configured for RAGAS")
    llm = ChatGroq(model="llama-3.1-8b-instant", api_key=key, temperature=0)
    return LangchainLLMWrapper(llm)


def _get_ragas_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    embeddings = HuggingFaceEmbeddings(model_name="thenlper/gte-small")
    return LangchainEmbeddingsWrapper(embeddings)


@dataclass
class EvalScore:
    query: str
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    factual_correctness: float = 0.0
    retrieval_confidence: float = 0.0
    total_tokens: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    model_trace: dict[str, str] = field(default_factory=dict)


class RagasMonitor:
    """Evaluates each pipeline run using RAGAS LLM-as-judge metrics."""

    def __init__(self):
        self.scores: list[EvalScore] = []

    @property
    def total_runs(self) -> int:
        return len(self.scores)

    @property
    def avg_faithfulness(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.faithfulness for s in self.scores) / len(self.scores)

    @property
    def avg_relevancy(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.answer_relevancy for s in self.scores) / len(self.scores)

    @property
    def avg_precision(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.context_precision for s in self.scores) / len(self.scores)

    @property
    def avg_recall(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.context_recall for s in self.scores) / len(self.scores)

    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        reference: str = "",
        retrieval_confidence: float = 0.0,
        total_tokens: int = 0,
        model_trace: dict[str, str] | None = None,
    ) -> EvalScore:
        score = EvalScore(
            query=query,
            retrieval_confidence=retrieval_confidence,
            total_tokens=total_tokens,
            model_trace=model_trace or {},
        )

        if not RAGAS_AVAILABLE:
            logger.debug("RAGAS not available, skipping evaluation")
            self.scores.append(score)
            return score

        if not contexts or not answer:
            logger.debug("No context or answer to evaluate")
            self.scores.append(score)
            return score

        try:
            sample = SingleTurnSample(
                user_input=query,
                response=answer,
                retrieved_contexts=contexts,
                reference=reference or None,
            )
            dataset = EvaluationDataset(samples=[sample])

            llm = _get_ragas_llm()
            embeddings = _get_ragas_embeddings()

            # ContextRecall and FactualCorrectness require a non-empty reference
            has_reference = bool(reference and reference.strip())
            metrics = [Faithfulness(), AnswerRelevancy(), ContextPrecision()]
            if has_reference:
                metrics += [ContextRecall(), FactualCorrectness()]

            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=llm,
                embeddings=embeddings,
            )

            df = result.to_pandas()
            if not df.empty:
                row = df.iloc[0].to_dict()
                score.faithfulness = float(row.get("faithfulness", 0) or 0)
                score.answer_relevancy = float(row.get("answer_relevancy", 0) or 0)
                score.context_precision = float(row.get("context_precision", 0) or 0)
                if has_reference:
                    score.context_recall = float(row.get("context_recall", 0) or 0)
                    score.factual_correctness = float(row.get("factual_correctness", 0) or 0)

            logger.info(
                f"RAGAS eval: faithfulness={score.faithfulness:.2f} "
                f"relevancy={score.answer_relevancy:.2f} "
                f"precision={score.context_precision:.2f} "
                f"recall={score.context_recall:.2f} "
                f"factual_correctness={score.factual_correctness:.2f}"
            )
        except Exception as e:
            logger.warning(f"RAGAS evaluation failed: {e}")

        self.scores.append(score)
        if len(self.scores) > 500:
            self.scores = self.scores[-250:]

        return score

    def latest(self) -> EvalScore | None:
        return self.scores[-1] if self.scores else None

    def summary(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "avg_faithfulness": round(self.avg_faithfulness, 3),
            "avg_answer_relevancy": round(self.avg_relevancy, 3),
            "avg_context_precision": round(self.avg_precision, 3),
            "avg_context_recall": round(self.avg_recall, 3),
            "last_10": [
                {
                    "query": s.query[:80],
                    "faithfulness": round(s.faithfulness, 3),
                    "relevancy": round(s.answer_relevancy, 3),
                    "precision": round(s.context_precision, 3),
                    "recall": round(s.context_recall, 3),
                    "factual_correctness": round(s.factual_correctness, 3),
                    "timestamp": s.timestamp,
                }
                for s in self.scores[-10:]
            ],
        }


_monitor: RagasMonitor | None = None


def get_ragas_monitor() -> RagasMonitor:
    global _monitor
    if _monitor is None:
        _monitor = RagasMonitor()
    return _monitor
