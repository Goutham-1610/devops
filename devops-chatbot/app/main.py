from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager

from app.core.config import settings
from app.database.connection import connect_to_mongo, close_mongo_connection
from app.api.slack import router as slack_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting DevOps ChatBot...")
    await connect_to_mongo()
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down DevOps ChatBot...")
    await close_mongo_connection()
    logger.info("Application shutdown complete")

# Create FastAPI application
app = FastAPI(
    title="DevOps ChatBot",
    description="A Slack bot for DevOps automation and monitoring",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include routers
app.include_router(slack_router, prefix="/slack", tags=["Slack"])

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "message": "DevOps ChatBot is running!",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/health")
async def health_check():
    """Detailed health check endpoint"""
    return {
        "status": "healthy",
        "service": "devops-chatbot",
        "version": "1.0.0",
        "database": "connected",
        "environment": "development" if settings.DEBUG else "production"
    }

@app.get("/api/stats")
async def api_stats():
    """API usage statistics"""
    from app.services.monitor import get_system_stats
    stats = await get_system_stats()
    return {"system_stats": stats}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
