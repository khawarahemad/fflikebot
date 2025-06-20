from flask import Blueprint, request, jsonify
import asyncio
from datetime import datetime, timezone
import logging
import aiohttp 
import requests 


from .utils.protobuf_utils import encode_uid, decode_info, create_protobuf 
from .utils.crypto_utils import encrypt_aes
from .token_manager import get_headers 

logger = logging.getLogger(__name__)

like_bp = Blueprint('like_bp', __name__)


_SERVERS = {}
_token_cache = None


async def async_post_request(url: str, data: bytes, token: str):
    try:
        headers = get_headers(token)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=10) as resp:
                return await resp.read()
    except Exception as e:
        logger.error(f"Async request failed: {str(e)}")
        return None

def make_request(uid_enc: str, url: str, token: str):
    data = bytes.fromhex(uid_enc)
    headers = get_headers(token)
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            return decode_info(response.content)
        logger.warning(f"Request failed with status {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        return None

async def detect_player_region(uid: str):
    for region_key, server_url in _SERVERS.items():
        tokens = _token_cache.get_tokens(region_key)
        logger.info(f"[REGION] Checking region {region_key} for UID {uid}. Tokens available: {len(tokens)}")
        if not tokens:
            logger.warning(f"[REGION] No tokens available for {region_key}. Skipping region.")
            continue

        info_url = f"{server_url}/GetPlayerPersonalShow"
        # Try up to 5 tokens to make region detection more robust
        for i, token in enumerate(tokens[:5]):
            logger.info(f"[REGION] Attempting lookup for UID {uid} in {region_key} with token {i+1}.")
            response = await async_post_request(info_url, bytes.fromhex(encode_uid(uid)), token)
            if response:
                player_info = decode_info(response)
                if player_info and player_info.AccountInfo.PlayerNickname:
                    logger.info(f"[REGION] Success! Player found in region {region_key} for UID {uid}.")
                    return region_key, player_info
        
        logger.warning(f"[REGION] Could not find player in {region_key} after trying {len(tokens[:5])} tokens.")

    return None, None

async def send_likes(uid: str, region: str):
    tokens = _token_cache.get_tokens(region) # Utilisez _token_cache
    like_url = f"{_SERVERS[region]}/LikeProfile" # Utilisez _SERVERS
    encrypted = encrypt_aes(create_protobuf(uid, region))

    tasks = [async_post_request(like_url, bytes.fromhex(encrypted), token) for token in tokens]
    results = await asyncio.gather(*tasks)

    return {
        'sent': len(results),
        'added': sum(1 for r in results if r is not None)
    }

@like_bp.route("/like", methods=["GET"])
async def like_player():
    try:
        uid = request.args.get("uid")
        if not uid or not uid.isdigit():
            return jsonify({
                "error": "Invalid UID",
                "message": "Valid numeric UID required",
                "status": 400,
                "credit": "KHAN BHAI"
            }), 400

        # Check IND tokens before region detection
        ind_tokens = _token_cache.get_tokens("IND")
        if not ind_tokens:
            logger.error("[LIKE] No valid tokens for IND server. Please check your guest accounts.")
            return jsonify({
                "error": "No valid tokens for IND server",
                "message": "Please check your IND guest accounts or try again later.",
                "status": 503,
                "credit": "KHAN BHAI"
            }), 503

        region, player_info = await detect_player_region(uid)
        if not player_info:
            logger.error(f"[LIKE] Player not found for UID {uid} in any server.")
            return jsonify({
                "error": "Player not found",
                "message": "Player not found on any server. Please check the UID or try again later.",
                "status": 404,
                "credit": "KHAN BHAI"
            }), 404

        before_likes = player_info.AccountInfo.Likes
        player_name = player_info.AccountInfo.PlayerNickname
        info_url = f"{_SERVERS[region]}/GetPlayerPersonalShow" 

        await send_likes(uid, region)

        current_tokens = _token_cache.get_tokens(region) 
        if not current_tokens:
            logger.error(f"No tokens available for {region} to verify likes after sending.")
            after_likes = before_likes
        else:
            new_info = None
            # Try up to 5 tokens to get updated player info
            for i, token in enumerate(current_tokens[:5]):
                logger.info(f"[LIKE] Attempting to verify likes for UID {uid} with token {i+1}.")
                new_info = make_request(encode_uid(uid), info_url, token)
                if new_info and new_info.AccountInfo.PlayerNickname:
                    logger.info(f"[LIKE] Successfully fetched updated like count for UID {uid}.")
                    break  # Found a working token, exit loop
            
            if new_info:
                after_likes = new_info.AccountInfo.Likes
            else:
                logger.error(f"[LIKE] Could not fetch updated like count for UID {uid} after trying {len(current_tokens[:5])} tokens.")
                after_likes = before_likes

        return jsonify({
            "player": player_name,
            "uid": uid,
            "likes_added": after_likes - before_likes,
            "likes_before": before_likes,
            "likes_after": after_likes,
            "server_used": region,
            "status": 1 if after_likes > before_likes else 2,
            "credit": "KHAN BHAI"
        })

    except Exception as e:
        logger.error(f"Like error for UID {uid}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "status": 500,
            "credit": "KHAN BHAI"
        }), 500

@like_bp.route("/validate", methods=["GET"])
async def validate_player():
    """
    Checks if a UID is valid and exists on any configured server without sending likes.
    """
    uid = request.args.get("uid")
    if not uid or not uid.isdigit():
        return jsonify({
            "error": "Invalid UID",
            "message": "A valid numeric UID is required as a query parameter.",
            "status": 400,
            "credit": "KHAN BHAI"
        }), 400

    try:
        logger.info(f"[VALIDATE] Starting validation for UID: {uid}")
        region, player_info = await detect_player_region(uid)

        if player_info and region:
            logger.info(f"[VALIDATE] Success: Found UID {uid} ({player_info.AccountInfo.PlayerNickname}) in region {region}.")
            return jsonify({
                "status": "found",
                "message": f"Player '{player_info.AccountInfo.PlayerNickname}' found on the {region} server.",
                "data": {
                    "uid": uid,
                    "nickname": player_info.AccountInfo.PlayerNickname,
                    "region": region
                },
                "credit": "KHAN BHAI"
            }), 200
        else:
            logger.warning(f"[VALIDATE] Failed: UID {uid} not found on any server.")
            return jsonify({
                "status": "not_found",
                "message": f"A player with UID {uid} could not be found on any of the configured servers.",
                "credit": "KHAN BHAI"
            }), 404

    except Exception as e:
        logger.error(f"[VALIDATE] An unexpected error occurred while validating UID {uid}: {e}", exc_info=True)
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please check the server logs.",
            "status": 500,
            "credit": "KHAN BHAI"
        }), 500

@like_bp.route("/health-check", methods=["GET"])
def health_check():
    try:
        token_status = {
            server: len(_token_cache.get_tokens(server)) > 0 
            for server in _SERVERS 
        }

        return jsonify({
            "status": "healthy" if all(token_status.values()) else "degraded",
            "servers": token_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "credit": "KHAN BHAI"
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "credit": "KHAN BHAI"
        }), 500

@like_bp.route("/", methods=["GET"]) 
async def root_home():
    """
    Route pour la page d'accueil principale de l'API (accessible via '/').
    """
    return jsonify({
        "message": "Api free fire like ",
        "credit": "KHAN BHAI",
    })

def initialize_routes(app_instance, servers_config, token_cache_instance):
    global _SERVERS, _token_cache 
    _SERVERS = servers_config
    _token_cache = token_cache_instance
    app_instance.register_blueprint(like_bp)