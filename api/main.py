from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.v1.router import router as v1_router
from api.v1.reasoning import reasoning_router
from api.middleware import add_open_access_middleware, _rate_limiter_instance


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    _ = _app.middleware_stack
    if _rate_limiter_instance is not None:
        await _rate_limiter_instance.start()

    # MCP: connect all configured servers
    try:
        from mcp.client import get_mcp_manager
        await get_mcp_manager().connect_all()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"MCP startup failed (non-fatal): {e}")

    # Neon keep-alive: ping every 4 min to prevent compute suspension
    async def _neon_keepalive():
        while True:
            await asyncio.sleep(240)
            try:
                from schema.config import get_settings
                import asyncpg
                settings = get_settings()
                if settings.postgres_url:
                    conn = await asyncpg.connect(settings.postgres_url)
                    await conn.execute("SELECT 1")
                    await conn.close()
            except Exception:
                pass

    asyncio.create_task(_neon_keepalive())

    yield

    # Shutdown: cancel reasoning background tasks
    from api.v1.reasoning import _background_tasks
    if _background_tasks:
        for task in list(_background_tasks):
            if not task.done():
                _ = task.cancel()
        _ = await asyncio.gather(*[t for t in _background_tasks if not t.done()], return_exceptions=True)
        _background_tasks.clear()

    # Shutdown: stop rate limiter
    if _rate_limiter_instance is not None:
        await _rate_limiter_instance.stop()

    # Shutdown: persist budget state to DynamoDB
    try:
        from budget.oracle import get_budget_oracle
        await get_budget_oracle().persist()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Budget persist on shutdown failed: {e}")

    # Shutdown: close MCP servers
    try:
        from mcp.client import get_mcp_manager
        await get_mcp_manager().close_all()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"MCP shutdown failed (non-fatal): {e}")

    # Shutdown: clean up resource pools
    try:
        from embedding.generator import close_embedding_generator
        await close_embedding_generator()

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

add_open_access_middleware(app)
app.include_router(v1_router)
app.include_router(reasoning_router)


@app.get("/")
async def root():
    return {
        "service": "SYNAPSE",
        "version": "4.0.0",
        "api_version": "v1",
        "docs": "/docs"
    }
