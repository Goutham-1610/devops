from fastapi import FastAPI
from app.api.slack import router as slack_router
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="DevOps ChatBot",
    description="A Slack bot for DevOps automation",
    version="1.0.0"
)

# Include routers
app.include_router(slack_router, prefix="/slack", tags=["slack"])

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "DevOps ChatBot is running!", "version": "1.0.0"}

@app.get("/health")
async def health():
    """Health check for monitoring"""
    return {"status": "healthy", "service": "devops-chatbot"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )
