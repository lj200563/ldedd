import os
from pathlib import Path


class ConfigManager:
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self):
        return {
            "MODELS": {
                "grok-3": "grok-3",
                "grok-4": "grok-4",
                "grok-4-fast": "grok-4-mini-thinking-tahoe"
            },
            "API": {
                "IS_TEMP_CONVERSATION": os.environ.get("IS_TEMP_CONVERSATION", "true").lower() == "true",
                "BASE_URL": "https://grok.com",
                "API_KEY": os.environ.get("API_KEY", "sk-123456"),
                "SIGNATURE_COOKIE": None,
                "RETRY_TIME": 1000,
                "PROXY": os.environ.get("PROXY") or None
            },
            "ADMIN": {},
            "SERVER": {
                "COOKIE": None,
                "PORT": int(os.environ.get("PORT", 5200))
            },
            "RETRY": {
                "RETRYSWITCH": False,
                "MAX_ATTEMPTS": 2
            },
        }
    
    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            value = value.get(k, default) if isinstance(value, dict) else default
        return value
    
    def set(self, key, value):
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
        
    def get_models(self):
        return self.get("MODELS", {})
    
    def is_reasoning_model(self, model):
        return model in ["grok-4", "grok-4-fast"]
    
    def is_valid_model(self, model):
        return model in self.get_models()


config_manager = ConfigManager()
