"""Node 2: Decomposition — GPT-OSS 20B breaks query into sub-questions + search plan."""
import json
import logging

from reasoning.graph.state import ReasoningState
from providers.protocol import InferenceConfig
from providers.groq_provider import GroqProvider
from prompt.assembler import PromptAssembler

logger = logging.getLogger(__name__)


async def decomposition_node(state: ReasoningState) -> ReasoningState:
    state["current_node"] = "decomposition"

    provider = GroqProvider("openai/gpt-oss-20b")
    assembler = PromptAssembler()

    task = f"""Decompose this analytical query into sub-questions and search queries:

QUERY: {state['query']}

Generate a JSON object with:
- sub_questions: list of strings (ranked by dependency order, 3-7 questions)
- search_queries: list of objects with fields: query (string), type (direct|synonym|evidence-seeking|contrapoint|recent|site-specific|adjacent), expected_information (string), priority (1-5)
- retrieval_strategy: "vector" | "bm25" | "hybrid" | "graph" — which index to hit first
- complexity_per_subquestion: object mapping sub-question index to "low"|"medium"|"high"
- merge_strategy: "weighted" | "ranked" | "interleaved" — how to merge results

Return ONLY valid JSON. No markdown, no prose."""

    prompt = assembler.assemble_json("decomposition", task)
    config = InferenceConfig(max_tokens=1500, temperature=0.1, reasoning_effort="low", response_format="json")

    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state["sub_questions"] = parsed.get("sub_questions", [state["query"]])
        state["search_queries"] = parsed.get("search_queries", [{"query": state["query"], "type": "direct", "priority": 1}])
        state["retrieval_strategy"] = parsed.get("retrieval_strategy", "hybrid")
        state["complexity_per_subquestion"] = parsed.get("complexity_per_subquestion", {})
        state["merge_strategy"] = parsed.get("merge_strategy", "ranked")
        state["model_trace"]["decomposition"] = "openai/gpt-oss-20b"
        state["total_tokens_used"]["decomposition"] = result.input_tokens_used + result.output_tokens_used
        logger.info(f"Decomposition: {len(state['sub_questions'])} sub-questions, {len(state['search_queries'])} search queries")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Decomposition JSON parse failed: {e}. Using fallback decomposition.")
        state["sub_questions"] = [state["query"]]
        state["search_queries"] = [{"query": state["query"], "type": "direct", "priority": 1}]
        state["retrieval_strategy"] = "hybrid"
        state["model_trace"]["decomposition"] = "fallback"

    return state
