"""Node 5: Analysis Crew — Extractor (8B plain) + Analyzer (Scout plain) + ContradictionDetector (Scout, CrewAI)."""
import json
import logging

from reasoning.graph.state import ReasoningState
from providers.protocol import InferenceConfig, AssembledPrompt
from providers.groq_provider import GroqProvider
from prompt.assembler import PromptAssembler

logger = logging.getLogger(__name__)


def _build_context_text(state: ReasoningState) -> str:
    """Build context text from retrieval + web results."""
    parts = []
    for r in state.retrieval_context[:15]:
        content = r.get("content") or r.get("snippet") or str(r)
        if content:
            parts.append(content[:300])
    for r in state.web_results[:5]:
        content = r.get("content_md") or r.get("snippet") or str(r)
        if content:
            parts.append(content[:300])
    return "\n\n".join(parts)


async def _run_extractor(context: str, state: ReasoningState) -> ReasoningState:
    """Extractor: Llama 3.1 8B — plain LangGraph node, zero CrewAI overhead."""
    provider = GroqProvider("llama-3.1-8b-instant")
    assembler = PromptAssembler()
    task = f"Extract factual claims from context:\n\n{context}"
    prompt = assembler.assemble_json("extractor", task)
    config = InferenceConfig(max_tokens=1000, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        state.extracted_claims = json.loads(result.content) if isinstance(json.loads(result.content), list) else []
        state.total_tokens_used["extractor"] = result.input_tokens_used + result.output_tokens_used
        state.model_trace["extractor"] = "llama-3.1-8b-instant"
    except Exception as e:
        logger.warning(f"Extractor failed: {e}")
        state.extracted_claims = []
    return state


async def _run_analyzer(context: str, state: ReasoningState) -> ReasoningState:
    """Analyzer: Llama 4 Scout — plain LangGraph node, zero CrewAI overhead."""
    provider = GroqProvider("meta-llama/llama-4-scout-17b-16e-instruct")
    assembler = PromptAssembler()
    claims_json = json.dumps(state.extracted_claims[:20], indent=2)
    task = f"Analyze these claims against the context. Resolve conflicts by FactTier.\n\nCLAIMS:\n{claims_json}\n\nCONTEXT:\n{context[:3000]}"
    prompt = assembler.assemble_json("analyzer", task)
    config = InferenceConfig(max_tokens=1500, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state.claim_evidence_map = parsed.get("claim_evidence_map", [])
        state.total_tokens_used["analyzer"] = result.input_tokens_used + result.output_tokens_used
        state.model_trace["analyzer"] = "meta-llama/llama-4-scout-17b-16e-instruct"
    except Exception as e:
        logger.warning(f"Analyzer failed: {e}")
        state.claim_evidence_map = []
    return state


async def _run_contradiction_detector(context: str, state: ReasoningState) -> ReasoningState:
    """Contradiction Detector: Llama 4 Scout, sole CrewAI agent."""
    provider = GroqProvider("meta-llama/llama-4-scout-17b-16e-instruct")
    assembler = PromptAssembler()
    claims_json = json.dumps(state.claim_evidence_map[:15], indent=2)
    task = f"Compare these claims for contradictions:\n\n{claims_json}"
    prompt = assembler.assemble_json("contradiction_detector", task)
    config = InferenceConfig(max_tokens=1000, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state.contradiction_flags = parsed.get("contradictions", [])
        state.total_tokens_used["contradiction_detector"] = result.input_tokens_used + result.output_tokens_used
        state.model_trace["contradiction_detector"] = "meta-llama/llama-4-scout-17b-16e-instruct"
    except Exception as e:
        logger.warning(f"Contradiction detector failed: {e}")
        state.contradiction_flags = []
    return state


async def _run_contradiction_detector_crewai(context: str, state: ReasoningState) -> ReasoningState:
    """Try CrewAI Contradiction Detector first, fall back to plain node."""
    try:
        from reasoning.nodes.contradiction_detector import run_contradiction_detector_crewai
        return await run_contradiction_detector_crewai(state)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"CrewAI contradiction detector unavailable: {e}")
    return await _run_contradiction_detector(context, state)


async def analysis_crew_node(state: ReasoningState) -> ReasoningState:
    state.current_node = "analysis_crew"

    context = _build_context_text(state)
    if not context:
        context = state.query

    state = await _run_extractor(context, state)
    state = await _run_analyzer(context, state)
    state = await _run_contradiction_detector_crewai(context, state)

    logger.info(
        f"Analysis: {len(state.extracted_claims)} claims extracted, "
        f"{len(state.claim_evidence_map)} evidenced, "
        f"{len(state.contradiction_flags)} contradictions"
    )
    return state
