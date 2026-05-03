"""
Code Review Bot — FastAPI Application Factory

Creates and configures the FastAPI application with CORS, routers, and middleware.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CodeReview Bot",
        description="AI-powered code review chatbot using LangChain + Ollama/Gemini",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",     # Vite dev server
            "http://localhost:3000",     # Fallback
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(v1_router)

    @app.on_event("startup")
    async def startup():
        logger.info("🚀 CodeReview Bot starting up...")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("👋 CodeReview Bot shutting down...")

    return app


app = create_app()
