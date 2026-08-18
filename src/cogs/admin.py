import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio

from src.config import load_config, save_config
from src.history_manager import load_history, save_history

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Check the bot status")
    async def status_command(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"⚡ Bot is active. Connected as: {self.bot.user}")

    @app_commands.command(name="model", description="View or Change the current LLM model")
    @app_commands.describe(model_name="The name of the model to use (leave empty to view current)")
    async def model_command(self, interaction: discord.Interaction, model_name: str = None):
        from src.main import bot_config
        bot_config = load_config()
        is_localhost = bot_config.get("is_localhost")
        
        if not model_name:
            if not is_localhost:
                current_model = bot_config.get("API_model")
                await interaction.response.send_message(f"📋 Current API LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}")
            else:
                current_model = bot_config.get("local_model")
                await interaction.response.send_message(f"📋 Current localhost LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}")
            return
            
        if not is_localhost:
            bot_config["API_model"] = model_name
            await asyncio.to_thread(save_config, bot_config)
            await interaction.response.send_message(f"✅ Switching API model to: \"{model_name}\"")
        else:
            bot_config["local_model"] = model_name
            await asyncio.to_thread(save_config, bot_config)
            await interaction.response.send_message(f"✅ Switching local model to: \"{model_name}\"")

    @app_commands.command(name="localhost", description="Check or toggle using localhost LLM")
    @app_commands.describe(enabled="True to use localhost, False to use API")
    async def localhost_command(self, interaction: discord.Interaction, enabled: bool = None):
        bot_config = load_config()
        if enabled is None:
            if bot_config.get("is_localhost"):
                await interaction.response.send_message(f"📋 Currently using localhost LLM: {bot_config.get('local_model', {})}")
            else:
                await interaction.response.send_message(f"📋 Currently using API LLM: {bot_config.get('API_model', {})}")
            return
            
        bot_config["is_localhost"] = enabled
        await asyncio.to_thread(save_config, bot_config)
        if enabled:
            await interaction.response.send_message(f"✅ Now using localhost LLM")
        else:
            await interaction.response.send_message(f"✅ Now using API LLM: {bot_config.get('API_model', {})}")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
