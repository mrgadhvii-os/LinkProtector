import logging
from datetime import datetime
import json
import os
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
import asyncio
import functools
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('ChannelBot')

# Remove circular import
# from bot import test_command

class CommandLogger:
    def __init__(self):
        self.log_file = "command_logs.json"
        self.logs: Dict[str, list] = self._load_logs()

    def _load_logs(self) -> Dict[str, list]:
        """Load existing logs from file"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading logs: {e}")
        return {"commands": [], "callbacks": []}

    def _save_logs(self):
        """Save logs to file"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.logs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving logs: {e}")

    def log_command(self, user_id: int, username: Optional[str], command: str, args: Optional[str] = None):
        """Log command usage"""
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": user_id,
            "username": username,
            "command": command,
            "args": args
        }
        self.logs["commands"].append(log_entry)
        self._save_logs()
        logger.info(f"Command used: {command} by user {user_id} ({username})")

    def log_callback(self, user_id: int, username: Optional[str], callback_data: str):
        """Log callback query usage"""
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": user_id,
            "username": username,
            "callback_data": callback_data
        }
        self.logs["callbacks"].append(log_entry)
        self._save_logs()
        logger.info(f"Callback used: {callback_data} by user {user_id} ({username})")

# Initialize command logger
cmd_logger = CommandLogger()

def log_command(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        try:
            # Get user info safely
            user_id = message.from_user.id if message.from_user else "Unknown"
            username = message.from_user.username if message.from_user else "Unknown"
            command = message.command[0] if message.command else "unknown"
            
            # Log command usage
            logger.info(f"Command used: {command} by user {user_id} (@{username})")
            
            # Log to JSON file
            try:
                with open('command_logs.json', 'r') as f:
                    logs = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logs = {"commands": []}
            
            # Add new log entry
            logs["commands"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "command": command,
                "user_id": str(user_id),
                "username": username
            })
            
            # Save updated logs
            with open('command_logs.json', 'w') as f:
                json.dump(logs, f, indent=4)
            
            # Execute the command
            return await func(client, message, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in command {getattr(message, 'command', ['unknown'])[0]}: {str(e)}")
            # Don't raise the error, let the command handle it
            return await func(client, message, *args, **kwargs)
    
    return wrapper

def log_callback(func):
    @wraps(func)
    async def wrapper(client, callback_query, *args, **kwargs):
        try:
            # Get user info safely
            user_id = callback_query.from_user.id if callback_query.from_user else "Unknown"
            username = callback_query.from_user.username if callback_query.from_user else "Unknown"
            data = callback_query.data if callback_query.data else "unknown"
            
            # Log callback usage
            logger.info(f"Callback used: {data} by user {user_id} (@{username})")
            
            # Log to JSON file
            try:
                with open('callback_logs.json', 'r') as f:
                    logs = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logs = {"callbacks": []}
            
            # Add new log entry
            logs["callbacks"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "callback_data": data,
                "user_id": str(user_id),
                "username": username
            })
            
            # Save updated logs
            with open('callback_logs.json', 'w') as f:
                json.dump(logs, f, indent=4)
            
            # Execute the callback
            return await func(client, callback_query, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in callback {getattr(callback_query, 'data', 'unknown')}: {str(e)}")
            # Don't raise the error, let the callback handle it
            return await func(client, callback_query, *args, **kwargs)
    
    return wrapper

def get_command_stats() -> Dict[str, Any]:
    """
    Get command usage statistics
    Returns a dictionary with command usage data
    """
    stats = {
        "total_commands": len(cmd_logger.logs["commands"]),
        "total_callbacks": len(cmd_logger.logs["callbacks"]),
        "unique_users": set(),
        "command_frequency": {},
        "callback_frequency": {}
    }
    
    # Process commands
    for cmd in cmd_logger.logs["commands"]:
        stats["unique_users"].add(cmd["user_id"])
        command = cmd["command"]
        stats["command_frequency"][command] = stats["command_frequency"].get(command, 0) + 1
    
    # Process callbacks
    for cb in cmd_logger.logs["callbacks"]:
        stats["unique_users"].add(cb["user_id"])
        callback = cb["callback_data"]
        stats["callback_frequency"][callback] = stats["callback_frequency"].get(callback, 0) + 1
    
    # Convert set to length for JSON serialization
    stats["unique_users"] = len(stats["unique_users"])
    
    return stats

async def log_periodic_stats():
    """
    Periodically log command usage statistics
    Runs every hour
    """
    while True:
        try:
            stats = get_command_stats()
            logger.info("Command Usage Statistics:")
            logger.info(f"Total Commands: {stats['total_commands']}")
            logger.info(f"Total Callbacks: {stats['total_callbacks']}")
            logger.info(f"Unique Users: {stats['unique_users']}")
            logger.info(f"Command Frequency: {stats['command_frequency']}")
            logger.info(f"Callback Frequency: {stats['callback_frequency']}")
        except Exception as e:
            logger.error(f"Error logging periodic stats: {e}")
        
        await asyncio.sleep(3600)  # Sleep for 1 hour

def setup_command_handlers(app: Client):
    """
    Set up command handlers with logging
    This should be called when initializing the bot
    """
    # Start periodic stats logging
    asyncio.create_task(log_periodic_stats())
    logger.info("Command logging system initialized") 