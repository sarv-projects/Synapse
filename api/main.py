from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.v1.router import router as v1_router
from api.v1.reasoning import reasoning_router
from api.middleware import add_open_access_middleware, _rate_limiter_instance


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: ensure middleware instances are created and start background tasks
    _ = _app.middleware_stack
    if _rate_limiter_instance is not None:
        await _rate_limiter_instance.start()

    yield

    # Shutdown: cancel all tracked background tasks from reasoning.py
    from api.v1.reasoning import _background_tasks
    if _background_tasks:
        for task in list(_background_tasks):
            if not task.done():
                _ = task.cancel()
        _ = await asyncio.gather(*[t for t in _background_tasks if not t.done()], return_exceptions=True)
        _background_tasks.clear()

    # Shutdown: stop middleware background tasks
    if _rate_limiter_instance is not None:
        await _rate_limiter_instance.stop()

    # Shutdown: clean up resource pools
    try:
        from embedding.generator import close_embedding_generator
        close_embedding_generator()

        from ingestion.neo4j.client import close_neo4j_client
        await close_neo4j_client()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Shutdown cleanup failed: {e}")


app = FastAPI(
    title="SYNAPSE API",
    description="Systematic, Networked, Yet Natural, Automated, Provenance-aware Schema Engine - Open Access",
    version="4.0.0",
    docs_url="/docs",
    lifespan=lifespan
)

# Add open access middleware (no authentication required)
add_open_access_middleware(app)

# Include v1 router (v3.0 endpoints)
app.include_router(v1_router)

# Include v4.0 reasoning router
app.include_router(reasoning_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "SYNAPSE",
        "version": "4.0.0",
        "api_version": "v1",
        "docs": "/docs"
    }
