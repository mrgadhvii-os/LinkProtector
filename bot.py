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
from aiohttp import web
from helper import log_command, log_callback, setup_command_handlers
from pyrogram.errors import FloodWait
from ip import IPChecker
import socket

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

# Add after bot initialization
ip_checker = IPChecker()

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

def save_link(token: str, link: str):
    """Save link data to JSON file."""
    try:
        with open('links.json', 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"links": {}}
    
    data["links"][token] = {
        "link": link,
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
            ip_text += "🚫 **Status:** You are not allowed to use this bot (India only)"
        
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

# Modify the start command
@app.on_message(filters.command("start"))
@log_command
async def start_command(client, message: Message):
    """Handle /start command"""
    try:
        # Get user's IP and verify
        user_ip = await get_user_ip(message)
        is_allowed, ban_message = await ip_checker.verify_user(message.from_user.id, user_ip)
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
        global BOT_USERNAME
        if not BOT_USERNAME:
            me = await client.get_me()
            BOT_USERNAME = me.username
        
        # Check if started with a token
        if len(message.command) > 1:
            token = message.command[1]
            link_data = get_link_data(token)
            
            if link_data:
                # Create WebApp URL
                webapp_url = f"https://exciting-rat.static.domains/redirect.html?url={quote(link_data['link'])}"
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🌟 Join Channel",
                        web_app=WebAppInfo(url=webapp_url)
                    )]
                ])
                
                await message.reply(
                    "🎉 *Welcome to Protected Channel Link!*\n\n"
                    "🔐 Click the button below to join securely:\n\n"
                    "_This link is protected by our secure system_",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Modern welcome message with emojis and formatting
        welcome_text = (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"**🎊 Welcome {message.from_user.mention}!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 I am a **Channel Link Protection Bot**\n"
            f"I can help you protect your channel links with advanced security.\n\n"
            f"**🛠 Available Commands:**\n"
            f"• `/start` - Start the bot\n"
            f"• `/gdv` - Generate protected link\n\n"
            f"**🌟 Key Features:**\n"
            f"• 🔒 Advanced Link Protection\n"
            f"• 🚀 Instant Link Generation\n"
            f"• 🛡️ Anti-Extraction System\n"
            f"• 📊 Real-time Analytics\n"
            f"• 🔄 Auto-updating Links\n\n"
            f"**📝 Example:**\n"
            f"`/gdv https://t.me/yourchannel`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        
        # Create keyboard with developer contact
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
            welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Error in start command: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

@app.on_message(filters.command("gdv"))
@log_command
async def gdv_command(client, message: Message):
    """Handle /gdv command"""
    try:
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(message.from_user.id, await get_user_ip(message))
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
        global BOT_USERNAME
        if not BOT_USERNAME:
            me = await client.get_me()
            BOT_USERNAME = me.username
            
        # Check if command has a link
        if len(message.command) > 1:
            telegram_link = message.command[1]
            
            # Validate and clean the link
            if not telegram_link.startswith(('https://t.me/', 'http://t.me/', 't.me/')):
                await message.reply(
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
            
            await message.reply(
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
            await message.reply(
                "❌ *Please provide a Telegram link*\n"
                "Example: `/gdv https://t.me/yourchannel`",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        print(f"Error in gdv command: {str(e)}")
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
    share_text = f"🔐 *Protected Channel Link*\n\n"
    
    if caption:
        share_text += f"{caption}\n\n"
    
    share_text += f"🔗 *Join here:* {short_url}\n\n"
    share_text += "_Secured by @" + BOT_USERNAME + "_"
    
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
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(message.from_user.id, await get_user_ip(message))
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
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
        print(f"Message handling error: {str(e)}")
        # Don't send error message to user for regular messages

@app.on_message(filters.photo & filters.private)
@log_command
async def handle_photo(client, message: Message):
    """Handle photo upload"""
    try:
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(message.from_user.id, await get_user_ip(message))
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
        user_id = message.from_user.id
        if user_id in user_states and user_states[user_id].waiting_for == "image":
            # Save image file_id
            user_states[user_id].image = message.photo.file_id
            
            # Create final post
            await create_final_post(client, message, user_id)
        else:
            # If user sends photo without context
            await message.reply(
                "❓ Would you like to create a protected link?\n"
                "Use /gdv command followed by your channel link.\n\n"
                "Example: `/gdv https://t.me/yourchannel`",
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        print(f"Error handling photo: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

async def create_final_post(client, message: Message, user_id: int):
    """Create the final post with image and caption"""
    try:
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(user_id, await get_user_ip(message))
        
        if not is_allowed:
            await message.reply(ban_message)
            return
        
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
        print(f"Error creating final post: {str(e)}")
        await message.reply("⚠️ Something went wrong. Please try again.")

@app.on_callback_query()
@log_callback
async def handle_callback(client, callback_query: CallbackQuery):
    """Handle callback queries"""
    try:
        # Verify user access
        is_allowed, ban_message = await ip_checker.verify_user(callback_query.from_user.id, await get_user_ip(callback_query.message))
        
        if not is_allowed:
            await callback_query.answer(ban_message)
            return
        
        data = callback_query.data
        user_id = callback_query.from_user.id
        
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

class BanManager:
    def __init__(self):
        self.ban_file = 'user_bans.json'
        self.banned_users = self.load_bans()
    
    def load_bans(self):
        try:
            with open(self.ban_file, 'r') as f:
                data = json.load(f)
                return set(data.get('banned_users', []))
        except:
            return set()
    
    def save_bans(self):
        with open(self.ban_file, 'w') as f:
            json.dump({'banned_users': list(self.banned_users)}, f)
    
    def ban_user(self, user_id: int) -> bool:
        self.banned_users.add(user_id)
        self.save_bans()
        return True
    
    def unban_user(self, user_id: int) -> bool:
        if user_id in self.banned_users:
            self.banned_users.remove(user_id)
            self.save_bans()
            return True
        return False
    
    def is_banned(self, user_id: int) -> bool:
        return user_id in self.banned_users

# Initialize ban manager
ban_manager = BanManager()

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
        ban_manager.ban_user(user_id)
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
        if ban_manager.unban_user(user_id):
            await message.reply(f"Unbanned user: {user_id}")
        else:
            await message.reply(f"User {user_id} is not banned")
        
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

async def send_ping():
    """Send ping message to admin."""
    global PING_COUNT
    ADMIN_ID = 7029363479
    
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

async def start_webserver():
    """Start web server for Heroku."""
    if os.environ.get("DYNO"):
        web_app = web.Application()
        web_app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))
        runner = web.AppRunner(web_app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        await web.TCPSite(runner, "0.0.0.0", port).start()
        print(f"Web server started on port {port}")

async def main():
    """Main function to run the bot."""
    try:
        # Start the bot
        await app.start()
        print("Bot started successfully!")
        
        # Get bot info
        me = await app.get_me()
        global BOT_USERNAME
        BOT_USERNAME = me.username
        print(f"Bot started as @{BOT_USERNAME}")
        
        # Initialize command logging
        setup_command_handlers(app)
        print("Command logging initialized")
        
        # Start web server if on Heroku
        if os.environ.get("DYNO"):
            await start_webserver()
        
        # Start ping service
        asyncio.create_task(send_ping())
        print("Services started")
        print("Bot is running...")
        
        # Keep the bot running using imported idle function
        await idle()
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    app.run(main()) 