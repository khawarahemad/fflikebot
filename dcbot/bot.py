import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import aiohttp
from discord import app_commands
import datetime

# Load .env file
load_dotenv()

# Load credentials from environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APP_ID = os.getenv("DISCORD_APP_ID")
PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
# Support multiple guilds
GUILD_IDS = [1144868481930645566, 1373188942639267902, 1308112085179174994]  # List of allowed guild IDs

# Enable message content intent for prefix commands to work properly
intents = discord.Intents.default()
intents.message_content = True  # <-- Enable this intent

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        try:
            total_synced = 0
            for gid in GUILD_IDS:
                guild = discord.Object(id=gid)
                synced = await self.tree.sync(guild=guild)
                print(f"[setup_hook] Synced {len(synced)} slash commands to guild {gid} (instant registration).")
                total_synced += len(synced)
            print(f"[setup_hook] Total slash commands synced: {total_synced}")
        except Exception as e:
            print(f"[setup_hook] Failed to sync slash commands: {e}")

bot = MyBot(command_prefix="!", intents=intents)

API_BASE = "https://fflikebot-production.up.railway.app"  # Change to your deployed API if needed
INFO_API = "https://api-info-gb.up.railway.app/info?uid={user_id}"
BAN_API = "https://api-check-ban.up.railway.app/check_ban/{user_id}"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"App ID: {APP_ID}")
    print(f"Public Key: {PUBLIC_KEY}")

