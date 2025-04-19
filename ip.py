import json
import aiohttp
import logging
from typing import Dict, Set, Optional, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ip_checks.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('IPChecker')

class IPChecker:
    def __init__(self):
        self.banned_users_file = 'userBAN.json'
        self.banned_users: Set[int] = self._load_banned_users()
        self.user_cache: Dict[int, Dict] = {}  # Cache user checks to reduce API calls
        
    def _load_banned_users(self) -> Set[int]:
        """Load banned users from JSON file"""
        try:
            with open(self.banned_users_file, 'r') as f:
                data = json.load(f)
                return set(data.get('userban', []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()
    
    def _save_banned_users(self):
        """Save banned users to JSON file"""
        with open(self.banned_users_file, 'w') as f:
            json.dump({'userban': list(self.banned_users)}, f, indent=4)
    
    async def get_ip_info(self, ip: str) -> Dict:
        """
        Get detailed IP information
        Returns full IP info dictionary
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://ip-api.com/json/{ip}') as response:
                    data = await response.json()
                    if data.get('status') == 'success':
                        return {
                            'country': data.get('country', 'Unknown'),
                            'region': data.get('regionName', 'Unknown'),
                            'city': data.get('city', 'Unknown'),
                            'isp': data.get('isp', 'Unknown'),
                            'timezone': data.get('timezone', 'Unknown'),
                            'ip': ip
                        }
        except Exception as e:
            logger.error(f"Error getting IP info for {ip}: {str(e)}")
        return {
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown',
            'isp': 'Unknown',
            'timezone': 'Unknown',
            'ip': ip
        }
    
    async def check_ip(self, ip: str) -> Tuple[bool, str]:
        """
        Check if IP is from India using ip-api.com
        Returns: (is_indian: bool, country: str)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://ip-api.com/json/{ip}') as response:
                    data = await response.json()
                    if data.get('status') == 'success':
                        country = data.get('country', 'Unknown')
                        is_indian = country.lower() == 'india'
                        return is_indian, country
        except Exception as e:
            logger.error(f"Error checking IP {ip}: {str(e)}")
        return False, 'Unknown'
    
    def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        return user_id in self.banned_users
    
    async def verify_user(self, user_id: int, ip: str) -> Tuple[bool, Optional[str]]:
        """
        Verify if user should be allowed to use the bot
        Returns: (is_allowed: bool, message: Optional[str])
        """
        # Check if user is already banned
        if self.is_user_banned(user_id):
            return False, "🚫 You are banned from using this bot."
        
        # Check if we have cached result
        if user_id in self.user_cache:
            if self.user_cache[user_id].get('is_indian', False):
                return True, None
            return False, "🚫 This bot is only available for users from India."
        
        # Check IP
        is_indian, country = await self.check_ip(ip)
        
        # Cache the result
        self.user_cache[user_id] = {
            'ip': ip,
            'country': country,
            'is_indian': is_indian,
            'checked_at': datetime.now().isoformat()
        }
        
        if not is_indian:
            # Ban user if not from India
            self.banned_users.add(user_id)
            self._save_banned_users()
            
            # Log the ban
            logger.warning(f"Banned user {user_id} from {country} (IP: {ip})")
            
            return False, f"🚫 This bot is only available for users from India.\nYour country: {country}"
        
        return True, None
    
    def get_stats(self) -> Dict:
        """Get IP verification statistics"""
        return {
            'total_banned': len(self.banned_users),
            'total_checked': len(self.user_cache),
            'countries': {
                data['country']: len([u for u, d in self.user_cache.items() if d['country'] == data['country']])
                for data in self.user_cache.values()
            }
        } 