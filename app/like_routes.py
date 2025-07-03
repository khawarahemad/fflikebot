from flask import Blueprint, request, jsonify, current_app
import asyncio
from datetime import datetime, timezone
import logging
import aiohttp 
import requests 
import time
import os
import random


from .utils.protobuf_utils import encode_uid, decode_info, create_protobuf 
from .utils.crypto_utils import encrypt_aes
from .utils.http_utils import get_headers

logger = logging.getLogger(__name__)

like_bp = Blueprint('like_bp', __name__)


_SERVERS = {}
_token_cache = None

# Add this at the top or near other config
AUTO_LIKE_UIDS = [
    "1689677011",
    "804459982",
    "1654843293",
    # ...
]

async def async_post_request(url: str, data: bytes, token: str, device_profile: dict = None):
    try:
        headers = get_headers(token, device_profile)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=10) as resp:
                return await resp.read()
    except Exception as e:
        logger.error(f"Async request failed: {str(e)}")
        return None

def make_request(uid_enc: str, url: str, token: str, device_profile: dict = None):
    data = bytes.fromhex(uid_enc)
    headers = get_headers(token, device_profile)
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

def generate_device_profile(batch_num):
    # Generate a unique device profile for each batch
    android_versions = ["9", "10", "11", "12"]
    device_models = ["ASUS_Z01QD", "SM-G973F", "Redmi Note 8", "Pixel 4", "OnePlus 7T"]
    build_ids = ["PI", "RQ3A.210805.001.A1", "QP1A.190711.020", "RKQ1.200710.002"]
    user_agent = f"Dalvik/2.1.0 (Linux; U; Android {random.choice(android_versions)}; {random.choice(device_models)} Build/{random.choice(build_ids)})"
    return {
        'User-Agent': user_agent,
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': f"v1 {batch_num}",
        'ReleaseVersion': "OB49"
    }

async def send_likes(uid: str, region: str):
    tokens = _token_cache.get_tokens(region)
    like_url = f"{_SERVERS[region]}/LikeProfile"
    encrypted = encrypt_aes(create_protobuf(uid, region))

    batch_size = 100
    total_sent = 0
    total_success = 0
    results = []
    failed_tokens = []

    # Prepare all batches and their device profiles
    batches = [tokens[i:i+batch_size] for i in range(0, len(tokens), batch_size)]
    batch_device_profiles = [generate_device_profile(i) for i in range(len(batches))]

    # Launch all batches in parallel
    async def run_batch(batch, device_profile):
        tasks = [async_post_request(like_url, bytes.fromhex(encrypted), token, device_profile) for token in batch]
        return await asyncio.gather(*tasks)

    batch_results_list = await asyncio.gather(*[run_batch(batch, batch_device_profiles[i]) for i, batch in enumerate(batches)])

    # Flatten results and process
    for batch_idx, batch_results in enumerate(batch_results_list):
        batch = batches[batch_idx]
        for idx, result in enumerate(batch_results):
            token = batch[idx]
            if result is not None:
                logger.info(f"[LIKE] Token success: {token[:8]}... for UID {uid}")
                total_success += 1
            else:
                logger.warning(f"[LIKE] Token failed: {token[:8]}... for UID {uid}")
                failed_tokens.append(token)
        total_sent += len(batch_results)
        results.extend(batch_results)

    # Retry failed tokens once after all batches
    if failed_tokens:
        logger.info(f"[LIKE] Retrying {len(failed_tokens)} failed tokens for UID {uid} after 2 seconds...")
        await asyncio.sleep(2)
        retry_device_profile = generate_device_profile(9999)
        retry_tasks = [async_post_request(like_url, bytes.fromhex(encrypted), token, retry_device_profile) for token in failed_tokens]
        retry_results = await asyncio.gather(*retry_tasks)
        for idx, result in enumerate(retry_results):
            token = failed_tokens[idx]
            if result is not None:
                logger.info(f"[LIKE][RETRY] Token success: {token[:8]}... for UID {uid}")
                total_success += 1
            else:
                logger.warning(f"[LIKE][RETRY] Token failed: {token[:8]}... for UID {uid}")
        total_sent += len(retry_results)
        results.extend(retry_results)

    return {
        'sent': total_sent,
        'added': total_success
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

        # Extra logging: how many tokens are being used
        tokens_used = _token_cache.get_tokens(region)
        logger.info(f"[LIKE] Using {len(tokens_used)} tokens for region {region} to send likes to UID {uid}.")

        send_result = await send_likes(uid, region)
        logger.info(f"[LIKE] send_likes result for UID {uid}: sent={send_result['sent']}, added={send_result['added']}.")

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
            "tokens_used": len(tokens_used),
            "likes_sent": send_result['sent'],
            "likes_success": send_result['added'],
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

@like_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "message": "pong"})

