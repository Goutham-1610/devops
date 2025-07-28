import asyncio
import subprocess
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime
from app.database.connection import get_database
from app.database.models import DeploymentLog
from app.core.security import sanitize_input

logger = logging.getLogger(__name__)

async def deploy_application(app_name: str, user_id: str, channel: str, deployment_type: str = "restart") -> Dict[str, Any]:
    """
    Deploy or restart an application using multiple strategies
    """
    start_time = datetime.utcnow()
    
    # Sanitize inputs to prevent command injection
    app_name = sanitize_input(app_name, max_length=50)
    
    try:
        logger.info(f"Starting {deployment_type} of {app_name} requested by {user_id}")
        
        # Create deployment log entry
        deployment_log = DeploymentLog(
            app_name=app_name,
            user_id=user_id,
            channel=channel,
            command=deployment_type,
            status="in_progress"
        )
        
        # Store initial log
        db = get_database()
        log_id = None
        if db:
            result = await db.deployment_logs.insert_one(deployment_log.dict(by_alias=True))
            log_id = result.inserted_id
        
        # Try different deployment strategies in order of preference
        success = False
        output = ""
        error = ""
        strategy_used = ""
        
        # Strategy 1: Docker container management
        if await is_docker_container(app_name):
            success, output, error = await handle_docker_container(app_name, deployment_type)
            strategy_used = "docker_container"
        
        # Strategy 2: Docker Compose service
        elif await is_docker_compose_service(app_name):
            success, output, error = await handle_docker_compose_service(app_name, deployment_type)
            strategy_used = "docker_compose"
        
        # Strategy 3: System service management
        elif await is_system_service(app_name):
            success, output, error = await handle_system_service(app_name, deployment_type)
            strategy_used = "system_service"
        
        # Strategy 4: PM2 process management (Node.js apps)
        elif await is_pm2_process(app_name):
            success, output, error = await handle_pm2_process(app_name, deployment_type)
            strategy_used = "pm2_process"
        
        else:
            # Fallback: treat as system service
            success, output, error = await handle_system_service(app_name, deployment_type)
            strategy_used = "system_service_fallback"
        
        # Calculate execution time
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # Update deployment log
        status = "success" if success else "failed"
        if db and log_id:
            await db.deployment_logs.update_one(
                {"_id": log_id},
                {
                    "$set": {
                        "status": status,
                        "execution_time": execution_time,
                        "details": {
                            "strategy_used": strategy_used,
                            "output": output,
                            "error": error,
                            "completed_at": end_time
                        }
                    }
                }
            )
        
        # Build response
        result = {
            "success": success,
            "app_name": app_name,
            "strategy_used": strategy_used,
            "execution_time": round(execution_time, 2),
            "timestamp": end_time.isoformat()
        }
        
        if success:
            result["message"] = f"✅ Successfully {deployment_type}ed {app_name} using {strategy_used}"
            result["output"] = output[:500] if output else "No output"  # Limit output length
        else:
            result["message"] = f"❌ Failed to {deployment_type} {app_name}"
            result["error"] = error[:500] if error else "Unknown error"
            
        return result
        
    except Exception as e:
        logger.error(f"Deployment error for {app_name}: {e}")
        return {
            "success": False,
            "app_name": app_name,
            "message": f"💥 Deployment failed with exception: {str(e)}",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

async def is_docker_container(name: str) -> bool:
    """Check if name corresponds to a Docker container"""
    try:
        result = await asyncio.create_subprocess_exec(
            'docker', 'ps', '-a', '--filter', f'name=^{name}$', '--format', '{{.Names}}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        containers = stdout.decode().strip().split('\n')
        return name in containers and containers != ['']
    except Exception as e:
        logger.debug(f"Docker container check failed for {name}: {e}")
        return False

async def is_docker_compose_service(name: str) -> bool:
    """Check if name corresponds to a Docker Compose service"""
    try:
        result = await asyncio.create_subprocess_exec(
            'docker-compose', 'ps', '-q', name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        return result.returncode == 0 and stdout.decode().strip() != ""
    except Exception as e:
        logger.debug(f"Docker Compose service check failed for {name}: {e}")
        return False

async def is_system_service(name: str) -> bool:
    """Check if name corresponds to a system service"""
    try:
        result = await asyncio.create_subprocess_exec(
            'systemctl', 'list-units', '--type=service', f'{name}.service',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        return result.returncode == 0 and name in stdout.decode()
    except Exception as e:
        logger.debug(f"System service check failed for {name}: {e}")
        return False

async def is_pm2_process(name: str) -> bool:
    """Check if name corresponds to a PM2 process"""
    try:
        result = await asyncio.create_subprocess_exec(
            'pm2', 'list', '--format',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        return result.returncode == 0 and name in stdout.decode()
    except Exception as e:
        logger.debug(f"PM2 process check failed for {name}: {e}")
        return False

async def handle_docker_container(name: str, action: str) -> Tuple[bool, str, str]:
    """Handle Docker container operations"""
    try:
        if action == "restart":
            # Restart container
            result = await asyncio.create_subprocess_exec(
                'docker', 'restart', name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        elif action == "deploy":
            # Stop, pull latest image, and start
            commands = [
                ['docker', 'stop', name],
                ['docker', 'pull', name],
                ['docker', 'start', name]
            ]
            
            combined_output = []
            combined_error = []
            
            for cmd in commands:
                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                combined_output.append(stdout.decode())
                combined_error.append(stderr.decode())
                
                if result.returncode != 0:
                    return False, '\n'.join(combined_output), '\n'.join(combined_error)
            
            return True, '\n'.join(combined_output), '\n'.join(combined_error)
        
        stdout, stderr = await result.communicate()
        success = result.returncode == 0
        return success, stdout.decode(), stderr.decode()
        
    except Exception as e:
        return False, "", str(e)

async def handle_docker_compose_service(name: str, action: str) -> Tuple[bool, str, str]:
    """Handle Docker Compose service operations"""
    try:
        if action == "restart":
            cmd = ['docker-compose', 'restart', name]
        elif action == "deploy":
            cmd = ['docker-compose', 'up', '-d', '--force-recreate', name]
        else:
            cmd = ['docker-compose', 'restart', name]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        success = result.returncode == 0
        return success, stdout.decode(), stderr.decode()
        
    except Exception as e:
        return False, "", str(e)

async def handle_system_service(name: str, action: str) -> Tuple[bool, str, str]:
    """Handle system service operations"""
    try:
        if action == "restart":
            cmd = ['sudo', 'systemctl', 'restart', f'{name}.service']
        elif action == "deploy":
            # For system services, restart is equivalent to deploy
            cmd = ['sudo', 'systemctl', 'restart', f'{name}.service']
        else:
            cmd = ['sudo', 'systemctl', 'restart', f'{name}.service']
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        success = result.returncode == 0
        return success, stdout.decode(), stderr.decode()
        
    except Exception as e:
        return False, "", str(e)

async def handle_pm2_process(name: str, action: str) -> Tuple[bool, str, str]:
    """Handle PM2 process operations"""
    try:
        if action == "restart":
            cmd = ['pm2', 'restart', name]
        elif action == "deploy":
            cmd = ['pm2', 'reload', name]  # Graceful reload for PM2
        else:
            cmd = ['pm2', 'restart', name]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        
        success = result.returncode == 0
        return success, stdout.decode(), stderr.decode()
        
    except Exception as e:
        return False, "", str(e)

async def get_deployment_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent deployment history"""
    try:
        db = get_database()
        if not db:
            return []
            
        cursor = db.deployment_logs.find().sort("timestamp", -1).limit(limit)
        logs = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for log in logs:
            log["_id"] = str(log["_id"])
            if "timestamp" in log:
                log["timestamp"] = log["timestamp"].isoformat()
            
        return logs
        
    except Exception as e:
        logger.error(f"Error getting deployment history: {e}")
        return []

async def get_application_status(app_name: str) -> Dict[str, Any]:
    """Get current status of an application"""
    app_name = sanitize_input(app_name, max_length=50)
    
    try:
        status_info = {
            "app_name": app_name,
            "checked_at": datetime.utcnow().isoformat(),
            "status": "unknown",
            "details": {}
        }
        
        # Check Docker container
        if await is_docker_container(app_name):
            result = await asyncio.create_subprocess_exec(
                'docker', 'ps', '--filter', f'name=^{app_name}$', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Ports}}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            if result.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                if len(lines) > 1:  # Skip header
                    status_info["status"] = "running" if "Up" in lines[1] else "stopped"
                    status_info["details"]["type"] = "docker_container"
                    status_info["details"]["info"] = lines[1]
        
        # Check system service
        elif await is_system_service(app_name):
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', f'{app_name}.service',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            status_info["status"] = stdout.decode().strip()
            status_info["details"]["type"] = "system_service"
        
        return status_info
        
    except Exception as e:
        logger.error(f"Error getting application status for {app_name}: {e}")
        return {
            "app_name": app_name,
            "status": "error",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def format_deployment_result_for_slack(result: Dict[str, Any]) -> str:
    """Format deployment result for Slack message"""
    try:
        app_name = result.get("app_name", "unknown")
        success = result.get("success", False)
        execution_time = result.get("execution_time", 0)
        strategy = result.get("strategy_used", "unknown")
        
        if success:
            emoji = "🚀"
            status = "SUCCESS"
            message = result.get("message", "Deployment completed")
        else:
            emoji = "❌"
            status = "FAILED"
            message = result.get("message", "Deployment failed")
        
        slack_message = f"""{emoji} **Deployment {status}**

**Application:** `{app_name}`
**Strategy:** {strategy.replace('_', ' ').title()}
**Execution Time:** {execution_time}s
**Status:** {message}

⏰ **Completed:** {result.get('timestamp', 'unknown')[:19].replace('T', ' ')} UTC"""

        # Add output or error details if available
        if success and result.get("output"):
            output = result["output"][:200]  # Limit length
            slack_message += f"\n\n**Output:**\n``````"
        elif not success and result.get("error"):
            error = result["error"][:200]  # Limit length
            slack_message += f"\n\n**Error:**\n``````"
        
        return slack_message
        
    except Exception as e:
        logger.error(f"Error formatting deployment result: {e}")
        return f"❌ **Error formatting deployment result:** {str(e)}"
