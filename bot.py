import os
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
    WebAppInfo
)
from pyrogram.enums import ParseMode
from config import API_ID, API_HASH, BOT_TOKEN
import aiohttp
import json
import re
from urllib.parse import quote
import base64
import time
import random
import string
import asyncio
from datetime import datetime

# Initialize bot
app = Client(
    "channel_link_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Store bot username and start time
BOT_USERNAME = ""
START_TIME = datetime.now()
PING_COUNT = 0

def get_uptime():
    """Get bot uptime in a readable format."""
    now = datetime.now()
    delta = now - START_TIME
    
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    
    return " ".join(parts)

async def send_ping():
    """Send ping message to admin."""
    global PING_COUNT
    ADMIN_ID = 7029363479
    
    while True:
        try:
            PING_COUNT += 1
            uptime = get_uptime()
            
            # Get random emoji for variety
            emojis = ["⚡", "✨", "🚀", "💫", "⭐", "🌟", "💪", "🔥", "🎯", "🌈"]
            emoji = random.choice(emojis)
            
            # Create status message
            status_msg = (
                f"{emoji} **Bot Status Update** {emoji}\n\n"
                f"🔄 **Ping Count:** `#{PING_COUNT}`\n"
                f"⏱ **Uptime:** `{uptime}`\n"
                f"🎯 **Status:** `Operational`\n\n"
                f"_Last checked: {datetime.now().strftime('%H:%M:%S')}_"
            )
            
            await app.send_message(
                chat_id=ADMIN_ID,
                text=status_msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            print(f"Error in ping service: {str(e)}")
        
        # Wait for 1 minute
        await asyncio.sleep(60)

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle the /start command."""
    try:
        global BOT_USERNAME
        if not BOT_USERNAME:
            me = await app.get_me()
            BOT_USERNAME = me.username
            
            # Start ping service
            asyncio.create_task(send_ping())
            
        # Check if started with a token
        if len(message.command) > 1:
            token = message.command[1]
            link_data = get_link_data(token)
            
            if link_data:
                # Create WebApp URL
                webapp_url = f"https://exciting-rat.static.domains/redirect.html?url={quote(link_data['link'])}"
                
                # Create keyboard with WebApp button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🌟 Join Channel",
                        web_app=WebAppInfo(url=webapp_url)
                    )]
                ])
                
                await message.reply_text(
                    "🎉 *Welcome to Protected Channel Link!*\n\n"
                    "🔐 Click the button below to join securely:\n\n"
                    "_This link is protected by our secure system_",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Default start message
        welcome_text = (
            f"👋 **Welcome {message.from_user.mention}!**\n\n"
            "🔥 **Channel Link Protection Bot**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Commands:**\n"
            "• /gdv - Create protected link\n"
            "Example: `/gdv https://t.me/channel`\n\n"
            "**Features:**\n"
            "• Secure Links 🔒\n"
            "• Link Protection ⚡\n"
            "• Easy Sharing 🔄\n"
            "• Anti-Extraction ✨"
        )
        
        await message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        print(f"Error in start command: {str(e)}")
        await message.reply_text("⚠️ Something went wrong. Please try again.")

@app.on_message(filters.command("gdv"))
async def handle_gdv_command(client: Client, message: Message):
    try:
        global BOT_USERNAME
        if not BOT_USERNAME:
            me = await app.get_me()
            BOT_USERNAME = me.username
            
        # Check if command has a link
        if len(message.command) > 1:
            telegram_link = message.command[1]
            
            # Validate and clean the link
            if not telegram_link.startswith(('https://t.me/', 'http://t.me/', 't.me/')):
                await message.reply_text(
                    "❌ *Please provide a valid Telegram link*\n"
                    "Example: `/gdv https://t.me/yourchannel`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Generate token and save link
            token = generate_token()
            save_link(token, telegram_link)
            
            # Create shareable link
            share_link = f"https://t.me/{BOT_USERNAME}?start={token}"
            
            # Create share button
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Share Link", url=f"https://t.me/share/url?url={quote(share_link)}")]
            ])
            
            await message.reply_text(
                "✅ *Link Generated Successfully!*\n\n"
                f"🔗 Your link: `{share_link}`\n\n"
                "📝 When users click this link:\n"
                "1. Bot will start automatically\n"
                "2. They'll see a secure join button\n"
                "3. Channel link will be protected\n\n"
                "🔄 Use the button below to share",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        else:
            await message.reply_text(
                "❌ *Please provide a Telegram link*\n"
                "Example: `/gdv https://t.me/yourchannel`",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        print(f"Error in gdv command: {str(e)}")
        await message.reply_text("⚠️ Something went wrong. Please try again.")

# Store user states
user_states = {}

class UserState:
    def __init__(self):
        self.telegram_link = None
        self.caption = None
        self.image = None
        self.waiting_for = None

def generate_token():
    """Generate a unique token for the link."""
    timestamp = str(int(time.time()))
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    token = f"{timestamp}-{random_str}"
    return base64.urlsafe_b64encode(token.encode()).decode()

def save_link(token: str, link: str, caption: str = None):
    """Save link data to JSON file."""
    try:
        with open('links.json', 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"links": {}}
    
    data["links"][token] = {
        "link": link,
        "caption": caption,
        "created_at": int(time.time())
    }
    
    with open('links.json', 'w') as f:
        json.dump(data, f, indent=4)

def get_link_data(token: str):
    """Get link data from JSON file."""
    try:
        with open('links.json', 'r') as f:
            data = json.load(f)
            return data["links"].get(token)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

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

async def create_dog_link(telegram_link: str) -> str:
    """Create telegram.dog link."""
    # Clean and format the link properly
    clean_link = telegram_link.strip()
    clean_link = re.sub(r'\s+', '', clean_link)  # Remove all whitespace
    clean_link = re.sub(r'^(?:https?://)?(?:t\.me/|telegram\.me/|telegram\.dog/)', '', clean_link)
    return f"https://t.me/{clean_link}"

async def create_share_button(telegram_link: str, caption: str = None) -> str:
    """Create a shareable button with the given link and caption."""
    dog_link = await create_dog_link(telegram_link)
    
    # Create share text
    share_text = "🔥 *Exclusive Content* 🔥\n\n"
    if caption:
        share_text += f"{caption}\n\n"
    share_text += "🔒 *Secure Link* 🔒\n"
    share_text += "✨ Join through our secure portal!\n\n"
    share_text += f"🌟 [{dog_link}]({dog_link})"
    
    return share_text

@app.on_message(filters.private & filters.text & ~filters.command("gdv") & ~filters.command("start") & ~filters.command("help") & ~filters.command("skip"))
async def handle_caption(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].waiting_for == "caption":
        user_states[user_id].caption = message.text
        
        # Ask if they want to add an image
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, add image", callback_data="add_image"),
                InlineKeyboardButton("❌ No image", callback_data="no_image")
            ]
        ])
        
        await message.reply_text(
            "🖼 *Would you like to add an image to your post?*",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user_id].waiting_for = "image_choice"

@app.on_message(filters.command("skip"))
async def handle_skip(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].waiting_for == "caption":
        # Skip caption and ask about image
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, add image", callback_data="add_image"),
                InlineKeyboardButton("❌ No image", callback_data="no_image")
            ]
        ])
        
        await message.reply_text(
            "🖼 *Would you like to add an image to your post?*",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user_id].waiting_for = "image_choice"

@app.on_message(filters.photo & filters.private)
async def handle_photo(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id].waiting_for == "image":
        # Save image file_id
        user_states[user_id].image = message.photo.file_id
        
        # Create final post
        await create_final_post(client, message, user_id)

async def create_final_post(client: Client, message: Message, user_id: int):
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

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle button clicks."""
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data == "add_image":
            await callback_query.message.reply_text(
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
                
                # Create the WebApp URL with the channel link
                webapp_url = f"https://exciting-rat.static.domains/redirect.html?url={quote(channel['link'])}"
                
                # Create keyboard with WebApp button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🌟 Join Channel",
                        web_app=WebAppInfo(url=webapp_url)
                    )],
                    [InlineKeyboardButton("« Back to Channels", callback_data="back")]
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
                print(f"Error in channel handling: {str(e)}")
                await callback_query.answer("Error displaying channel info. Please try again.", show_alert=True)
                
        elif data == "back":
            welcome_text = (
                f"👋 **Welcome {callback_query.from_user.mention}!**\n\n"
                "🔥 **Premium Channels Directory**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**Select any channel below to join:**\n"
                "_All links are protected and secure_ 🔒\n\n"
                "**Features:**\n"
                "• Instant Access 🚀\n"
                "• Premium Content ⭐\n"
                "• Daily Updates 📢\n"
                "• Exclusive Benefits 🎁"
            )
            
            await callback_query.message.edit_text(
                welcome_text,
                reply_markup=create_channel_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        print(f"Callback error: {str(e)}")
        try:
            await callback_query.answer(
                "⚠️ Something went wrong. Please try again.",
                show_alert=True
            )
        except:
            pass

# Run the bot
app.run() 