@like_bp.route("/validate-tokens", methods=["GET"])
def validate_tokens_endpoint():
    region = request.args.get("region")
    uid = request.args.get("uid")
    if not region or not uid:
        return jsonify({"error": "region and uid are required as query parameters."}), 400
    try:
        info_url = f"{_SERVERS[region]}/GetPlayerPersonalShow"
        uid_enc = encode_uid(uid)
        tokens = _token_cache.get_tokens(region)
        valid = 0
        invalid = 0
        errors = 0
        async def check_tokens():
            nonlocal valid, invalid, errors
            for token in tokens:
                try:
                    resp = await async_post_request(info_url, bytes.fromhex(uid_enc), token)
                    if resp:
                        valid += 1
                    else:
                        invalid += 1
                except Exception as e:
                    errors += 1
        asyncio.run(check_tokens())
        return jsonify({
            "region": region,
            "uid": uid,
            "total_tokens": len(tokens),
            "valid_tokens": valid,
            "invalid_tokens": invalid,
            "error_tokens": errors
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@like_bp.route("/reload-tokens", methods=["GET"])
def reload_tokens_endpoint():
    try:
        # Clear all tokens from memory
        _token_cache.cache.clear()
        _token_cache.last_refresh.clear()
        
        # Force refresh tokens from config for all regions
        for region in _SERVERS:
            _token_cache._refresh_tokens(region)
            _token_cache.last_refresh[region] = time.time()
        
        # Get token counts for response
        token_counts = {}
        for region in _SERVERS:
            tokens = _token_cache.get_tokens(region)
            token_counts[region] = len(tokens)
        
        # Send notification to Discord Webhook on success
        webhook_url = os.getenv("DISCORD_LOG_WEBHOOK")
        if webhook_url:
            try:
                embed = {
                    "title": "✅ Token Refresh Successful",
                    "description": "All tokens have been forcefully reloaded from the configuration files.",
                    "color": 0x2ECC71,  # Green
                    "fields": [
                        {"name": f"🌐 {region}", "value": f"**{count}** tokens loaded", "inline": True}
                        for region, count in token_counts.items()
                    ],
                    "footer": {"text": "Report generated at"},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
                logger.info("[WEBHOOK] Successfully sent token reload report to Discord.")
                # Trigger auto-like after reload
                autolike_embed = {
                    "title": "🤖 Auto-like Triggered!",
                    "description": f"Auto-like has been triggered for {len(AUTO_LIKE_UIDS)} UIDs after token reload.",
                    "color": 0x3498DB,
                    "footer": {"text": "Auto-like started at"},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                requests.post(webhook_url, json={"embeds": [autolike_embed]}, timeout=10)
                # Run auto-like worker in background
                import threading
                threading.Thread(target=lambda: asyncio.run(_autolike_worker(AUTO_LIKE_UIDS))).start()
            except Exception as e:
                logger.error(f"[WEBHOOK] Failed to send success notification or trigger autolike: {e}")

        return jsonify({
            "message": "Tokens refreshed from config successfully",
            "token_counts": token_counts,
            "credit": "KHAN BHAI"
        })
    except Exception as e:
        logger.error(f"Failed to reload tokens: {e}", exc_info=True)
        # Send failure notification to Discord Webhook
        webhook_url = os.getenv("DISCORD_LOG_WEBHOOK")
        if webhook_url:
            try:
                embed = {
                    "title": "❌ Token Refresh Failed",
                    "description": f"An error occurred during token refresh: ```{str(e)}```",
                    "color": 0xE74C3C,  # Red
                    "footer": {"text": "Error report generated at"},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
            except Exception as hook_e:
                logger.error(f"[WEBHOOK] Also failed to send error report to Discord: {hook_e}")

        return jsonify({
            "error": "Failed to reload tokens",
            "message": str(e),
            "credit": "KHAN BHAI"
        }), 500

@like_bp.route("/autolike", methods=["POST"])
def autolike_endpoint():
    try:
        # Accept UIDs as JSON array or comma-separated string
        data = request.get_json(force=True, silent=True) or {}
        uids = data.get("uids")
        if not uids:
            uids = request.args.get("uids")
        if not uids:
            return jsonify({"error": "No UIDs provided. Send as JSON array in 'uids' or as comma-separated string in 'uids' param."}), 400
        if isinstance(uids, str):
            uid_list = [u.strip() for u in uids.split(",") if u.strip()]
        else:
            uid_list = [str(u).strip() for u in uids if str(u).strip()]
        if not uid_list:
            return jsonify({"error": "No valid UIDs found."}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(_autolike_worker(uid_list))
        loop.close()

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def _autolike_worker(uid_list):
    webhook_url = os.getenv("DISCORD_LOG_WEBHOOK")
    success = []
    failed = []
    for uid in uid_list:
        # Simulate a GET request to /like for each UID
        try:
            with current_app.test_request_context(f"/like?uid={uid}"):
                resp = await like_player()
                if isinstance(resp, tuple):
                    data = resp[0].json
                else:
                    data = resp.json
                # Ensure all fields are present for webhook reporting
                result = {
                    "uid": data.get("uid", uid),
                    "player": data.get("player", "?"),
                    "likes_added": data.get("likes_added", 0),
                    "likes_before": data.get("likes_before", 0),
                    "likes_after": data.get("likes_after", 0),
                    "server_used": data.get("server_used", "?"),
                    "status": data.get("status", 0),
                    "error": data.get("error")
                }
                if result["likes_added"] > 0:
                    success.append(result)
                else:
                    # Try to fetch player info for failed likes to fill in player/likes fields
                    try:
                        region, player_info = await detect_player_region(uid)
                        if player_info:
                            result["player"] = getattr(player_info.AccountInfo, "PlayerNickname", "?")
                            result["likes_before"] = getattr(player_info.AccountInfo, "Likes", 0)
                            result["likes_after"] = getattr(player_info.AccountInfo, "Likes", 0)
                            result["server_used"] = region or "?"
                    except Exception:
                        pass
                    failed.append(result)
        except Exception as e:
            # Try to fetch player info for failed likes to fill in player/likes fields
            result = {
                "uid": uid,
                "player": "?",
                "likes_added": 0,
                "likes_before": 0,
                "likes_after": 0,
                "server_used": "?",
                "status": 0,
                "error": str(e)
            }
            try:
                region, player_info = await detect_player_region(uid)
                if player_info:
                    result["player"] = getattr(player_info.AccountInfo, "PlayerNickname", "?")
                    result["likes_before"] = getattr(player_info.AccountInfo, "Likes", 0)
                    result["likes_after"] = getattr(player_info.AccountInfo, "Likes", 0)
                    result["server_used"] = region or "?"
            except Exception:
                pass
            failed.append(result)
        await asyncio.sleep(3)
    # Prepare webhook message
    if webhook_url:
        try:
            desc = ""
            if success:
                desc += "✅ **Success:**\n"
                for d in success:
                    desc += f"- UID: `{d['uid']}` | Player: `{d['player']}` | Likes Added: `{d['likes_added']}` (Before: {d['likes_before']}, After: {d['likes_after']})\n"
            if failed:
                desc += "\n❌ **No Likes Added:**\n"
                for d in failed:
                    desc += f"- UID: `{d['uid']}` | Player: `{d['player']}` | Likes Added: `{d['likes_added']}` (Before: {d['likes_before']}, After: {d['likes_after']})\n"
            embed = {
                "title": "🤖 Auto-like Complete!",
                "description": desc or "No results.",
                "color": 0x3498DB,
                "footer": {"text": "Auto-like finished"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        except Exception as e:
            logger.error(f"[WEBHOOK] Failed to send autolike summary: {e}")
    return {"success": success, "failed": failed}

def initialize_routes(app_instance, servers_config, token_cache_instance):
    global _SERVERS, _token_cache 
    _SERVERS = servers_config
    _token_cache = token_cache_instance
    app_instance.register_blueprint(like_bp)