from fastapi import APIRouter, Request, HTTPException
from slack_sdk.web.async_client import AsyncWebClient
import json
import logging
from app.core.config import settings
from app.core.security import verify_slack_signature
from app.services.monitor import get_system_stats, format_system_stats_for_slack
from app.services.deploy import deploy_application, format_deployment_result_for_slack
from app.services.heal import run_healing_tasks, format_healing_results_for_slack

logger = logging.getLogger(__name__)
router = APIRouter()
client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)

@router.post("/events")
async def slack_events(request: Request):
    """Handle Slack events including URL verification"""
    try:
        body = await request.body()
        
        # Parse JSON payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Slack request")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle URL verification challenge (required for Event Subscriptions)
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            if challenge:
                logger.info(f"Slack URL verification challenge received: {challenge}")
                return {"challenge": challenge}
            else:
                raise HTTPException(status_code=400, detail="Missing challenge parameter")
        
        # Verify Slack signature for all other requests
        verify_slack_signature(request, body)
        
        # Handle app mentions
        if "event" in payload:
            event = payload["event"]
            if event.get("type") == "app_mention":
                await handle_app_mention(event)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/commands")
async def slack_commands(request: Request):
    """Handle Slack slash commands"""
    try:
        body = await request.body()
        verify_slack_signature(request, body)
        
        # Parse form data from Slack
        form_data = {}
        for item in body.decode().split('&'):
            if '=' in item:
                key, value = item.split('=', 1)
                form_data[key] = value.replace('+', ' ')
        
        command = form_data.get('command', '').strip()
        text = form_data.get('text', '').strip()
        channel_id = form_data.get('channel_id')
        user_id = form_data.get('user_id')
        
        # Process the command
        response_text = await process_command(command, text, user_id, channel_id)
        
        return {
            "response_type": "in_channel",
            "text": response_text
        }
        
    except Exception as e:
        logger.error(f"Error handling Slack command: {e}")
        return {
            "response_type": "ephemeral",
            "text": f"❌ Error processing command: {str(e)}"
        }

async def handle_app_mention(event):
    """Handle @bot mentions"""
    try:
        text = event.get("text", "").lower()
        channel = event.get("channel")
        user = event.get("user")
        
        # Remove bot mention from text
        text = " ".join([word for word in text.split() if not word.startswith("<@")])
        
        response = await process_command_text(text, user, channel)
        
        await client.chat_postMessage(
            channel=channel,
            text=response
        )
        
    except Exception as e:
        logger.error(f"Error handling app mention: {e}")

async def process_command(command: str, text: str, user_id: str, channel_id: str) -> str:
    """Process slash commands"""
    return await process_command_text(f"{command} {text}", user_id, channel_id)

async def process_command_text(text: str, user_id: str, channel_id: str) -> str:
    """Process command text and return response"""
    text = text.lower().strip()
    
    try:
        if "status" in text or "health" in text:
            stats = await get_system_stats()
            return await format_system_stats_for_slack(stats)
        
        elif "help" in text:
            return """🤖 **DevOps ChatBot Commands:**
            
• `status` or `health` - Get system status
• `deploy <app_name>` - Deploy/restart application  
• `restart` or `heal` - Run healing operations
• `clean` - Clean disk space
• `help` - Show this help message

**Examples:**
• `@DevOps ChatBot status`
• `/devops deploy nginx`
• `@DevOps ChatBot heal`
"""
        
        elif "deploy" in text:
            # Extract app name from command
            parts = text.split()
            app_name = "nginx"  # default
            for i, part in enumerate(parts):
                if part == "deploy" and i + 1 < len(parts):
                    app_name = parts[i + 1]
                    break
            
            result = await deploy_application(app_name, user_id, channel_id)
            return await format_deployment_result_for_slack(result)
        
        elif "heal" in text or "restart" in text:
            result = await run_healing_tasks(user_id, channel_id)
            return await format_healing_results_for_slack(result)
        
        elif "clean" in text:
            result = await run_healing_tasks(user_id, channel_id, ["clean_disk_space"])
            return await format_healing_results_for_slack(result)
        
        else:
            return "🤔 I don't understand that command. Type `help` to see available commands."
    
    except Exception as e:
        logger.error(f"Command processing error: {e}")
        return f"❌ **Error:** Something went wrong: {str(e)}"
