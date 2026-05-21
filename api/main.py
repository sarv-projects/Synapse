from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # Load .env before anything else reads os.environ

from fastapi import FastAPI
from schema.config import get_settings
from api.v1.router import router as v1_router
from api.v1.reasoning import reasoning_router
from api.middleware import add_open_access_middleware

settings = get_settings()

app = FastAPI(
    title="SYNAPSE API",
    description="Systematic, Networked, Yet Natural, Automated, Provenance-aware Schema Engine - Open Access",
    version="4.0.0",
    docs_url="/docs"
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

