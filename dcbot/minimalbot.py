import os
from dotenv import load_dotenv
import discord

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = 1144868481930645566

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        @self.tree.command(name="ping", description="Ping test", guild=guild)
        async def ping(interaction: discord.Interaction):
            await interaction.response.send_message("Pong!")
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} slash commands to guild {GUILD_ID} (minimal test).")

bot = MyBot()
bot.run(TOKEN)