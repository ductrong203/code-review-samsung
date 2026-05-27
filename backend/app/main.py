"""FastAPI application factory."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.database import close_database, init_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logging.getLogger("app.agents").setLevel(logging.DEBUG)
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:8100",
            "http://127.0.0.1:8100",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router)

    @app.on_event("startup")
    async def startup():
        logger.info("CodeReview Bot starting up...")
        await init_database()

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("CodeReview Bot shutting down...")
        close_database()

    return app


app = create_app()
