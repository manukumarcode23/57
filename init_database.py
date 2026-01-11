import asyncio
import logging
from bot.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing database...")
    await init_db()
    logger.info("✅ Database initialized successfully!")
    logger.info("✅ All tables created!")

if __name__ == "__main__":
    asyncio.run(main())
