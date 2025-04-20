import os
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
    WebAppInfo
)
from pyrogram.enums import ParseMode
from pyrogram.handlers import MessageHandler
from config import API_ID, API_HASH, BOT_TOKEN, MONGO_URL
import motor.motor_asyncio
import aiohttp
import json
import re
from urllib.parse import quote, quote_plus, urlparse
import base64
import time
import random
import string
import asyncio
from datetime import datetime, timedelta
from flask import Flask
import threading
from waitress import serve
from helper import log_command, log_callback, setup_command_handlers
from pyrogram.errors import FloodWait
from ip import IPChecker
import socket
import secrets
import hashlib
import logging
import psutil
import platform

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB Setup
try:
    # Parse MongoDB URL and encode username/password
    parsed_url = urlparse(MONGO_URL)
    if parsed_url.username and parsed_url.password:
        encoded_username = quote_plus(parsed_url.username)
        encoded_password = quote_plus(parsed_url.password)
        encoded_url = MONGO_URL.replace(
            f"{parsed_url.username}:{parsed_url.password}",
            f"{encoded_username}:{encoded_password}"
        )
    else:
        encoded_url = MONGO_URL

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(encoded_url)
    db = mongo_client.linkprotector  # database name
    
    # Define collections
    links_collection = db.links  # for protected links
    users_collection = db.users  # for user tracking
    verified_collection = db.verified  # for verified users
    banned_collection = db.banned  # for banned users
    stats_collection = db.stats  # for bot statistics
    
    # Create indexes
    async def create_indexes():
        await links_collection.create_index("token", unique=True)
        await users_collection.create_index("user_id", unique=True)
        await verified_collection.create_index("user_id", unique=True)
        await banned_collection.create_index("user_id", unique=True)
    
    # Run index creation
    loop = asyncio.get_event_loop()
    loop.run_until_complete(create_indexes())
    
    logger.info("MongoDB connected successfully!")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise SystemExit("Could not connect to MongoDB. Exiting...")

# Create Flask app
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Hello from MrGadhvii'

