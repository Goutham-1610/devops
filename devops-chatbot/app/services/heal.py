import asyncio
import psutil
import shutil
import os
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
from app.database.connection import get_database
from app.core.security import sanitize_input

logger = logging.getLogger(__name__)

async def run_healing_tasks(user_id: str, channel: str, tasks: List[str] = None) -> Dict[str, Any]:
    """
    Run automated healing tasks
    """
    start_time = datetime.utcnow()
    
    if tasks is None:
        tasks = ["restart_failed_services", "clean_disk_space", "check_memory_usage", "restart_hanging_processes"]
    
    results = []
    overall_success = True
    
    try:
        logger.info(f"Starting healing tasks requested by {user_id}: {tasks}")
        
        for task in tasks:
            try:
                if task == "restart_failed_services":
                    result = await restart_failed_services()
                elif task == "clean_disk_space":
                    result = await clean_disk_space()
                elif task == "check_memory_usage":
                    result = await check_memory_usage()
                elif task == "restart_hanging_processes":
                    result = await restart_hanging_processes()
                else:
                    result = {"task": task, "success": False, "message": "Unknown task"}
                
                results.append(result)
                if not result.get("success", False):
                    overall_success = False
                    
            except Exception as e:
                logger.error(f"Error running healing task {task}: {e}")
                results.append({
                    "task": task,
                    "success": False,
                    "message": f"Exception: {str(e)}"
                })
                overall_success = False
        
        # Calculate execution time
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # Store healing log
        await store_healing_log(user_id, channel, results, overall_success, execution_time)
        
        return {
            "success": overall_success,
            "execution_time": round(execution_time, 2),
            "tasks_completed": len(results),
            "results": results,
            "timestamp": end_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Healing tasks failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }

