"""CrewAI Contradiction Detector — sole CrewAI agent in the v4.0 pipeline."""
import json
import logging

from reasoning.graph.state import ReasoningState

logger = logging.getLogger(__name__)

CREWAI_AVAILABLE = False
try:
    from crewai import Agent, Task, Crew
    CREWAI_AVAILABLE = True
except ImportError:
    logger.warning("crewai not installed; Contradiction Detector falls back to plain LangGraph node")


async def run_contradiction_detector_crewai(state: ReasoningState) -> ReasoningState:
    """Run contradiction detection using CrewAI agent scaffolding."""
    if not CREWAI_AVAILABLE or not state.claim_evidence_map:
        return await _run_plain_node(state)

    try:
        claims_json = json.dumps(state.claim_evidence_map[:15], indent=2)

        detector = Agent(
            role="Contradiction Detector",
            goal="Identify contradictory claims across sources, flagging AGREE, CONTRADICT, or UNCERTAIN with source attribution and conflict severity",
            backstory=(
                "You are a meticulous fact-checker for the SYNAPSE AI knowledge graph. "
                "You compare claims from multiple sources, prioritize higher FactTier evidence (T1 > T2 > T3 > T4), "
                "and flag every contradiction with precise source attribution."
            ),
            verbose=False,
            allow_delegation=False,
            llm="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        )

        task = Task(
            description=f"Compare these claims for contradictions:\n\n{claims_json}\n\n"
                        "Return JSON: {{\"contradictions\": [{{\"claim_a\": \"...\", \"claim_b\": \"...\", "
                        "\"verdict\": \"AGREE|CONTRADICT|UNCERTAIN\", \"conflict_severity\": \"low|medium|high\", "
                        "\"explanation\": \"...\"}}]}}",
            expected_output="JSON object with contradictions array",
            agent=detector,
        )

        crew = Crew(agents=[detector], tasks=[task], verbose=False)
        result = crew.kickoff()

        raw = str(result)
        try:
            parsed = json.loads(raw)
            state.contradiction_flags = parsed.get("contradictions", [])
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}', raw)
            if match:
                parsed = json.loads(match.group())
                state.contradiction_flags = parsed.get("contradictions", [])
            else:
                state.contradiction_flags = []

        state.model_trace["contradiction_detector"] = "crewai:meta-llama/llama-4-scout-17b-16e-instruct"
        logger.info(f"CrewAI contradiction detector: {len(state.contradiction_flags)} contradictions found")
        return state

    except Exception as e:
        logger.warning(f"CrewAI contradiction detector failed, falling back to plain node: {e}")
        return await _run_plain_node(state)


async def _run_plain_node(state: ReasoningState) -> ReasoningState:
    """Plain LangGraph node fallback for contradiction detection."""
    from providers.groq_provider import GroqProvider
    from providers.protocol import InferenceConfig
    from prompt.assembler import PromptAssembler

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
    except Exception:
        state.contradiction_flags = []
    state.model_trace["contradiction_detector"] = "meta-llama/llama-4-scout-17b-16e-instruct"
    return state
