"""Node 5: Analysis Crew — Extractor (8B) + Analyzer (Scout) + ContradictionDetector + SubagentManager for complex sub-questions."""
import json
import logging

from reasoning.graph.state import ReasoningState
from providers.protocol import InferenceConfig, AssembledPrompt
from providers.groq_provider import GroqProvider
from prompt.assembler import PromptAssembler

logger = logging.getLogger(__name__)


def _build_context_text(state: ReasoningState) -> str:
    parts = []
    for r in state.get("retrieval_context", [])[:15]:
        content = r.get("content") or r.get("snippet") or str(r)
        if content:
            parts.append(content[:300])
    for r in state.get("web_results", [])[:5]:
        content = r.get("content_md") or r.get("snippet") or str(r)
        if content:
            parts.append(content[:300])
    return "\n\n".join(parts)


async def _run_extractor(context: str, state: ReasoningState) -> ReasoningState:
    provider = GroqProvider("llama-3.1-8b-instant")
    assembler = PromptAssembler()
    task = f"Extract factual claims from context:\n\n{context}"
    prompt = assembler.assemble_json("extractor", task)
    config = InferenceConfig(max_tokens=1000, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state["extracted_claims"] = parsed if isinstance(parsed, list) else []
        state["total_tokens_used"]["extractor"] = result.input_tokens_used + result.output_tokens_used
        state["model_trace"]["extractor"] = "llama-3.1-8b-instant"
    except Exception as e:
        logger.warning(f"Extractor failed: {e}")
        state["extracted_claims"] = []
    return state


async def _run_analyzer(context: str, state: ReasoningState) -> ReasoningState:
    provider = GroqProvider("meta-llama/llama-4-scout-17b-16e-instruct")
    assembler = PromptAssembler()
    claims_json = json.dumps(state.get("extracted_claims", [])[:20], indent=2)
    task = f"Analyze these claims against the context. Resolve conflicts by FactTier.\n\nCLAIMS:\n{claims_json}\n\nCONTEXT:\n{context[:3000]}"
    prompt = assembler.assemble_json("analyzer", task)
    config = InferenceConfig(max_tokens=1500, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state["claim_evidence_map"] = parsed.get("claim_evidence_map", [])
        state["total_tokens_used"]["analyzer"] = result.input_tokens_used + result.output_tokens_used
        state["model_trace"]["analyzer"] = "meta-llama/llama-4-scout-17b-16e-instruct"
    except Exception as e:
        logger.warning(f"Analyzer failed: {e}")
        state["claim_evidence_map"] = []
    return state


async def _run_contradiction_detector(context: str, state: ReasoningState) -> ReasoningState:
    provider = GroqProvider("meta-llama/llama-4-scout-17b-16e-instruct")
    assembler = PromptAssembler()
    claims_json = json.dumps(state.get("claim_evidence_map", [])[:15], indent=2)
    task = f"Compare these claims for contradictions:\n\n{claims_json}"
    prompt = assembler.assemble_json("contradiction_detector", task)
    config = InferenceConfig(max_tokens=1000, temperature=0.1, response_format="json")
    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state["contradiction_flags"] = parsed.get("contradictions", [])
        state["total_tokens_used"]["contradiction_detector"] = result.input_tokens_used + result.output_tokens_used
        state["model_trace"]["contradiction_detector"] = "meta-llama/llama-4-scout-17b-16e-instruct"
    except Exception as e:
        logger.warning(f"Contradiction detector failed: {e}")
        state["contradiction_flags"] = []
    return state


async def _run_contradiction_detector_crewai(context: str, state: ReasoningState) -> ReasoningState:
    try:
        from reasoning.nodes.contradiction_detector import run_contradiction_detector_crewai
        return await run_contradiction_detector_crewai(state)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"CrewAI contradiction detector unavailable: {e}")
    return await _run_contradiction_detector(context, state)


async def _run_subagents_for_complex(state: ReasoningState) -> ReasoningState:
    """Spawn SubagentManager for sub-questions marked as 'high' complexity."""
    complexity = state.get("complexity_per_subquestion") or {}
    sub_questions = state.get("sub_questions") or []
    complex_indices = [
        i for i, sq in enumerate(sub_questions)
        if str(complexity.get(str(i), complexity.get(i, "low"))).lower() == "high"
    ]
    if not complex_indices:
        return state

    from reasoning.subagents.manager import get_subagent_manager
    manager = get_subagent_manager()

    subagent_results = []
    for idx in complex_indices[:3]:  # cap at 3 to control budget
        sq = sub_questions[idx]
        # Temporarily set query to the sub-question for the subagent
        sub_state = {**state, "query": sq}
        result, tokens, success = await manager.spawn(
            sub_state,
            task_type="analysis",
            max_tokens=1500,
            max_duration=45,
        )
        if success:
            subagent_results.append({
                "sub_question": sq,
                "result": result.get("result", ""),
                "model": result.get("model", ""),
            })
            state["total_tokens_used"][f"subagent_{idx}"] = tokens
            state["model_trace"][f"subagent_{idx}"] = result.get("model", "unknown")

    if subagent_results:
        # Inject subagent results into retrieval_context so synthesis can use them
        for r in subagent_results:
            state["retrieval_context"].append({
                "content": r["result"],
                "source": "subagent",
                "title": r["sub_question"][:80],
                "score": 0.9,
            })
        logger.info(f"Subagents: {len(subagent_results)} complex sub-questions resolved")

    return state


async def analysis_crew_node(state: ReasoningState) -> ReasoningState:
    state["current_node"] = "analysis_crew"

    context = _build_context_text(state)
    if not context:
        context = state.get("query", "")

    # Run subagents for complex sub-questions before main analysis
    state = await _run_subagents_for_complex(state)

    state = await _run_extractor(context, state)
    state = await _run_analyzer(context, state)
    state = await _run_contradiction_detector_crewai(context, state)

    logger.info(
        f"Analysis: {len(state.get('extracted_claims', []))} claims extracted, "
        f"{len(state.get('claim_evidence_map', []))} evidenced, "
        f"{len(state.get('contradiction_flags', []))} contradictions"
    )
    return state
