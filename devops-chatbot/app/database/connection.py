from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MongoManager:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None

# Global MongoDB manager instance
mongodb = MongoManager()

async def connect_to_mongo():
    """Create database connection"""
    try:
        logger.info("Connecting to MongoDB...")
        mongodb.client = AsyncIOMotorClient(settings.MONGODB_URL)
        mongodb.database = mongodb.client[settings.MONGODB_DATABASE]
        
        # Test the connection
        await mongodb.client.admin.command('ping')
        logger.info(f"Successfully connected to MongoDB database: {settings.MONGODB_DATABASE}")
        
        # Create indexes for better performance
        await create_indexes()
        
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error connecting to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Close database connection"""
    if mongodb.client:
        mongodb.client.close()
        logger.info("Disconnected from MongoDB")

async def create_indexes():
    """Create database indexes for better performance"""
    try:
        # Index on user_id and channel for faster conversation lookups
        await mongodb.database.conversations.create_index([("user_id", 1), ("channel", 1)])
        
        # Index on timestamp for sorting messages
        await mongodb.database.conversations.create_index([("created_at", -1)])
        
        # Index on deployment logs
        await mongodb.database.deployment_logs.create_index([("timestamp", -1)])
        
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")

def get_database():
    """Get database instance"""
    return mongodb.database
