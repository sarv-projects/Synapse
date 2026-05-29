"""v4.0 API endpoints: /reason, /reason/{job_id}, /ingest, /budget, /webhook/subscribe."""
import asyncio
from dataclasses import asdict, fields, is_dataclass
import logging
import uuid
from datetime import UTC, datetime

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

reasoning_router = APIRouter(prefix="/api/v1", tags=["v4.0 Reasoning"])


class ReasonRequest(BaseModel):
    query: str
    session_id: str | None = None
    format: str = "markdown"


class WebhookSubscriptionRequest(BaseModel):
    endpoint_url: str
    event_types: list[str] = ["reason.complete"]
    secret_token: str = ""
    owner_id: str = "anonymous"


# In-memory job store (DynamoDB in production)
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()

# Tracked background tasks for graceful shutdown
_background_tasks: set[asyncio.Task[None]] = set()


def _track_task(task: asyncio.Task[None]) -> asyncio.Task[None]:
    """Track a background task so it can be cancelled on shutdown."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _get_job(job_id: str) -> dict | None:
    async with _jobs_lock:
        return _jobs.get(job_id)


async def _set_job(job_id: str, state: dict) -> None:
    async with _jobs_lock:
        _jobs[job_id] = state


async def _update_job(job_id: str, **kwargs) -> None:
    async with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


@reasoning_router.post("/reason")
async def reason(request: ReasonRequest):
    """Submit a deep reasoning query. Returns job_id immediately (async)."""
    job_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    await _set_job(job_id, {
        "job_id": job_id, "status": "PENDING", "current_node": "",
        "query": request.query, "session_id": session_id,
        "format": request.format, "created_at": datetime.now(UTC).isoformat(),
        "result": None,
    })

    # Try SQS queue first, fall back to direct task spawning
    try:
        from budget.sqs_queue import get_sqs_queue
        sqs = get_sqs_queue()
        await sqs.connect()
        enqueued = await sqs.enqueue(job_id, request.query, session_id, request.format)
        if not enqueued:
            _track_task(asyncio.create_task(_run_reasoning_pipeline(job_id, request.query, session_id, request.format)))
    except Exception as e:
        logger.error(f"SQS enqueue failed for job {job_id}, falling back to direct task: {e}", exc_info=True)
        _track_task(asyncio.create_task(_run_reasoning_pipeline(job_id, request.query, session_id, request.format)))

    # Save to DynamoDB for persistence
    try:
        from budget.dynamodb import get_dynamodb_store
        db = get_dynamodb_store()
        await db.connect()
        job = await _get_job(job_id)
        if job:
            await db.save_job(job_id, job)
    except Exception as e:
        logger.error(f"Failed to persist job {job_id} to DynamoDB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save job state")

    return {"job_id": job_id, "status": "PENDING"}


async def _run_reasoning_pipeline(job_id: str, query: str, session_id: str, fmt: str):
    """Run the full 8-node reasoning pipeline asynchronously."""
    try:
        from reasoning.graph.state import ReasoningState
        from reasoning.graph.builder import GraphBuilder
        from schema.config import get_settings

        settings = get_settings()
        state = ReasoningState(
            query=query,
            session_id=session_id,
            format=fmt,
            retry_count=0,
            max_retries=settings.critic_max_retries,
            retrieval_context=[],
            web_results=[],
            extracted_claims=[],
            claim_evidence_map=[],
            contradiction_flags=[],
            model_trace={},
            total_tokens_used={},
            sub_questions=[],
            search_queries=[],
        )
        await _update_job(job_id, status="PROCESSING")

        graph = GraphBuilder().build()
        async for update in graph.astream(state):
            state = _merge_graph_update(state, update)
            if state.current_node:
                await _update_job(job_id, current_node=state.current_node)
            if state.current_node in {"entry", "synthesis", "output"}:
                await _save_checkpoint(state, state.current_node)
            if state.status == "FAILED":
                await _update_job(job_id, status="FAILED", error=state.error)
                await _persist_job(job_id)
                return

        result = {
            "markdown": state.final_markdown,
            "synthesis_markdown": state.synthesis_markdown,
            "confidence_map": state.confidence_map,
            "sources": state.sources,
            "gaps": state.knowledge_gaps,
            "contradictions": state.contradiction_flags,
            "model_trace": state.model_trace,
            "total_tokens": state.total_tokens_used,
            "retrieval_confidence": state.retrieval_confidence,
            "web_research_used": state.web_research_used,
        }
        await _update_job(job_id, status="COMPLETE", result=result, produced_by=state.produced_by)

        # Attach RAGAS evaluation scores
        try:
            from eval.ragas_monitor import get_ragas_monitor
            latest = get_ragas_monitor().latest()
            if latest:
                ragas_eval = {
                    "faithfulness": round(latest.faithfulness, 3),
                    "answer_relevancy": round(latest.answer_relevancy, 3),
                    "context_precision": round(latest.context_precision, 3),
                    "context_recall": round(latest.context_recall, 3),
                }
                await _update_job(job_id, ragas_eval=ragas_eval)
                job = await _get_job(job_id)
                if job and "result" in job:
                    job["result"]["ragas_eval"] = ragas_eval
        except Exception as e:
            logger.error(f"Failed to attach RAGAS eval for job {job_id}: {e}", exc_info=True)

        await _save_checkpoint(state, "output")

    except Exception as e:
        logger.exception(f"Reasoning pipeline failed for {job_id}")
        await _update_job(job_id, status="FAILED", error=str(e))

    await _persist_job(job_id)


def _merge_graph_update(state, update):
    """Merge LangGraph update payloads back into ReasoningState."""
    from reasoning.graph.state import ReasoningState

    valid_fields = set(ReasoningState.__annotations__.keys())

    def state_dict(value) -> dict:
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if k in valid_fields}
        return {}

    merged = state_dict(state)
    if isinstance(update, dict):
        if any(k in valid_fields for k in update):
            merged.update(state_dict(update))
        else:
            for node_name, node_update in update.items():
                if node_name == "__end__":
                    continue
                if isinstance(node_update, dict):
                    merged.update(state_dict(node_update))
                    merged["current_node"] = merged.get("current_node") or node_name

    return ReasoningState(**{k: v for k, v in merged.items() if k in valid_fields})


async def _save_checkpoint(state, name: str):
    try:
        from reasoning.graph.checkpoint import get_checkpoint_store
        store = get_checkpoint_store()
        await store.connect()
        state_dict = {
            "query": state.query, "status": state.status, "session_id": state.session_id,
            "synthesis_markdown": state.synthesis_markdown,
            "final_markdown": state.final_markdown,
            "model_trace": state.model_trace,
            "total_tokens_used": state.total_tokens_used,
        }
        await store.save(state.session_id, name, state_dict)
    except Exception as e:
        logger.error(f"Failed to save checkpoint for session {state.session_id}: {e}", exc_info=True)


async def _persist_job(job_id: str):
    try:
        from budget.dynamodb import get_dynamodb_store
        db = get_dynamodb_store()
        await db.connect()
        job = await _get_job(job_id)
        if job:
            await db.save_job(job_id, job)
    except Exception as e:
        logger.error(f"Failed to persist job {job_id} to DynamoDB: {e}", exc_info=True)


@reasoning_router.get("/reason/{job_id}")
async def get_reason_result(job_id: str, format: str | None = Query(default=None)):
    """Poll for reasoning job result."""
    job = await _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job["status"],
        "current_node": job.get("current_node", ""),
        "query": job.get("query", ""),
        "created_at": job.get("created_at", ""),
    }

    if job["status"] in ("COMPLETE", "FAILED"):
        response["result"] = job.get("result")
        response["error"] = job.get("error")
        response["produced_by"] = job.get("produced_by", "")

    return response


@reasoning_router.post("/ingest")
async def ingest_document(file: UploadFile = File(...), session_id: str | None = Form(default=None)):
    """Upload a document for session-scoped indexing."""
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    doc_id = str(uuid.uuid4())
    sid = session_id or str(uuid.uuid4())

    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB")
    try:
        text = content.decode("utf-8")[:50000]
    except UnicodeDecodeError:
        text = f"[Binary file: {file.filename}, {len(content)} bytes]"

    from retrieval.session_index import get_session_index
    sess_idx = get_session_index(sid)
    sess_idx.add_documents([
        {"url": f"upload://{file.filename}", "title": file.filename, "content_md": text, "fetched_at": datetime.now(UTC).isoformat()}
    ])

    return {
        "document_id": doc_id,
        "filename": file.filename,
        "chunks": max(1, len(text) // 1000),
        "entities_extracted": 0,
        "session_id": sid,
    }


@reasoning_router.get("/budget")
async def get_budget():
    """Get per-model budget status."""
    try:
        from budget.oracle import get_budget_oracle
        oracle = get_budget_oracle()
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "models": oracle.snapshot(),
        }
    except Exception as e:
        return {"error": str(e)}


@reasoning_router.post("/webhook/subscribe")
async def webhook_subscribe(req: WebhookSubscriptionRequest):
    """Subscribe to webhook events including reason.complete."""
    from webhook.registry import get_webhook_registry
    from webhook.registry import WebhookSubscription

    try:
        registry = get_webhook_registry()
        sub = WebhookSubscription(
            endpoint_url=req.endpoint_url,
            event_types=req.event_types,
            secret_token=req.secret_token,
            active=True,
            owner_id=req.owner_id,
        )
        sub_id = registry.register(sub)
        return {"subscription_id": sub_id, "status": "active"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@reasoning_router.get("/eval")
async def get_eval_metrics():
    """RAGAS evaluation metrics — retrieval quality and answer accuracy."""
    try:
        from eval.ragas_monitor import get_ragas_monitor
        monitor = get_ragas_monitor()
        return monitor.summary()
    except Exception as e:
        return {"error": str(e)}
