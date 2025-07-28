import psutil
import subprocess
import asyncio
import logging
import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
from app.database.connection import get_database
from app.database.models import SystemMetrics
from app.core.security import sanitize_input

logger = logging.getLogger(__name__)

async def get_system_stats() -> Dict[str, Any]:
    """Get comprehensive system statistics"""
    try:
        # CPU Information
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        # Memory Information
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        # Disk Information
        disk = psutil.disk_usage('/')
        
        # Network Information
        network = psutil.net_io_counters()
        
        # Process Information
        active_processes = len(psutil.pids())
        
        # System Load (Unix-like systems)
        try:
            load_avg = psutil.getloadavg()
        except (AttributeError, OSError):
            load_avg = [0.0, 0.0, 0.0]  # Windows fallback
        
        # Boot time
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": {
                "percent": round(cpu_percent, 2),
                "count": cpu_count,
                "frequency_mhz": round(cpu_freq.current, 2) if cpu_freq else 0
            },
            "memory": {
                "percent": round(memory.percent, 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2)
            },
            "swap": {
                "percent": round(swap.percent, 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "total_gb": round(swap.total / (1024**3), 2)
            },
            "disk": {
                "percent": round(disk.percent, 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2)
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            },
            "system": {
                "active_processes": active_processes,
                "load_average": [round(l, 2) for l in load_avg],
                "uptime_hours": round(uptime.total_seconds() / 3600, 2),
                "boot_time": boot_time.isoformat()
            }
        }
        
        # Store metrics in database
        await store_system_metrics(stats)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

async def store_system_metrics(stats: Dict[str, Any]):
    """Store system metrics in MongoDB"""
    try:
        db = get_database()
        if db is not None:
            metrics = SystemMetrics(
                cpu_percent=stats["cpu"]["percent"],
                memory_percent=stats["memory"]["percent"],
                disk_percent=stats["disk"]["percent"],
                active_processes=stats["system"]["active_processes"],
                system_load=stats["system"]["load_average"]
            )
            
            await db.system_metrics.insert_one(metrics.dict(by_alias=True))
            logger.debug("System metrics stored successfully")
            
            # Clean old metrics (keep only last 30 days)
            await cleanup_old_metrics()
            
    except Exception as e:
        logger.error(f"Error storing system metrics: {e}")

async def cleanup_old_metrics():
    """Remove metrics older than retention period"""
    try:
        db = get_database()
        if db is not None:
            # Calculate cutoff date
            from app.core.config import settings
            cutoff_date = datetime.utcnow() - timedelta(days=settings.METRICS_RETENTION_DAYS)
            
            # Delete old metrics
            result = await db.system_metrics.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} old metrics")
                
    except Exception as e:
        logger.error(f"Error cleaning up old metrics: {e}")

async def check_service_status(service_name: str) -> Dict[str, Any]:
    """Check if a system service is running"""
    # Sanitize service name to prevent command injection
    service_name = sanitize_input(service_name, max_length=50)
    
    try:
        if psutil.WINDOWS:
            # Windows service check
            result = await asyncio.create_subprocess_exec(
                'sc', 'query', service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            # Linux/macOS service check
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            status = stdout.decode().strip()
            is_running = "active" in status.lower() or "running" in status.lower()
        else:
            status = stderr.decode().strip()
            is_running = False
            
        return {
            "service": service_name,
            "status": status,
            "running": is_running,
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking service {service_name}: {e}")
        return {
            "service": service_name,
            "status": f"error: {str(e)}",
            "running": False,
            "checked_at": datetime.utcnow().isoformat()
        }

async def get_docker_stats() -> Dict[str, Any]:
    """Get Docker container statistics"""
    try:
        # Check if Docker is available
        result = await asyncio.create_subprocess_exec(
            'docker', 'ps', '--format', 'json',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode != 0:
            return {
                "error": "Docker not available or not running",
                "checked_at": datetime.utcnow().isoformat()
            }
        
        containers = []
        for line in stdout.decode().strip().split('\n'):
            if line:
                try:
                    container = json.loads(line)
                    containers.append({
                        "name": container.get("Names", "unknown"),
                        "image": container.get("Image", "unknown"),
                        "status": container.get("Status", "unknown"),
                        "created": container.get("CreatedAt", "unknown"),
                        "ports": container.get("Ports", "")
                    })
                except json.JSONDecodeError:
                    continue
        
        return {
            "containers": containers,
            "total_containers": len(containers),
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting Docker stats: {e}")
        return {
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def format_system_stats_for_slack(stats: Dict[str, Any]) -> str:
    """Format system statistics for Slack message"""
    if "error" in stats:
        return f"❌ **Error getting system stats:** {stats['error']}"
    
    try:
        cpu = stats["cpu"]
        memory = stats["memory"]
        disk = stats["disk"]
        system = stats["system"]
        
        # Determine status emojis
        cpu_emoji = "🔴" if cpu["percent"] > 80 else "🟡" if cpu["percent"] > 60 else "🟢"
        mem_emoji = "🔴" if memory["percent"] > 80 else "🟡" if memory["percent"] > 60 else "🟢"
        disk_emoji = "🔴" if disk["percent"] > 80 else "🟡" if disk["percent"] > 60 else "🟢"
        
        message = f"""🖥️ **System Status Report**

{cpu_emoji} **CPU Usage:** {cpu['percent']}% ({cpu['count']} cores)
{mem_emoji} **Memory:** {memory['percent']}% ({memory['used_gb']:.1f}GB / {memory['total_gb']:.1f}GB)
{disk_emoji} **Disk:** {disk['percent']}% ({disk['used_gb']:.1f}GB / {disk['total_gb']:.1f}GB)

📊 **System Info:**
• **Processes:** {system['active_processes']} running
• **Load Average:** {', '.join(map(str, system['load_average']))}
• **Uptime:** {system['uptime_hours']:.1f} hours

⏰ **Checked:** {stats['timestamp'][:19].replace('T', ' ')} UTC"""

        return message
        
    except Exception as e:
        logger.error(f"Error formatting stats for Slack: {e}")
        return f"❌ **Error formatting system stats:** {str(e)}"
