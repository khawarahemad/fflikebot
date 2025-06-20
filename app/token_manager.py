# app/token_manager.py
import os
import json
import threading
import time
import logging
import requests
from cachetools import TTLCache
from datetime import timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys
import asyncio
from .like_routes import _SERVERS, async_post_request
from .utils.protobuf_utils import encode_uid
from .utils.http_utils import get_headers

logger = logging.getLogger(__name__)

AUTH_URL = os.getenv("AUTH_URL", "https://jwtxthug.up.railway.app/token") 
CACHE_DURATION = timedelta(hours=7).seconds
TOKEN_REFRESH_THRESHOLD = timedelta(hours=6).seconds
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class TokenCache:
    def __init__(self, servers_config):
        self.cache = TTLCache(maxsize=1000, ttl=CACHE_DURATION)
        self.last_refresh = {}
        self.lock = threading.Lock()
        self.session = requests.Session()
        self.servers_config = servers_config
        self.production = os.environ.get("PRODUCTION", "0") == "1"
        # On startup, always try to load tokens from file first
        for server_key in self.servers_config:
            loaded = self._load_tokens_from_file(server_key)
            if not loaded:
                self._refresh_tokens(server_key)
            self.last_refresh[server_key] = time.time()
            logger.info(f"[TOKEN] Startup: {len(self.cache.get(server_key, []))} tokens loaded for {server_key}.")

    def get_tokens(self, server_key):
        with self.lock:
            # If tokens are in memory, use them directly
            tokens = self.cache.get(server_key)
            if tokens:
                logger.debug(f"[TOKEN] Returning {len(tokens)} in-memory tokens for {server_key}.")
                return tokens
            # If not in memory, try loading from file
            loaded = self._load_tokens_from_file(server_key)
            tokens = self.cache.get(server_key)
            if tokens:
                logger.info(f"[TOKEN] Loaded {len(tokens)} tokens for {server_key} from file on demand.")
                return tokens
            # If still not present, only refresh if not in production
            if not self.production:
                logger.info(f"[TOKEN] No tokens in memory or file for {server_key}, refreshing...")
                self._refresh_tokens(server_key)
                tokens = self.cache.get(server_key, [])
                logger.info(f"[TOKEN] After refresh: {len(tokens)} tokens for {server_key}.")
                return tokens
            else:
                logger.warning(f"[TOKEN] No tokens available for {server_key} in production mode!")
                return []

    def _fetch_one_token(self, user, server_key):
        """Fetches a single token for a user and handles errors."""
        retries = 3
        for attempt in range(retries):
            try:
                params = {'uid': user['uid'], 'password': user['password']}
                response = self.session.get(AUTH_URL, params=params, timeout=160)
                if response.status_code == 200:
                    token = response.json().get("token")
                    if token:
                        return token
                    else:
                        logger.warning(f"[TOKEN] Token missing in successful response for user {user['uid']} on {server_key}.")
                        return None # Don't retry
                else:
                    logger.warning(f"[TOKEN] Could not get token for user {user['uid']} on {server_key}. Server responded with status {response.status_code}.")
                    return None # Don't retry
            except requests.exceptions.RequestException as e:
                logger.warning(f"[TOKEN] Network error for user {user['uid']} (Attempt {attempt + 1}/{retries}). Retrying...")
                if attempt < retries - 1:
                    time.sleep(2) # Wait 2 seconds before retrying
                else:
                    logger.error(f"[TOKEN] Final network error for user {user['uid']} after {retries} attempts. This user will be skipped.")
            except Exception as e:
                # Catch other unexpected errors
                logger.error(f"[TOKEN] Unexpected error for user {user['uid']} on {server_key}: {e}")
                return None # Don't retry for other errors
        return None

    def _refresh_tokens(self, server_key):
        try:
            creds = self._load_credentials(server_key)
            if not creds:
                logger.info(f"[TOKEN] No credentials for {server_key}, skipping refresh.")
                return

            logger.info(f"[TOKEN] Starting parallel token refresh for {len(creds)} accounts on {server_key} server...")
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                # Use map to fetch tokens in parallel and filter out None values from failed requests
                tokens = list(filter(None, executor.map(lambda user: self._fetch_one_token(user, server_key), creds)))

            if tokens:
                self.cache[server_key] = tokens
                self._save_tokens_to_file(server_key, tokens)
                logger.info(f"[TOKEN] Successfully refreshed {len(tokens)} out of {len(creds)} tokens for {server_key} server.")
            else:
                logger.warning(f"[TOKEN] No valid tokens found for {server_key} after refresh. Please check your credentials or network connection.")
                self.cache[server_key] = []
                self._save_tokens_to_file(server_key, [])

        except Exception as e:
            logger.error(f"[TOKEN] Critical error during token refresh for {server_key}: {e}")
            if server_key not in self.cache:
                self.cache[server_key] = []
                self._save_tokens_to_file(server_key, [])

    def _save_tokens_to_file(self, server_key, tokens):
        try:
            file_path = os.path.join(CACHE_DIR, f"tokens_{server_key}.json")
            with open(file_path, 'w') as f:
                json.dump(tokens, f)
        except Exception as e:
            logger.error(f"[TOKEN] Failed to save tokens to file for {server_key}.")

    def _load_tokens_from_file(self, server_key):
        try:
            file_path = os.path.join(CACHE_DIR, f"tokens_{server_key}.json")
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    tokens = json.load(f)
                    if tokens:
                        self.cache[server_key] = tokens
                        logger.info(f"[TOKEN] Loaded {len(tokens)} tokens for {server_key} from cache file.")
                        return True
            return False
        except Exception as e:
            logger.error(f"[TOKEN] Failed to load tokens from file for {server_key}.")
            return False

    def _load_credentials(self, server_key):
        try:
            config_data = os.getenv(f"{server_key}_CONFIG")
            if config_data:
                return json.loads(config_data)

          
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', f'{server_key.lower()}_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"[TOKEN] No config file found for {server_key} server. Please add your guest account credentials to {config_path}.")
                return []
        except Exception as e:
            logger.error(f"[TOKEN] Error loading credentials for {server_key}. Please check your config file format.")
            return []

def validate_tokens(region, uid_to_test):
    """
    Validate all tokens for a region by attempting to fetch player info for a known UID.
    Usage: python -m app.token_manager REGION UID
    """
    logging.basicConfig(level=logging.INFO)
    token_cache = TokenCache(servers_config=_SERVERS)
    tokens = token_cache.get_tokens(region)
    info_url = f"{_SERVERS[region]}/GetPlayerPersonalShow"
    uid_enc = encode_uid(uid_to_test)

    async def check_tokens():
        valid = 0
        for token in tokens:
            try:
                resp = await async_post_request(info_url, bytes.fromhex(uid_enc), token)
                if resp:
                    logging.info(f"[VALIDATE] Token valid: {token[:8]}...")
                    valid += 1
                else:
                    logging.warning(f"[VALIDATE] Token invalid: {token[:8]}...")
            except Exception as e:
                logging.error(f"[VALIDATE] Token error: {token[:8]}... {e}")
        print(f"Total valid tokens: {valid}/{len(tokens)}")

    asyncio.run(check_tokens())

if __name__ == "__main__" and len(sys.argv) == 3:
    region = sys.argv[1]
    uid = sys.argv[2]
    validate_tokens(region, uid)