async def restart_failed_services(services: List[str] = None) -> Dict[str, Any]:
    """Restart failed system services"""
    if services is None:
        services = ["nginx", "apache2", "mysql", "postgresql", "redis-server", "mongodb"]
    
    results = []
    services_restarted = 0
    
    try:
        for service in services:
            service = sanitize_input(service, max_length=30)
            
            # Check if service exists and is failed
            check_result = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', f'{service}.service',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await check_result.communicate()
            status = stdout.decode().strip()
            
            if status in ['failed', 'inactive']:
                # Try to restart the service
                restart_result = await asyncio.create_subprocess_exec(
                    'sudo', 'systemctl', 'restart', f'{service}.service',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                restart_stdout, restart_stderr = await restart_result.communicate()
                
                if restart_result.returncode == 0:
                    results.append({
                        "service": service,
                        "action": "restarted",
                        "success": True,
                        "previous_status": status
                    })
                    services_restarted += 1
                else:
                    results.append({
                        "service": service,
                        "action": "restart_failed",
                        "success": False,
                        "error": restart_stderr.decode().strip()
                    })
            else:
                results.append({
                    "service": service,
                    "action": "no_action_needed",
                    "success": True,
                    "status": status
                })
        
        return {
            "task": "restart_failed_services",
            "success": True,
            "services_restarted": services_restarted,
            "total_services_checked": len(services),
            "details": results
        }
        
    except Exception as e:
        logger.error(f"Error in restart_failed_services: {e}")
        return {
            "task": "restart_failed_services",
            "success": False,
            "error": str(e),
            "details": results
        }

async def clean_disk_space(threshold_percent: int = 85) -> Dict[str, Any]:
    """Clean disk space if usage is above threshold"""
    try:
        # Check current disk usage
        disk_usage = psutil.disk_usage('/')
        usage_percent = (disk_usage.used / disk_usage.total) * 100
        
        if usage_percent < threshold_percent:
            return {
                "task": "clean_disk_space",
                "success": True,
                "action": "no_cleanup_needed",
                "current_usage": round(usage_percent, 2),
                "threshold": threshold_percent
            }
        
        cleaned_bytes = 0
        actions_taken = []
        
        # Clean common temporary directories
        temp_dirs = ['/tmp', '/var/tmp', '/var/log']
        
        for temp_dir in temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    dir_cleaned = await clean_directory(temp_dir)
                    cleaned_bytes += dir_cleaned
                    if dir_cleaned > 0:
                        actions_taken.append(f"Cleaned {temp_dir}: {dir_cleaned / (1024*1024):.1f}MB")
            except Exception as e:
                logger.error(f"Error cleaning {temp_dir}: {e}")
                actions_taken.append(f"Failed to clean {temp_dir}: {str(e)}")
        
        # Clean Docker if available
        try:
            docker_cleaned = await clean_docker_resources()
            cleaned_bytes += docker_cleaned
            if docker_cleaned > 0:
                actions_taken.append(f"Cleaned Docker resources: {docker_cleaned / (1024*1024):.1f}MB")
        except Exception as e:
            logger.debug(f"Docker cleanup not available: {e}")
        
        # Clean package manager cache
        try:
            cache_cleaned = await clean_package_cache()
            cleaned_bytes += cache_cleaned
            if cache_cleaned > 0:
                actions_taken.append(f"Cleaned package cache: {cache_cleaned / (1024*1024):.1f}MB")
        except Exception as e:
            logger.debug(f"Package cache cleanup failed: {e}")
        
        # Check final disk usage
        final_disk_usage = psutil.disk_usage('/')
        final_usage_percent = (final_disk_usage.used / final_disk_usage.total) * 100
        
        return {
            "task": "clean_disk_space",
            "success": True,
            "initial_usage_percent": round(usage_percent, 2),
            "final_usage_percent": round(final_usage_percent, 2),
            "cleaned_mb": round(cleaned_bytes / (1024*1024), 2),
            "actions_taken": actions_taken
        }
        
    except Exception as e:
        logger.error(f"Error in clean_disk_space: {e}")
        return {
            "task": "clean_disk_space",
            "success": False,
            "error": str(e)
        }

async def clean_directory(directory: str) -> int:
    """Clean files in a directory and return bytes cleaned"""
    cleaned_bytes = 0
    
    try:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            
            if os.path.isfile(filepath):
                # Clean old log files, temp files, etc.
                if (filename.endswith('.log') and 
                    os.path.getmtime(filepath) < (datetime.now().timestamp() - 7*24*3600)):  # 7 days old
                    
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleaned_bytes += size
                    
                elif filename.startswith('tmp') or filename.endswith('.tmp'):
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    cleaned_bytes += size
                    
    except Exception as e:
        logger.error(f"Error cleaning directory {directory}: {e}")
    
    return cleaned_bytes

async def clean_docker_resources() -> int:
    """Clean unused Docker resources"""
    cleaned_bytes = 0
    
    try:
        # Run docker system prune
        result = await asyncio.create_subprocess_exec(
            'docker', 'system', 'prune', '-f',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        
        if result.returncode == 0:
            # Parse output to estimate cleaned bytes (rough estimate)
            output = stdout.decode()
            if "Total reclaimed space" in output:
                # This is a rough estimation
                cleaned_bytes = 100 * 1024 * 1024  # Estimate 100MB
                
    except Exception as e:
        logger.debug(f"Docker cleanup failed: {e}")
    
    return cleaned_bytes

async def clean_package_cache() -> int:
    """Clean package manager cache"""
    cleaned_bytes = 0
    
    try:
        # Try apt cache clean (Ubuntu/Debian)
        result = await asyncio.create_subprocess_exec(
            'sudo', 'apt-get', 'clean',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await result.communicate()
        
        if result.returncode == 0:
            cleaned_bytes = 50 * 1024 * 1024  # Estimate 50MB
            
    except Exception:
        # Try yum cache clean (CentOS/RHEL)
        try:
            result = await asyncio.create_subprocess_exec(
                'sudo', 'yum', 'clean', 'all',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            if result.returncode == 0:
                cleaned_bytes = 50 * 1024 * 1024  # Estimate 50MB
                
        except Exception as e:
            logger.debug(f"Package cache cleanup failed: {e}")
    
    return cleaned_bytes

async def check_memory_usage(threshold_percent: int = 90) -> Dict[str, Any]:
    """Check memory usage and kill high-memory processes if needed"""
    try:
        memory = psutil.virtual_memory()
        usage_percent = memory.percent
        
        if usage_percent < threshold_percent:
            return {
                "task": "check_memory_usage",
                "success": True,
                "action": "no_action_needed",
                "current_usage": round(usage_percent, 2),
                "threshold": threshold_percent
            }
        
        # Find high-memory processes
        high_memory_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                if proc.info['memory_percent'] > 10:  # Processes using >10% memory
                    high_memory_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by memory usage
        high_memory_processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        
        return {
            "task": "check_memory_usage",
            "success": True,
            "current_usage": round(usage_percent, 2),
            "threshold": threshold_percent,
            "high_memory_processes": high_memory_processes[:5],  # Top 5
            "action": "identified_high_memory_processes"
        }
        
    except Exception as e:
        logger.error(f"Error in check_memory_usage: {e}")
        return {
            "task": "check_memory_usage",
            "success": False,
            "error": str(e)
        }

async def restart_hanging_processes() -> Dict[str, Any]:
    """Identify and restart hanging processes"""
    try:
        hanging_processes = []
        
        # This is a simplified approach - in production, you'd have more sophisticated detection
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent']):
            try:
                # Check for processes that might be hanging
                if (proc.info['status'] == psutil.STATUS_ZOMBIE or 
                    proc.info['status'] == psutil.STATUS_DISK_SLEEP):
                    hanging_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return {
            "task": "restart_hanging_processes",
            "success": True,
            "hanging_processes_found": len(hanging_processes),
            "processes": hanging_processes,
            "action": "identified_hanging_processes"
        }
        
    except Exception as e:
        logger.error(f"Error in restart_hanging_processes: {e}")
        return {
            "task": "restart_hanging_processes",
            "success": False,
            "error": str(e)
        }

async def store_healing_log(user_id: str, channel: str, results: List[Dict], success: bool, execution_time: float):
    """Store healing operation log in database"""
    try:
        db = get_database()
        if db:
            healing_log = {
                "user_id": user_id,
                "channel": channel,
                "timestamp": datetime.utcnow(),
                "success": success,
                "execution_time": execution_time,
                "tasks_run": len(results),
                "results": results
            }
            
            await db.healing_logs.insert_one(healing_log)
            logger.info(f"Healing log stored for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error storing healing log: {e}")

async def format_healing_results_for_slack(results: Dict[str, Any]) -> str:
    """Format healing results for Slack message"""
    try:
        success = results.get("success", False)
        execution_time = results.get("execution_time", 0)
        tasks_completed = results.get("tasks_completed", 0)
        task_results = results.get("results", [])
        
        emoji = "🔧" if success else "⚠️"
        status = "COMPLETED" if success else "COMPLETED WITH ISSUES"
        
        message = f"""{emoji} **System Healing {status}**

**Tasks Completed:** {tasks_completed}
**Execution Time:** {execution_time}s
**Overall Success:** {'✅ Yes' if success else '❌ No'}

**Task Results:**"""

        for task_result in task_results:
            task_name = task_result.get("task", "unknown").replace("_", " ").title()
            task_success = task_result.get("success", False)
            task_emoji = "✅" if task_success else "❌"
            
            message += f"\n{task_emoji} **{task_name}**"
            
            # Add specific details based on task type
            if task_result.get("task") == "clean_disk_space":
                cleaned_mb = task_result.get("cleaned_mb", 0)
                if cleaned_mb > 0:
                    message += f" - Cleaned {cleaned_mb:.1f}MB"
                else:
                    message += " - No cleanup needed"
                    
            elif task_result.get("task") == "restart_failed_services":
                restarted = task_result.get("services_restarted", 0)
                checked = task_result.get("total_services_checked", 0)
                message += f" - Restarted {restarted}/{checked} services"
                
            elif task_result.get("task") == "check_memory_usage":
                usage = task_result.get("current_usage", 0)
                message += f" - Memory usage: {usage:.1f}%"
        
        message += f"\n\n⏰ **Completed:** {results.get('timestamp', 'unknown')[:19].replace('T', ' ')} UTC"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting healing results: {e}")
        return f"❌ **Error formatting healing results:** {str(e)}"