async def fetch_json(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return {"error": f"API returned status code {resp.status}"}
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            return {"error": f"Network error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

def format_timestamp(timestamp_str):
    try:
        timestamp = int(timestamp_str)
        return f"<t:{timestamp}:F>"
    except:
        return "Unknown"

# ========== LIKE COMMAND ==========
@bot.command(name="like")
async def like_command(ctx, uid: str):
    url = f"{API_BASE}/like?uid={uid}"
    data = await fetch_json(url)
    
    if "error" in data:
        return await ctx.send(f"❌ Error: {data['error']}")
    
    is_success = data.get("status") == 1
    embed = discord.Embed(
        title="Like Added Successfully!" if is_success else "Like Failed",
        color=discord.Color.green() if is_success else discord.Color.red()
    )
    
    embed.add_field(name="Player", value=data.get("player", "Unknown"), inline=True)
    embed.add_field(name="UID", value=data.get("uid", "Unknown"), inline=True)
    embed.add_field(name="Server", value=data.get("server_used", "Unknown"), inline=True)
    embed.add_field(name="Likes Added", value=data.get("likes_added", "Unknown"), inline=True)
    embed.add_field(name="Before", value=data.get("likes_before", "Unknown"), inline=True)
    embed.add_field(name="After", value=data.get("likes_after", "Unknown"), inline=True)
    embed.set_footer(text=f"Credit: {data.get('credit', 'Unknown')}")
    
    # Set GIF image based on result
    if is_success:
        gif_url = "https://raw.githubusercontent.com/khawarahemad/assets/main/success.gif"  # Example public success gif
    else:
        gif_url = "https://raw.githubusercontent.com/khawarahemad/assets/main/failure.gif"  # Example public failure gif
    
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

# ========== VERIFY COMMAND ==========
@bot.command(name="verify")
async def verify_command(ctx, uid: str):
    url = f"{API_BASE}/validate?uid={uid}"
    data = await fetch_json(url)
    
    if "error" in data:
        return await ctx.send(f"❌ Error: {data['error']}")
    
    # Handle not found or error status
    if data.get("status") == "not_found":
        embed = discord.Embed(
            title="Player Not Found",
            description=data.get("message", "No player found for this UID."),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Credit: {data.get('credit', 'Unknown')}")
        return await ctx.send(embed=embed)
    
    # Handle found
    if data.get("status") == "found":
        player = data.get("data", {})
        embed = discord.Embed(
            title="Verification Result",
            color=discord.Color.green()
        )
        embed.add_field(name="Player", value=player.get("nickname", "Unknown"), inline=True)
        embed.add_field(name="UID", value=player.get("uid", "Unknown"), inline=True)
        embed.add_field(name="Region", value=player.get("region", "Unknown"), inline=True)
        embed.add_field(name="Status", value="✅ Found", inline=True)
        embed.add_field(name="Message", value=data.get("message", ""), inline=False)
        embed.set_footer(text=f"Credit: {data.get('credit', 'Unknown')}")
        return await ctx.send(embed=embed)
    
    # Fallback for unexpected response
    await ctx.send(f"❌ Unexpected API response: ```json\n{data}\n```")

# ========== INFO COMMAND ==========
@bot.command(name="info")
async def info_command(ctx, uid: str):
    url = INFO_API.format(user_id=uid)
    data = await fetch_json(url)
    
    if "error" in data:
        return await ctx.send(f"❌ Error: {data['error']}")
    
    basic = data.get("basicInfo", {})
    clan = data.get("clanBasicInfo", {})
    social = data.get("socialInfo", {})
    pet = data.get("petInfo", {})
    
    embed = discord.Embed(
        title=f"Player Info: {basic.get('nickname', 'Unknown')}",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Level", value=basic.get("level", "Unknown"), inline=True)
    embed.add_field(name="Region", value=basic.get("region", "Unknown"), inline=True)
    embed.add_field(name="Rank", value=basic.get("rank", "Unknown"), inline=True)
    embed.add_field(name="Points", value=basic.get("rankingPoints", "Unknown"), inline=True)
    embed.add_field(name="Likes", value=basic.get("liked", "Unknown"), inline=True)
    embed.add_field(name="Created", value=format_timestamp(basic.get("createAt")), inline=True)
    
    if clan:
        embed.add_field(name="Clan", value=f"{clan.get('clanName')} (Lvl {clan.get('clanLevel')})", inline=False)
    
    if pet:
        embed.add_field(name="Pet", value=f"{pet.get('name')} (Lvl {pet.get('level')})", inline=True)
    
    if social.get("signature"):
        embed.add_field(name="Bio", value=social["signature"][:100] + (social["signature"][100:] and '...'), inline=False)
    
    embed.set_footer(text=f"UID: {uid} | Last login: {format_timestamp(basic.get('lastLoginAt'))}")
    await ctx.send(embed=embed)

# ========== BAN CHECK COMMAND ==========
@bot.command(name="checkban")
async def checkban_command(ctx, uid: str):
    url = BAN_API.format(user_id=uid)
    data = await fetch_json(url)
    
    if "error" in data:
        return await ctx.send(f"❌ Error: {data['error']}")
    
    if data.get("status") != 200:
        return await ctx.send(f"❌ API Error: {data.get('msg', 'Unknown error')}")
    
    player_data = data.get("data", {})
    
    embed = discord.Embed(
        title="Ban Check Result",
        color=discord.Color.red() if player_data.get("is_banned") == 1 else discord.Color.green()
    )
    
    embed.add_field(name="Player", value=player_data.get("nickname", "Unknown"), inline=True)
    embed.add_field(name="UID", value=player_data.get("id", "Unknown"), inline=True)
    embed.add_field(name="Region", value=player_data.get("region", "Unknown"), inline=True)
    
    ban_status = "BANNED 🔴" if player_data.get("is_banned") == 1 else "CLEAN ✅"
    ban_details = f"{player_data.get('period')} days" if player_data.get("is_banned") == 1 else "N/A"
    
    embed.add_field(name="Status", value=ban_status, inline=False)
    embed.add_field(name="Ban Duration", value=ban_details, inline=True)
    embed.set_footer(text=f"Credit: {data.get('credit', 'Unknown')}")
    
    await ctx.send(embed=embed)

# ========== PING COMMAND ==========
@bot.command(name="ping")
async def ping_command(ctx):
    """Responds with Pong! and latency for monitoring bot health."""
    latency = round(bot.latency * 1000)  # ms
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.tree.command(name="ping", description="Check if the bot is alive (slash command)")
async def ping_slash_command(interaction: discord.Interaction):
    """Slash command for /ping."""
    latency = round(bot.latency * 1000)  # ms
    await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("DISCORD_BOT_TOKEN is not set in the environment!")
    else:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"Failed to start bot: {e}")