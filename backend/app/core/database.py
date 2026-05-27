"""MongoDB client helpers."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the configured MongoDB database."""
    global _client
    settings = get_settings()
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client[settings.MONGO_DB_NAME]


async def init_database() -> None:
    """Create indexes used by auth and review history."""
    db = get_database()
    await db.users.create_index("email", unique=True)
    await db.review_history.create_index([("user_id", 1), ("created_at", -1)])


def close_database() -> None:
    """Close the MongoDB client if it was opened."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
