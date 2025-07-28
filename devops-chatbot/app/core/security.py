import hashlib
import hmac
import time
import secrets
from fastapi import HTTPException, Request
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def verify_slack_signature(request: Request, body: bytes):
    """
    Verify that the request came from Slack using HMAC signature verification.
    This prevents unauthorized requests from malicious actors.
    """
    
    # Get required headers from Slack
    timestamp = request.headers.get('X-Slack-Request-Timestamp')
    signature = request.headers.get('X-Slack-Signature')
    
    if not timestamp or not signature:
        logger.error("Missing Slack headers in request")
        raise HTTPException(
            status_code=400, 
            detail="Missing required Slack headers (X-Slack-Request-Timestamp or X-Slack-Signature)"
        )
    
    # Validate timestamp format and check for replay attacks
    try:
        request_timestamp = int(timestamp)
        current_time = int(time.time())
        
        # Check if request is older than 5 minutes (Slack recommendation)
        if abs(current_time - request_timestamp) > settings.REQUEST_TIMEOUT:
            logger.error(f"Request timestamp too old: {request_timestamp}, current: {current_time}")
            raise HTTPException(
                status_code=400, 
                detail=f"Request timestamp too old. Max age: {settings.REQUEST_TIMEOUT} seconds"
            )
            
    except ValueError:
        logger.error(f"Invalid timestamp format: {timestamp}")
        raise HTTPException(status_code=400, detail="Invalid timestamp format")
    
    # Create the signature base string (Slack's standard format)
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    
    # Create the expected signature using HMAC-SHA256
    expected_signature = 'v0=' + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_signature, signature):
        logger.error("Slack signature verification failed")
        logger.debug(f"Expected: {expected_signature}")
        logger.debug(f"Received: {signature}")
        raise HTTPException(
            status_code=400, 
            detail="Invalid signature - request not from Slack"
        )
    
    logger.debug("Slack signature verified successfully")

def generate_api_key() -> str:
    """Generate a secure API key for internal services"""
    return secrets.token_urlsafe(32)

def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_urlsafe(16)

def hash_user_id(user_id: str) -> str:
    """Hash user ID for privacy protection in logs"""
    return hashlib.sha256(f"{user_id}{settings.SECRET_KEY}".encode()).hexdigest()[:16]

def validate_slack_payload(payload: dict) -> bool:
    """
    Validate basic Slack payload structure
    """
    required_fields = ['token', 'team_id']
    
    # Check for required fields in different payload types
    if payload.get('type') == 'url_verification':
        required_fields.append('challenge')
    elif 'event' in payload:
        required_fields.extend(['event_id', 'event_time'])
    
    for field in required_fields:
        if field not in payload:
            logger.error(f"Missing required field in Slack payload: {field}")
            return False
    
    return True

class SecurityMiddleware:
    """Security middleware for additional protection"""
    
    def __init__(self):
        self.rate_limit_storage = {}  # In production, use Redis
        self.blocked_ips = set()
    
    def check_rate_limit(self, client_ip: str, limit: int = 10, window: int = 60) -> bool:
        """
        Simple rate limiting (requests per minute)
        In production, use Redis with sliding window
        """
        current_time = time.time()
        
        if client_ip not in self.rate_limit_storage:
            self.rate_limit_storage[client_ip] = []
        
        # Clean old requests
        self.rate_limit_storage[client_ip] = [
            req_time for req_time in self.rate_limit_storage[client_ip]
            if current_time - req_time < window
        ]
        
        # Check limit
        if len(self.rate_limit_storage[client_ip]) >= limit:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return False
        
        # Add current request
        self.rate_limit_storage[client_ip].append(current_time)
        return True
    
    def is_ip_blocked(self, client_ip: str) -> bool:
        """Check if IP is blocked"""
        return client_ip in self.blocked_ips
    
    def block_ip(self, client_ip: str):
        """Block an IP address"""
        self.blocked_ips.add(client_ip)
        logger.warning(f"Blocked IP address: {client_ip}")

# Global security middleware instance
security_middleware = SecurityMiddleware()

def log_security_event(event_type: str, client_ip: str, details: dict = None):
    """Log security-related events"""
    log_data = {
        "event_type": event_type,
        "client_ip": client_ip,
        "timestamp": time.time(),
        "details": details or {}
    }
    
    logger.warning(f"Security Event: {log_data}")
    
    # In production, send to security monitoring system
    # send_to_security_system(log_data)

def sanitize_input(input_string: str, max_length: int = 1000) -> str:
    """Sanitize user input to prevent injection attacks"""
    if not isinstance(input_string, str):
        return ""
    
    # Remove potentially dangerous characters
    sanitized = input_string.strip()
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"Input truncated to {max_length} characters")
    
    # Remove common injection patterns
    dangerous_patterns = ['<script', 'javascript:', 'data:', 'vbscript:']
    for pattern in dangerous_patterns:
        if pattern.lower() in sanitized.lower():
            logger.warning(f"Potentially dangerous pattern detected: {pattern}")
            sanitized = sanitized.replace(pattern, '[FILTERED]')
    
    return sanitized
