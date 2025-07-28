from fastapi import APIRouter, Request, HTTPException
from slack_sdk.web.async_client import AsyncWebClient
import json
import logging
from app.core.config import settings
from app.core.security import verify_slack_signature
from app.services.monitor import get_system_stats, check_service_status
from app.services.heal import restart_failed_services, clean_disk_space
from app.services.deploy import deploy_application, get_application_status
logger = logging.getLogger(__name__)
router = APIRouter()
client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)

@router.post("/events")
async def slack_events(request: Request):
    """Handle Slack events"""
    body = await request.body()
    verify_slack_signature(request, body)
    
    payload = json.loads(body)
    
    # URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}
    
    # Handle events
    event = payload.get("event", {})
    if event.get("type") == "app_mention":
        await handle_mention(event)
    
    return {"status": "ok"}

@router.post("/commands")
async def slack_commands(request: Request):
    """Handle Slack slash commands"""
    body = await request.body()
    verify_slack_signature(request, body)
    
    # Parse form data
    form_data = {}
    for item in body.decode().split('&'):
        key, value = item.split('=', 1)
        form_data[key] = value.replace('+', ' ')
    
    command = form_data.get('command')
    text = form_data.get('text', '')
    channel_id = form_data.get('channel_id')
    
    response_text = await process_command(command, text)
    
    return {
        "response_type": "in_channel",
        "text": response_text
    }

async def handle_mention(event):
    """Process app mentions"""
    text = event.get("text", "").lower()
    channel = event.get("channel")
    
    response = await process_command_text(text)
    await client.chat_postMessage(channel=channel, text=response)

async def process_command(command: str, text: str) -> str:
    """Process slash commands"""
    return await process_command_text(f"{command} {text}")

async def process_command_text(text: str) -> str:
    """Process command text and return response"""
    text = text.lower().strip()
    
    try:
        if "status" in text or "health" in text:
            stats = get_system_stats()
            return f"🖥️ **System Status:**\n" \
                   f"• CPU: {stats['cpu_percent']:.1f}%\n" \
                   f"• Memory: {stats['memory_percent']:.1f}%\n" \
                   f"• Disk: {stats['disk_percent']:.1f}%\n" \
                   f"• Uptime: {stats['uptime']}"
        
        elif "deploy" in text:
            # Extract app name from command
            parts = text.split()
            app_name = parts[1] if len(parts) > 1 else "nginx"
            
            result = await deploy_application(app_name)
            if result["success"]:
                return f"🚀 **Deployment Success:** {result['message']}"
            else:
                return f"❌ **Deployment Failed:** {result['message']}"
        
        elif "restart" in text:
            services = ["nginx", "redis", "postgresql"]
            results = restart_failed_services(services)
            
            response = "🔄 **Service Restart Results:**\n"
            for result in results:
                emoji = "✅" if result["success"] else "❌"
                response += f"{emoji} {result['service']}: {result['message']}\n"
            return response
        
        elif "clean" in text:
            result = clean_disk_space()
            if result["action"] == "clean":
                return f"🧹 **Disk Cleanup:** {result['message']}"
            else:
                return f"💾 **Disk Status:** {result['message']}"
        
        elif "help" in text:
            return """🤖 **DevOps ChatBot Commands:**
            
• `status` or `health` - Get system status
• `deploy <app_name>` - Deploy/restart application  
• `restart` - Restart failed services
• `clean` - Clean disk space if needed
• `help` - Show this help message

**Examples:**
• `@botname status`
• `/devops deploy nginx`
• `@botname restart services`
"""
        
        else:
            return "🤔 I don't understand that command. Type `help` to see available commands."
    
    except Exception as e:
        logger.error(f"Command processing error: {e}")
        return f"❌ **Error:** Something went wrong: {str(e)}"
