# test_config.py
try:
    from app.core.config import settings, validate_settings
    
    print("✅ Configuration import successful")
    print(f"Debug mode: {settings.DEBUG}")
    print(f"Port: {settings.PORT}")
    print(f"MongoDB URL: {settings.MONGODB_URL}")
    print(f"MongoDB Database: {settings.MONGODB_DATABASE}")
    
    # Check if Slack tokens are set
    if settings.SLACK_BOT_TOKEN and settings.SLACK_BOT_TOKEN != "your_slack_bot_token_here":
        print("✅ Slack Bot Token is configured")
    else:
        print("❌ Slack Bot Token not configured")
    
    if settings.SLACK_SIGNING_SECRET and settings.SLACK_SIGNING_SECRET != "your_slack_signing_secret_here":
        print("✅ Slack Signing Secret is configured")
    else:
        print("❌ Slack Signing Secret not configured")
    
    # Validate settings
    validate_settings()
    print("✅ All settings validation passed")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
