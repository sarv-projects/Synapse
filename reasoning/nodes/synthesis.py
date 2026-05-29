"""Node 6: Synthesis — Llama 3.3 70B produces structured Markdown from analysis."""
import logging

from reasoning.graph.state import ReasoningState
from providers.protocol import InferenceConfig
from providers.groq_provider import GroqProvider
from prompt.assembler import PromptAssembler

logger = logging.getLogger(__name__)


async def synthesis_node(state: ReasoningState) -> ReasoningState:
    state["current_node"] = "synthesis"

    provider = GroqProvider("llama-3.3-70b-versatile")
    assembler = PromptAssembler()

    # Build a clean context packet for the 70B model
    import json
    context_parts = [
        f"QUERY: {state['query']}",
        f"SUB-QUESTIONS: {json.dumps(state['sub_questions'])}",
        f"CLAIM-EVIDENCE MAP: {json.dumps(state.get('claim_evidence_map', [])[:20], indent=2)}",
        f"CONTRADICTIONS: {json.dumps(state.get('contradiction_flags', []))}",
    ]

    retrieval_text = "\n".join([
        r.get("content") or r.get("snippet") or str(r)
        for r in state.get("retrieval_context", [])[:10]
    ])
    if retrieval_text:
        context_parts.append(f"RETRIEVAL CONTEXT:\n{retrieval_text[:3000]}")

    task = "\n\n".join(context_parts)

    prompt = assembler.assemble(
        role="synthesizer",
        task_content=task,
        retrieval_context=[],
        max_tokens=12000,
    )
    config = InferenceConfig(max_tokens=4000, temperature=0.3)

    try:
        result = await provider.generate(prompt, config)
        state["synthesis_markdown"] = result.content
        state["total_tokens_used"]["synthesis"] = result.input_tokens_used + result.output_tokens_used
        state["model_trace"]["synthesis"] = "llama-3.3-70b-versatile"
        logger.info(f"Synthesis: {len(state.get('synthesis_markdown', ''))} chars generated in {result.latency_ms}ms")
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        state["synthesis_markdown"] = f"## Summary\nSynthesis could not be generated: {e}\n"
        state["model_trace"]["synthesis"] = "error"

    return state
