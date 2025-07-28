import hashlib
import hmac
import time
from typing import Optional
from app.core.config import settings

class SlackSecurity:
    """Handle Slack request verification and security"""
    
    @staticmethod
    def verify_slack_request(
        body: str, 
        timestamp: str, 
        signature: str
    ) -> bool:
        """Verify that requests are coming from Slack"""
        
        # Check timestamp to prevent replay attacks
        if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
            return False
        
        # Create signature
        sig_basestring = f"v0:{timestamp}:{body}"
        expected_signature = 'v0=' + hmac.new(
            settings.slack_signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(expected_signature, signature)
    
    @staticmethod
    def sanitize_command_input(text: str) -> str:
        """Sanitize user input for command execution"""
        # Remove potentially dangerous characters
        dangerous_chars = ['&', '|', ';', '$', '`', '>', '<', '"', "'"]
        sanitized = text
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()

class DeploymentSecurity:
    """Security utilities for deployment operations"""
    
    @staticmethod
    def validate_deployment_target(target: str) -> bool:
        """Validate deployment target environment"""
        allowed_targets = ['development', 'staging', 'production']
        return target.lower() in allowed_targets
    
    @staticmethod
    def require_approval_for_prod(environment: str, user_id: str) -> bool:
        """Check if production deployment requires approval"""
        if environment.lower() == 'production':
            # In a real implementation, check user permissions
            # For now, return True if user is authorized
            authorized_users = ['U1234567890']  # Replace with real user IDs
            return user_id in authorized_users
        return True
