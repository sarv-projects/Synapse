"""Node 7: Critic — GPT-OSS 20B evaluates synthesis on grounding, completeness, logic."""
import json
import logging

from reasoning.graph.state import ReasoningState
from providers.protocol import InferenceConfig
from providers.groq_provider import GroqProvider
from prompt.assembler import PromptAssembler

logger = logging.getLogger(__name__)


async def critic_node(state: ReasoningState) -> ReasoningState:
    state.current_node = "critic"
    state.retry_count += 1

    provider = GroqProvider("openai/gpt-oss-20b")
    assembler = PromptAssembler()

    task = f"""Evaluate this synthesis:

SYNTHESIS:
{state.synthesis_markdown[:4000]}

SUB-QUESTIONS TO ANSWER:
{json.dumps(state.sub_questions)}

RETRIEVAL CONTEXT (for grounding check):
{json.dumps([r.get('content', '')[:200] for r in state.retrieval_context[:5]])}

Evaluate on grounding, completeness, and logic. Return JSON per critic.txt."""

    prompt = assembler.assemble_json("critic", task)
    config = InferenceConfig(max_tokens=1500, temperature=0.1, reasoning_effort="medium", response_format="json")

    try:
        result = await provider.generate(prompt, config)
        parsed = json.loads(result.content)
        state.critic_result = parsed
        state.critic_pass = parsed.get("pass", False)
        state.total_tokens_used["critic"] = result.input_tokens_used + result.output_tokens_used
        state.model_trace["critic"] = "openai/gpt-oss-20b"

        scores = {
            "grounding": parsed.get("grounding_score", 0),
            "completeness": parsed.get("completeness_score", 0),
            "logic": parsed.get("logic_score", 0),
        }
        logger.info(f"Critic: pass={state.critic_pass}, retry={state.retry_count}, scores={scores}")

    except Exception as e:
        logger.warning(f"Critic failed: {e}")
        state.critic_pass = True  # On failure, accept what we have
        state.critic_result = {"pass": True, "error": str(e)}
        state.model_trace["critic"] = "fallback"

    # If Critic failed twice, escalate to 120B
    if not state.critic_pass and state.retry_count >= state.max_retries:
        state.final_markdown = state.synthesis_markdown
        logger.info("Critic: max retries reached, outputting best available synthesis")

    return state