@flask_app.route('/health')
def health():
    """Detailed health check endpoint"""
    try:
        # System info
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Bot uptime
        uptime = datetime.now() - START_TIME
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        
        # Network info
        net_io = psutil.net_io_counters()
        bytes_sent = net_io.bytes_sent
        bytes_recv = net_io.bytes_recv
        
        # Bot stats
        total_users = len(USERS)
        total_banned = len(ip_checker.banned_users)
        
        health_data = {
            "status": "operational",
            "owner": "MrGadhvii",
            "bot_info": {
                "username": BOT_USERNAME,
                "uptime": uptime_str,
                "start_time": START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
                "total_users": total_users,
                "banned_users": total_banned,
                "ping_count": PING_COUNT
            },
            "system_info": {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "cpu": {
                    "usage_percent": round(cpu_percent, 2),
                    "cores": psutil.cpu_count()
                },
                "memory": {
                    "total": f"{memory.total / (1024**3):.2f} GB",
                    "used": f"{memory.used / (1024**3):.2f} GB",
                    "free": f"{memory.free / (1024**3):.2f} GB",
                    "percent": memory.percent
                },
                "disk": {
                    "total": f"{disk.total / (1024**3):.2f} GB",
                    "used": f"{disk.used / (1024**3):.2f} GB",
                    "free": f"{disk.free / (1024**3):.2f} GB",
                    "percent": disk.percent
                },
                "network": {
                    "bytes_sent": f"{bytes_sent / (1024**2):.2f} MB",
                    "bytes_received": f"{bytes_recv / (1024**2):.2f} MB"
                }
            },
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Format response with indentation for better readability
        return flask_app.response_class(
            response=json.dumps(health_data, indent=2),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        error_response = {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return flask_app.response_class(
            response=json.dumps(error_response, indent=2),
            status=500,
            mimetype='application/json'
        )

def run_flask():
    """Run Flask server"""
    try:
        # Force port 8080 for Heroku
        port = 8080
        logger.info(f"Starting Flask server on port {port}")
        logger.info("Health endpoint available at /health")
        serve(flask_app, host='0.0.0.0', port=port, threads=4)
    except Exception as e:
        logger.error(f"Flask server error: {e}", exc_info=True)
        # Try alternate port if 8080 fails
        try:
            port = int(os.environ.get("PORT", 8080))
            logger.info(f"Retrying Flask server on port {port}")
            serve(flask_app, host='0.0.0.0', port=port, threads=4)
        except Exception as e:
            logger.error(f"Flask server retry failed: {e}", exc_info=True)

# Initialize bot
app = Client(
    "LinkProtectorXBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Store bot username and start time
BOT_USERNAME = ""
START_TIME = datetime.now()
PING_COUNT = 0

# Store channel data and their shortened URLs
channels = {
    "channel1": {
        "name": "🎮 Gaming Zone",
        "link": "https://t.me/+abcdefghijk123456",  # Replace with your invite link
        "description": "🎯 Best gaming content and updates!\n"
                      "• Daily gaming news\n"
                      "• Game reviews\n"
                      "• Gaming tips & tricks",
        "short_url": None  # Will store shortened URL
    },
    "channel2": {
        "name": "📱 Tech Hub",
        "link": "https://t.me/+mnopqrstuvw789012",  # Replace with your invite link
        "description": "🚀 Latest technology news and reviews\n"
                      "• Tech updates daily\n"
                      "• Product reviews\n"
                      "• Tech tips & tutorials",
        "short_url": None  # Will store shortened URL
    },
    # Add more channels as needed
}

# Store user states
user_states = {}

# Add user tracking
USERS_FILE = 'users.json'

def load_users():
    """Load users from JSON file."""
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('users', []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_users(users):
    """Save users to JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump({'users': list(users)}, f)

# Initialize users set
USERS = load_users()

# Initialize IP checker
ip_checker = IPChecker()

# Add this with other global variables
TOKENS_FILE = 'verification_tokens.json'

def generate_verification_token(user_id: int) -> str:
    """Generate a secure verification token for user"""
    try:
        # Load or create tokens file
        try:
            with open(TOKENS_FILE, 'r') as f:
                tokens = json.load(f)
        except:
            tokens = {}
        
        # Generate token
        random_bytes = secrets.token_bytes(16)
        current_time = int(time.time())
        token_data = f"{user_id}:{current_time}:{random_bytes.hex()}"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:32]
        
        # Store token
        tokens[token] = {
            "user_id": user_id,
            "expires": current_time + 600  # 10 minutes
        }
        
        # Save tokens
        with open(TOKENS_FILE, 'w') as f:
            json.dump(tokens, f)
        
        return token
    except Exception as e:
        print(f"Token generation error: {e}")
        return None

def verify_token(token: str, user_id: int) -> bool:
    """Verify a token is valid for user"""
    try:
        # Load tokens
        with open(TOKENS_FILE, 'r') as f:
            tokens = json.load(f)
        
        if token not in tokens:
            return False
        
        token_data = tokens[token]
        current_time = int(time.time())
        
        # Check expiry and user
        if current_time > token_data["expires"] or token_data["user_id"] != user_id:
            del tokens[token]
            with open(TOKENS_FILE, 'w') as f:
                json.dump(tokens, f)
            return False
        
        # Valid token - remove it
        del tokens[token]
        with open(TOKENS_FILE, 'w') as f:
            json.dump(tokens, f)
        return True
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return False

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Handle /start command"""
    try:
        user_id = message.from_user.id
        
        # Add user to database
        try:
            await users_collection.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'user_id': user_id,
                        'username': message.from_user.username,
                        'joined_at': datetime.now()
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error adding user to database: {e}")
        
        # If user is banned, reject them
        if ip_checker.is_user_banned(user_id):
            await message.reply(
                "🚫 You are banned from using this bot.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Check if this is a verification callback
        if len(message.command) > 1:
            token = message.command[1]
            
            # Handle GDV links (v2 tokens)
            if token.startswith('v2-'):
                try:
                    link_data = get_link_data(token)
                    if link_data and link_data.get('link'):
                        link = link_data['link']
                        # Check if it's a Telegram link
                        if 't.me/' in link.lower() or 'telegram.me/' in link.lower():
                            # For Telegram links, use redirect
                            webapp_url = f"https://adorable-sfogliatella-26d564.netlify.app/redirect.html?url={quote(link)}"
                        else:
                            # For non-Telegram links, open directly
                            webapp_url = link
                        
                        # Create keyboard with WebApp button
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(
                                "🌟 𝙊𝙥𝙚𝙣 𝙇𝙞𝙣𝙠",
                                web_app=WebAppInfo(url=webapp_url)
                            )]
                        ])
                        
                        await message.reply(
                            "🔐 **Protected Link**\n\n"
                            "• Click the button below to proceed\n"
                            "__Click the button to continue:__",
                            reply_markup=keyboard,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        return
                    else:
                        await message.reply(
                            "❌ This link has expired or is invalid.\n"
                            "Please request a new link.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        return
                except Exception as e:
                    logger.error(f"Error handling GDV link: {e}")
                    return
            
            # Handle verification tokens
            if verify_token(token, user_id):
                # Add user to verified list
                ip_checker.add_verified_user(user_id)
                
                await message.reply(
                    "✅ **Verified Successfully**\n"
                    "__Owner: @MrGadhvii__",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Show welcome message
                await send_welcome_message(client, message)
                return
            else:
                await message.reply(
                    "❌ Invalid or expired verification.\n"
                    "Please try verifying again.",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # If user is already verified, proceed normally
        if ip_checker.is_verified(user_id):
            await send_welcome_message(client, message)
            return
        
        # For new users only: Show verification button
        verification_token = generate_verification_token(user_id)
        if not verification_token:
            await message.reply(
                "⚠️ Error generating verification. Please try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Show verification WebApp button
        verify_url = f"https://adorable-sfogliatella-26d564.netlify.app/verify.html?user_id={user_id}&token={verification_token}&bot={BOT_USERNAME}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔒 Verify Your Location",
                web_app=WebAppInfo(url=verify_url)
            )]
        ])
        
        await message.reply(
            "🔒 **Human Verification Required**\n\n"
            "Please click the button below to verify.\n\n"
            "ℹ️ __You will be redirected to a secure verification page.__",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Start command error: {e}")
        await message.reply(
            "⚠️ Something went wrong. Please try again.",
            parse_mode=ParseMode.MARKDOWN
        )

# Add this function before the command handlers
async def get_user_ip(message: Message) -> str:
    """Get user's IP address from forwarded header or default to a fallback method"""
    try:
        # Try to get from forwarded header
        if message.forward_from:
            return message.forward_from.forward_sender_name or "0.0.0.0"
        # Fallback to a default IP check service
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.ipify.org?format=json') as response:
                data = await response.json()
                return data.get('ip', '0.0.0.0')
    except:
        return "0.0.0.0"

# Add this after your existing get_user_ip function
@app.on_message(filters.command("myip"))
@log_command
async def myip_command(client, message: Message):
    """Handle /myip command - Show user's IP info"""
    try:
        # Get user's IP
        user_ip = await get_user_ip(message)
        
        # Get detailed IP info
        ip_info = await ip_checker.get_ip_info(user_ip)
        
        # Create IP info message
        ip_text = (
            "🌐 **Your IP Information**\n\n"
            f"🔍 **IP:** `{ip_info['ip']}`\n"
            f"🌍 **Country:** `{ip_info['country']}`\n"
            f"🏘️ **Region:** `{ip_info['region']}`\n"
            f"🏙️ **City:** `{ip_info['city']}`\n"
            f"🏢 **ISP:** `{ip_info['isp']}`\n"
            f"⏰ **Timezone:** `{ip_info['timezone']}`\n\n"
        )
        
        # Check if user is allowed (from India)
        is_allowed, _ = await ip_checker.verify_user(message.from_user.id, user_ip)
        if is_allowed:
            ip_text += "✅ **Status:** You are allowed to use this bot!"
        else:
            ip_text += "🚫 **Status:** You are not allowed to use this bot."
        
        await message.reply(
            ip_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        print(f"MyIP command error: {str(e)}")
        await message.reply("⚠️ Error getting IP information.")

@app.on_message(filters.command("test"))
@log_command
async def test_command(client, message: Message):
    """Simple test command to ban yourself"""
    try:
        await message.reply("🔄 Starting test ban...")
        
        # Add to ban list
        ip_checker.banned_users.add(message.from_user.id)
        ip_checker._save_banned_users()
        
        await message.reply(
            "✅ Test successful!\n\n"
            "You are now banned. Try /start to see what happens.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Test error: {str(e)}")
        await message.reply("❌ Test failed!")

async def send_welcome_message(client, message):
    """Send welcome message after verification"""
    try:
        welcome_text = (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎊 Welcome **{message.from_user.first_name}**!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 I am a **Channel Link Protection Bot**\n"
            f"__ɪ ᴄᴀɴ ʜᴇʟᴘ ʏᴏᴜ ᴘʀᴏᴛᴇᴄᴛ ʏᴏᴜʀ ᴄʜᴀɴɴᴇʟ ʟɪɴᴋꜱ ᴡɪᴛʜ ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴄᴜʀɪᴛʏ.__\n\n"
            f"**🛠 Available Commands:**\n"
            f"• /start - Start the bot\n"
            f"• /gdv - Generate protected link\n\n"
            f"**🌟 Key Features:**\n"
            f"• 🔒 Advanced Link Protection\n"
            f"• 🚀 Instant Link Generation\n"

        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👨‍💻 𝘿𝙚𝙫𝙚𝙡𝙤𝙥𝙚𝙧", url="https://t.me/MrGadhvii"),
                InlineKeyboardButton("🔔 𝙐𝙥𝙙𝙖𝙩𝙚𝙨", url="https://t.me/OneNetworkX")
            ]
        ])
        
        await message.reply(
            welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Welcome message error: {e}")

@app.on_callback_query(filters.regex("^verify_success_(.+)$"))
async def verify_success(client, callback_query: CallbackQuery):
    """Handle successful verification from WebApp"""
    try:
        user_id = int(callback_query.data.split('_')[2])
        
        # Add user to verified list
        ip_checker.add_verified_user(user_id)
        
        # Update message and show welcome
        await callback_query.message.edit_text(
            "✅ **Verified Successfully**\n"
            "__Owner: @MrGadhvii__"
        )
        
        # Send welcome message
        await send_welcome_message(client, callback_query.message)
        
    except Exception as e:
        logger.error(f"Verification success error: {str(e)}")
        await callback_query.message.edit_text(
            "⚠️ Verification process failed. Please try again later."
        )

@app.on_callback_query(filters.regex("^verify_fail_(.+)$"))
async def verify_fail(client, callback_query: CallbackQuery):
    """Handle failed verification from WebApp"""
    try:
        user_id = int(callback_query.data.split('_')[2])
        
        # Ban user
        ip_checker.banned_users.add(user_id)
        ip_checker._save_banned_users()
        
        await callback_query.message.edit_text(
            "❌ Verification Failed!\n\n"
            "This bot is only available for users from India.\n"
            "If you think this is a mistake, contact @MrGadhvii"
        )
        
    except Exception as e:
        logger.error(f"Verification fail error: {str(e)}")
        await callback_query.message.edit_text(
            "⚠️ Verification failed. Please contact support."
        )

# Add these functions after the imports and before the bot initialization
def generate_token():
    """Generate a unique token for the link."""
    try:
        timestamp = int(time.time())
        # Token valid for 1 year
        expiry = timestamp + (365 * 24 * 60 * 60)
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        token_data = f"{timestamp}-{expiry}-{random_str}"
        # Add v2 prefix to distinguish from verification tokens
        return f"v2-{base64.urlsafe_b64encode(token_data.encode()).decode()}"
    except Exception as e:
        logger.error(f"Token generation error: {e}")
        return None

def save_link(token: str, link: str):
    """Save link data to JSON file."""
    try:
        with open('links.json', 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"links": {}}
    
    # Parse token to get timestamp and expiry
    try:
        # Remove v2 prefix before decoding
        pure_token = token.replace('v2-', '', 1)
        token_data = base64.urlsafe_b64decode(pure_token.encode()).decode()
        timestamp, expiry, _ = token_data.split('-')
        expiry = int(expiry)
    except:
        timestamp = int(time.time())
        expiry = timestamp + (365 * 24 * 60 * 60)  # 1 year default
    
    data["links"][token] = {
        "link": link,
        "created_at": int(timestamp),
        "expires_at": expiry
    }
    
    with open('links.json', 'w') as f:
        json.dump(data, f, indent=4)

def get_link_data(token: str):
    """Get link data from JSON file."""
    try:
        with open('links.json', 'r') as f:
            data = json.load(f)
            link_data = data["links"].get(token)
            
            if not link_data:
                return None
            
            # Check if link has expired
            current_time = int(time.time())
            if current_time > link_data.get("expires_at", 0):
                # Remove expired link
                del data["links"][token]
                with open('links.json', 'w') as f:
                    json.dump(data, f, indent=4)
                return None
                
            return link_data
    except (FileNotFoundError, json.JSONDecodeError):
        return None

# Add this function to handle link generation
async def generate_protected_link(telegram_link: str) -> str:
    """Generate a protected link with token."""
    token = generate_token()
    save_link(token, telegram_link)
    return token

@app.on_message(filters.command("gdv"))
@log_command
async def gdv_command(client, message: Message):
    """Handle /gdv command"""
    try:
        user_id = message.from_user.id
        
        # Check if user is banned using ip_checker
        if ip_checker.is_user_banned(user_id):
            await message.reply(
                "🚫 You are banned from using this bot.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Check if user is verified using ip_checker
        if not ip_checker.is_verified(user_id):
            await message.reply(
                "❌ Please verify your location first.\n"
                "Use /start to begin verification.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Check if command has a link
        if len(message.command) > 1:
            url = message.command[1]
            
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            try:
                # Additional URL validation could be added here
                if len(url) < 4:  # Simple length check
                    raise ValueError("Invalid URL")
                    
                # Generate token and save link
                token = generate_token()
                if not token:
                    await message.reply("⚠️ Error generating link. Please try again.")
                    return
                
                # Save link using save_link function
                save_link(token, url)
                
                # Create shareable link using telegram.dog
                share_link = f"https://telegram.dog/{BOT_USERNAME}?start={token}"
                
                # Create share button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Share Link", url=f"https://t.me/share/url?url={quote(share_link)}")]
                ])
                
                # Check if it's a Telegram link
                is_telegram_link = 't.me/' in url.lower() or 'telegram.me/' in url.lower()
                
                await message.reply(
                    "✅ **Protected Link Generated!**\n\n"
                    f"🔗 Your link: `{share_link}`\n\n"
                    "📝 **Link Details:**\n"
                    "• Valid for 1 year\n"
                    f"• Type: {'Telegram Channel/Group' if is_telegram_link else 'External Website'}\n"
                    "🔄 Use the button below to share",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                await message.reply(
                    "❌ **Invalid URL Format**\n"
                    "Example: `/gdv https://example.com` or\n"
                    "Example: `/gdv t.me/mrgadhvii`",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await message.reply(
                "❌ **Please provide a URL to protect**\n"
                "Example: `/gdv https://example.com` or\n"
                "Example: `/gdv t.me/mrgadhvii`",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Error in gdv command: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

async def shorten_url(url: str) -> str:
    """Shorten a URL using ulvis.net API"""
    api_url = "https://ulvis.net/api.php"
    params = {
        "url": url,
        "private": 1,
        "format": "json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, params=params) as response:
            data = await response.json()
            return data.get("result", {}).get("short_url", url)

async def create_share_button(telegram_link: str, caption: str = None) -> str:
    """Create share text with optional caption."""
    # Generate token for the link
    token = generate_token()
    save_link(token, telegram_link)
    
    # Create bot link with token
    bot_link = f"https://t.me/{BOT_USERNAME}?start={token}"
    
    # Try to shorten the URL
    try:
        short_url = await shorten_url(bot_link)
    except:
        short_url = bot_link
    
    # Create share text
    share_text = f"🔐 **Protected Channel Link**\n\n"
    
    if caption:
        share_text += f"{caption}\n\n"
    
    share_text += f"🔗 **Join here:** {short_url}\n\n"
    share_text += "__Secured by @" + BOT_USERNAME + "__"
    
    return share_text

def create_channel_keyboard():
    """Create the main keyboard with channel buttons"""
    keyboard = []
    for channel_id, channel in channels.items():
        keyboard.append([
            InlineKeyboardButton(
                channel["name"],
                callback_data=f"channel_{channel_id}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)

@app.on_message(filters.private & filters.text & ~filters.command(["start", "gdv", "help", "skip", "broadcast", "broadcat"]))
@log_command
async def handle_caption(client, message: Message):
    """Handle caption input"""
    try:
        user_id = message.from_user.id
        
        # Check if user is banned
        if ip_checker.is_user_banned(user_id):
            await message.reply(
                "🚫 You are banned from using this bot.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Check if user is verified
        if not ip_checker.is_verified(user_id):
            await message.reply(
                "❌ Please verify your location first.\n"
                "Use /start to begin verification."
            )
            return
        
        if user_id in user_states and user_states[user_id].waiting_for == "caption":
            user_states[user_id].caption = message.text
            
            # Ask if they want to add an image
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, add image", callback_data="add_image"),
                    InlineKeyboardButton("❌ No image", callback_data="no_image")
                ]
            ])
            
            await message.reply(
                "🖼 *Would you like to add an image to your post?*",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            user_states[user_id].waiting_for = "image_choice"
        else:
            # Default response for messages without context
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/MrGadhvii"),
                    InlineKeyboardButton("🔔 Updates", url="https://t.me/TheGadhvii")
                ],
                [
                    InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")
                ]
            ])
            
            await message.reply(
                "👋 Hi! I'm a channel link protection bot.\n\n"
                "**Available Commands:**\n"
                "• /start - Start the bot\n"
                "• /gdv - Generate protected link\n\n"
                "Need help? Contact @MrGadhvii",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")
        # Don't send error message to user for regular messages

@app.on_message(filters.photo & filters.private)
@log_command
async def handle_photo(client, message: Message):
    """Handle photo upload"""
    try:
        user_id = message.from_user.id
        
        # Check if user is banned
        if ip_checker.is_user_banned(user_id):
            await message.reply(
                "🚫 You are banned from using this bot.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        # Check if user is verified
        if not ip_checker.is_verified(user_id):
            await message.reply(
                "❌ Please verify your location first.\n"
                "Use /start to begin verification."
            )
            return
        
        if user_id in user_states and user_states[user_id].waiting_for == "image":
            # Save image file_id
            user_states[user_id].image = message.photo.file_id
            
            # Create final post
            await create_final_post(client, message, user_id)
        else:
            # If user sends photo without context
            await message.reply(
                "❓ ​🇼​​🇴​​🇺​​🇱​​🇩​ ​🇾​​🇴​​🇺​ ​🇱​​🇮​​🇰​​🇪​ ​🇹​​🇴​ ​🇨​​🇷​​🇪​​🇦​​🇹​​🇪​ ​🇦​ ​🇵​​🇷​​🇴​​🇹​​🇪​​🇨​​🇹​​🇪​​🇩​ ​🇱​​🇮​​🇳​​🇰 ​?\n"
                "Use /gdv command followed by your channel link.\n\n"
                "Example: `/gdv https://example.com`",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"Error handling photo: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

async def create_final_post(client, message: Message, user_id: int):
    """Create the final post with image and caption"""
    try:
        state = user_states[user_id]
        share_text = await create_share_button(state.telegram_link, state.caption)
        
        # Create share button
        share_button = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 Share Post",
                    url=f"https://t.me/share/url?url={quote(share_text)}"
                )
            ]
        ])
        
        if state.image:
            # Send with image
            await client.send_photo(
                chat_id=message.chat.id,
                photo=state.image,
                caption=share_text,
                reply_markup=share_button,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Send without image
            await client.send_message(
                chat_id=message.chat.id,
                text=share_text,
                reply_markup=share_button,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Clear user state
        del user_states[user_id]
    except Exception as e:
        logger.error(f"Error creating final post: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

@app.on_callback_query()
@log_callback
async def handle_callback(client, callback_query: CallbackQuery):
    """Handle callback queries"""
    try:
        user_id = callback_query.from_user.id
        
        # Check if user is banned
        if ip_checker.is_user_banned(user_id):
            await callback_query.answer("🚫 You are banned from using this bot.", show_alert=True)
            return
            
        # Check if user is verified
        if not ip_checker.is_verified(user_id):
            await callback_query.answer("❌ Please verify your location first. Use /start to begin verification.", show_alert=True)
            return
        
        data = callback_query.data
        
        if data == "add_image":
            await callback_query.message.reply(
                "📤 *Send me an image for your post*",
                parse_mode=ParseMode.MARKDOWN
            )
            user_states[user_id].waiting_for = "image"
            await callback_query.answer()
            
        elif data == "no_image":
            await create_final_post(client, callback_query.message, user_id)
            await callback_query.answer()
            
        elif data.startswith("channel_"):
            channel_id = data.replace("channel_", "")
            channel = channels.get(channel_id)
            
            if not channel:
                await callback_query.answer("Channel not found!", show_alert=True)
                return
                
            try:
                # First acknowledge the callback
                await callback_query.answer("Loading channel info...")
                
                # Check if it's a Telegram link
                if 't.me/' in channel['link'].lower() or 'telegram.me/' in channel['link'].lower():
                    # For Telegram links, use redirect
                    webapp_url = f"https://adorable-sfogliatella-26d564.netlify.app/redirect.html?url={quote(channel['link'])}"
                else:
                    # For non-Telegram links, open directly
                    webapp_url = channel['link']
                
                # Create keyboard with WebApp button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🌟 𝙅𝙤𝙞𝙣 𝘾𝙝𝙖𝙣𝙣𝙚𝙡",
                        web_app=WebAppInfo(url=webapp_url)
                    )],
                    [InlineKeyboardButton("« 𝘽𝙖𝙘𝙠 𝘽𝙚𝙛𝙤𝙧𝙚", callback_data="back")]
                ])
                
                channel_text = (
                    f"🎉 {channel['name']}\n\n"
                    f"📝 {channel['description']}\n\n"
                    "🔐 Click the button below to join securely:"
                )
                
                await callback_query.message.edit_text(
                    channel_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error in channel handling: {str(e)}")
                await callback_query.answer("Error displaying channel info. Please try again.", show_alert=True)
                
        elif data == "back":
            welcome_text = (
                f"👋 **Welcome {callback_query.from_user.mention}!**\n\n"
                "🔥 **Premium Channels Directory**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**Select any channel below to join:**\n"
                "__All links are protected and secure__ 🔒\n\n"
                "**Features:**\n"
                "• 𝙸𝚗𝚜𝚝𝚊𝚗𝚝 𝙰𝚌𝚌𝚎𝚜𝚜 🚀\n"
                "• 𝙿𝚛𝚎𝚖𝚒𝚞𝚖 𝙲𝚘𝚗𝚝𝚎𝚗𝚝 ⭐\n"
                "• 𝙳𝚊𝚒𝚕𝚢 𝚄𝚙𝚍𝚊𝚝𝚎𝚜 📢\n"
                "• 𝙴𝚡𝚌𝚕𝚞𝚜𝚒𝚟𝚎 𝙱𝚎𝚗𝚎𝚒𝚝𝚜 🎁"
            )
            
            await callback_query.message.edit_text(
                welcome_text,
                reply_markup=create_channel_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif data == "confirm_broadcast":
            if user_id != 7029363479:  # Only admin can confirm broadcast
                await callback_query.answer("❌ Only admin can broadcast messages!", show_alert=True)
                return
                
            # Get broadcast data
            broadcast_data = user_states.get(user_id)
            if not broadcast_data:
                await callback_query.answer("❌ Broadcast data not found!", show_alert=True)
                return
                
            broadcast_msg = broadcast_data["broadcast_msg"]
            reply_msg = broadcast_data["reply_msg"]
            confirm_msg = broadcast_data["confirm_msg"]
            
            # Update status message
            await confirm_msg.edit_text("🚀 Broadcasting message...")
            
            # Initialize counters
            success = 0
            failed = 0
            
            # Send to all users
            for target_id in USERS:
                try:
                    if reply_msg and (reply_msg.photo or reply_msg.video or reply_msg.document):
                        # Handle media messages
                        if reply_msg.photo:
                            await client.send_photo(
                                chat_id=target_id,
                                photo=reply_msg.photo.file_id,
                                caption=broadcast_msg,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        elif reply_msg.video:
                            await client.send_video(
                                chat_id=target_id,
                                video=reply_msg.video.file_id,
                                caption=broadcast_msg,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        elif reply_msg.document:
                            await client.send_document(
                                chat_id=target_id,
                                document=reply_msg.document.file_id,
                                caption=broadcast_msg,
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        # Text only
                        await client.send_message(
                            chat_id=target_id,
                            text=broadcast_msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    success += 1
                    
                    # Update status every 20 successful sends
                    if success % 20 == 0:
                        await confirm_msg.edit_text(
                            f"🚀 Broadcasting...\n\n"
                            f"✅ Sent: {success}\n"
                            f"❌ Failed: {failed}\n"
                            f"⏳ Remaining: {len(USERS) - (success + failed)}"
                        )
                except Exception as e:
                    print(f"Failed to send to {target_id}: {str(e)}")
                    failed += 1
                
                # Add delay to avoid flood limits
                await asyncio.sleep(0.1)
            
            # Send final status
            await confirm_msg.edit_text(
                f"✅ Broadcast Completed!\n\n"
                f"📊 **Statistics:**\n"
                f"• Total Users: {len(USERS)}\n"
                f"• Successful: {success}\n"
                f"• Failed: {failed}\n\n"
                f"🕒 Completed at: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # Clear broadcast data
            if user_id in user_states:
                del user_states[user_id]
                
        elif data == "cancel_broadcast":
            if user_id != 7029363479:  # Only admin can cancel broadcast
                await callback_query.answer("❌ Only admin can cancel broadcast!", show_alert=True)
                return
                
            broadcast_data = user_states.get(user_id)
            if broadcast_data and broadcast_data["confirm_msg"]:
                await broadcast_data["confirm_msg"].edit_text("❌ Broadcast Cancelled!")
                
            # Clear broadcast data
            if user_id in user_states:
                del user_states[user_id]
                
    except Exception as e:
        print(f"Callback error: {str(e)}")
        try:
            await callback_query.answer(
                "⚠️ Something went wrong. Please try again.",
                show_alert=True
            )
        except:
            pass

@app.on_message(filters.command(["broadcast", "broadcat"]) & filters.user(7029363479))
async def broadcast_command(client, message: Message):
    """Handle broadcast command - Admin only"""
    try:
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(message.from_user.id, await get_user_ip(message))
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
        # Check if message is empty
        if message.reply_to_message:
            # Broadcasting a replied message
            msg = message.reply_to_message
            
            # Send initial status
            status = await message.reply("🚀 **Starting broadcast...**")
            
            success = 0
            failed = 0
            
            # Get total users
            total_users = len(USERS)
            if total_users == 0:
                await status.edit("❌ No users found in database!")
                return
            
            for user_id in USERS:
                try:
                    if msg.photo:
                        # For photos
                        await msg.copy(user_id)
                    elif msg.video:
                        # For videos
                        await msg.copy(user_id)
                    elif msg.document:
                        # For documents
                        await msg.copy(user_id)
                    elif msg.text:
                        # For text messages
                        await client.send_message(user_id, msg.text)
                    success += 1
                except FloodWait as e:
                    # Handle flood wait
                    await asyncio.sleep(e.value)
                    # Retry after waiting
                    try:
                        await msg.copy(user_id)
                        success += 1
                    except:
                        failed += 1
                except Exception as e:
                    print(f"Failed to send to {user_id}: {e}")
                    failed += 1
                
                # Update status every 5 users
                if success % 5 == 0:
                    try:
                        await status.edit(
                            f"🚀 **Broadcasting...**\n\n"
                            f"**Total Users:** {total_users}\n"
                            f"**Completed:** {success + failed}/{total_users}\n"
                            f"**Success:** {success}\n"
                            f"**Failed:** {failed}"
                        )
                    except:
                        pass
                    
                await asyncio.sleep(0.2)  # Delay to avoid flood
        
        elif len(message.command) > 1:
            # Broadcasting a text message
            broadcast_text = " ".join(message.command[1:])
            
            # Send initial status
            status = await message.reply("🚀 **Starting broadcast...**")
            
            success = 0
            failed = 0
            
            # Get total users
            total_users = len(USERS)
            if total_users == 0:
                await status.edit("❌ No users found in database!")
                return
            
            for user_id in USERS:
                try:
                    await client.send_message(user_id, broadcast_text)
                    success += 1
                except FloodWait as e:
                    # Handle flood wait
                    await asyncio.sleep(e.value)
                    # Retry after waiting
                    try:
                        await client.send_message(user_id, broadcast_text)
                        success += 1
                    except:
                        failed += 1
                except Exception as e:
                    print(f"Failed to send to {user_id}: {e}")
                    failed += 1
                
                # Update status every 5 users
                if success % 5 == 0:
                    try:
                        await status.edit(
                            f"🚀 **Broadcasting...**\n\n"
                            f"**Total Users:** {total_users}\n"
                            f"**Completed:** {success + failed}/{total_users}\n"
                            f"**Success:** {success}\n"
                            f"**Failed:** {failed}"
                        )
                    except:
                        pass
                    
                await asyncio.sleep(0.2)  # Delay to avoid flood
        
        else:
            # No message to broadcast
            await message.reply(
                "**📢 Broadcast Usage**\n\n"
                "**1.** Forward any message and reply it with `/broadcast`\n"
                "**2.** Use `/broadcast your message`"
            )
            return
        
        # Send final status
        await status.edit(
            f"✅ **Broadcast Completed!**\n\n"
            f"**Total Users:** {total_users}\n"
            f"**Success:** {success}\n"
            f"**Failed:** {failed}\n\n"
            f"**Completion Time:** {datetime.now().strftime('%H:%M:%S')}"
        )
        
    except Exception as e:
        print(f"Broadcast Error: {str(e)}")
        await message.reply(
            "❌ **An error occurred!**\n\n"
            f"**Error:** `{str(e)}`"
        )

@app.on_message(filters.command("ipstats") & filters.user(7029363479))
async def ip_stats_command(client, message: Message):
    """Show IP verification statistics"""
    try:
        stats = ip_checker.get_stats()
        stats_text = (
            "📊 **IP Verification Statistics**\n\n"
            f"👥 Total Users Checked: `{stats['total_checked']}`\n"
            f"🚫 Total Banned Users: `{stats['total_banned']}`\n\n"
            "🌍 **Users by Country:**\n"
        )
        
        # Add country statistics
        for country, count in stats['countries'].items():
            stats_text += f"• {country}: `{count}`\n"
        
        await message.reply(stats_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"Stats error: {str(e)}")
        await message.reply("⚠️ Error getting statistics.")

@app.on_message(filters.command("ban"))
async def ban_command(client, message: Message):
    """Ban a user command"""
    try:
        # Check if admin
        if message.from_user.id != 7029363479:
            return
        
        # Get user ID to ban
        if len(message.command) != 2:
            await message.reply("Use: /ban [user_id]")
            return
        
        try:
            user_id = int(message.command[1])
        except:
            await message.reply("Invalid user ID")
            return
        
        # Ban user
        ip_checker.banned_users.add(user_id)
        ip_checker._save_banned_users()
        await message.reply(f"Banned user: {user_id}")
        
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

@app.on_message(filters.command("unban"))
async def unban_command(client, message: Message):
    """Unban a user command"""
    try:
        # Check if admin
        if message.from_user.id != 7029363479:
            return
        
        # Get user ID to unban
        if len(message.command) != 2:
            await message.reply("Use: /unban [user_id]")
            return
        
        try:
            user_id = int(message.command[1])
        except:
            await message.reply("Invalid user ID")
            return
        
        # Unban user
        if user_id in ip_checker.banned_users:
            ip_checker.banned_users.remove(user_id)
            ip_checker._save_banned_users()
            await message.reply(f"Unbanned user: {user_id}")
        else:
            await message.reply(f"User {user_id} is not banned")
        
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

async def send_ping():
    """Send ping message to admin."""
    global PING_COUNT
    ADMIN_ID = 0000000000
    
    while True:
        try:
            PING_COUNT += 1
            now = datetime.now()
            delta = now - START_TIME
            
            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            seconds = delta.seconds % 60
            
            uptime_parts = []
            if days > 0:
                uptime_parts.append(f"{days}d")
            if hours > 0:
                uptime_parts.append(f"{hours}h")
            if minutes > 0:
                uptime_parts.append(f"{minutes}m")
            if seconds > 0 or not uptime_parts:
                uptime_parts.append(f"{seconds}s")
            
            uptime = " ".join(uptime_parts)
            
            emojis = ["⚡", "✨", "🚀", "💫", "⭐", "🌟", "💪", "🔥", "🎯", "🌈"]
            emoji = random.choice(emojis)
            
            status_msg = (
                f"{emoji} **Bot Status Update** {emoji}\n\n"
                f"👥 **Total Users:** `{len(USERS)}`\n"
                f"🔄 **Ping Count:** `#{PING_COUNT}`\n"
                f"⏱ **Uptime:** `{uptime}`\n"
                f"🎯 **Status:** `Operational`\n\n"
                f"_Last checked: {now.strftime('%H:%M:%S')}_"
            )
            
            await app.send_message(
                chat_id=ADMIN_ID,
                text=status_msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            print(f"Ping error: {str(e)}")
        
        await asyncio.sleep(60)

async def shutdown(signal, loop):
    """Clean shutdown of the bot"""
    logger.info(f'Stop signal received ({signal.name}). Exiting...')
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    logger.info(f'Cancelling {len(tasks)} outstanding tasks')
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    """Main function to run the bot"""
    try:
        # Start the bot
        await app.start()
        logger.info("Bot started successfully!")
        
        # Get bot info
        me = await app.get_me()
        global BOT_USERNAME
        BOT_USERNAME = me.username
        logger.info(f"Bot started as @{BOT_USERNAME}")
        
        # Initialize command logging
        setup_command_handlers(app)
        logger.info("Command logging initialized")
        
        # Start Flask server in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Flask server thread started")
        
        # Start ping service
        asyncio.create_task(send_ping())
        logger.info("Services started")
        logger.info("Bot is running...")
        
        await idle()
        
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
    finally:
        logger.info("Stopping bot...")
        await app.stop()

if __name__ == "__main__":
    try:
        app.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Bot stopped")
