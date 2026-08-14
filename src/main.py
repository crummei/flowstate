import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import re
import random as rand
import asyncio
import time

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler()]
)    

import discord # pip install discord.py
from discord.ext import commands

# from groq import AsyncGroq # pip install groq
from openai import AsyncOpenAI, APIConnectionError # pip install openai

from src.history_manager import load_history, save_history
serverData = load_history()

from src.paths import SRC_DIR, DATA_DIR, ENV_PATH
# model_path = os.path.join(DATA_DIR, "kokoro-v1.0.fp16.onnx")
# voices_path = os.path.join(DATA_DIR, "voices-v1.0.bin")

from src.config import load_config, save_config
bot_config = load_config()
account_lists = bot_config.get("account_lists", {})

from dotenv import load_dotenv # python-dotenv
load_dotenv(ENV_PATH)

# llama-3.3-70b-versatile
# llama-3.1-8b-instant

# Has weird <think> Thought </think> prefix
    # deepseek-r1-distill-llama-70b
    # deepseek-r1-distill-qwen-32b

# mistral-saba-24b

active_sessions = {}
last_voice_activity = {}

# Global API Clients to reuse connections
_api_client = None
_local_client = None


from discord import app_commands

class FlowstateBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='*', 
            intents=discord.Intents.all()
        )

    async def setup_hook(self):
        await self.add_cog(AdminCog(self))
        await self.tree.sync()
        self.loop.create_task(terminal_listener(self))
        self.loop.create_task(voice_timeout(self))

bot = FlowstateBot()


# -----------------------------
#       Helper Functions
# -----------------------------

async def get_user_voice_channel(bot: commands.Bot, target_uid: int, message: discord.Message = None):
    # Check if the message was sent in a groupchat
    if message and isinstance(message.channel, discord.GroupChannel):
        return message.channel
        
    # Prioritize the guild where the message was sent
    if message and getattr(message, 'guild', None):
        member = message.guild.get_member(target_uid)
        if member and member.voice and member.voice.channel:
            return member.voice.channel

    # Iterate through all guilds
    for guild in bot.guilds:
        member = guild.get_member(target_uid)
        
        if member and member.voice and member.voice.channel:
            return member.voice.channel
            
    return None

async def voice_timeout(bot):
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        await asyncio.sleep(30) # Run this check every 30 seconds
        
        for vc in list(bot.voice_clients):
            # Guild ID for servers, channel ID for groupchat
            activity_id = vc.guild.id if getattr(vc, 'guild', None) else vc.channel.id
            channel_name = getattr(vc.channel, 'name', 'Group Call') or 'Group Call'
            
            if hasattr(vc.channel, 'members'):
                member_count = len(vc.channel.members)

            elif hasattr(vc.channel, 'voice_states'):
                member_count = len(vc.channel.voice_states)

            else:
                member_count = 2
            
            # If the bot is alone in the channel
            if member_count <= 1:
                logging.info(f"\n🚪 Left {channel_name} (Channel empty)")
                await vc.disconnect()
                last_voice_activity.pop(activity_id, None)
                continue
                
            # If the bot is inactive for 2 minutes
            last_active = last_voice_activity.get(activity_id, time.time())
            if not vc.is_playing() and (time.time() - last_active) > 120:
                logging.info(f"\n🚪 Left {channel_name} (Inactive for 2 minutes)")
                await vc.disconnect()
                last_voice_activity.pop(activity_id, None)

def is_user_in_vc(target_vc, user_id: int) -> bool:
    # Check whether user_id is currently present in target_vc (guild channel or group call)
    user_id = int(user_id)

    if hasattr(target_vc, 'members'):        # Guild voice/stage channel
        return any(m.id == user_id for m in target_vc.members)

    if hasattr(target_vc, 'voice_states'):    # Group DM call
        return user_id in target_vc.voice_states

    return False

async def wait_for_user_in_vc(target_vc, user_id: int, timeout: float = 60, poll_interval: float = 1.0) -> bool:
    # Poll until user_id joins target_vc, or give up after `timeout` seconds
    waited = 0.0

    while waited < timeout:
        if is_user_in_vc(target_vc, user_id):
            return True
        await asyncio.sleep(poll_interval)
        waited += poll_interval

    return is_user_in_vc(target_vc, user_id)

def is_user_in_dict(target_id, data_dict = account_lists):
    for key, value in data_dict.items():
        if key == 'USER_ID' and value == target_id:
            return True
        
        elif isinstance(value, dict):
            if is_user_in_dict(target_id, value):
                return True
            
    return False

def normalize_command(raw: str) -> str:
    parts = raw.split(" ", 1)
    parts[0] = parts[0].lower()
    return " ".join(parts)


# -----------------------------
#            Processing
# -----------------------------

async def process_admin_commands(command):  
    if command.startswith("help"):
        try:
            parts = command.split(" ", 1)
            
            if command.strip() == "help":
                return logging.INFO, f"""
-# Values marked with * are optional.
-# Values inside () show a list of choices.
-# Values inside <> are variables, meant to be filled with the actual data.

> - model | View/Change the current LLM model | Usage: model *<model_name>
> - instruct | View/Change the current instruction set | Usage: instruct (list | add <text> | delete <num> | <num> <text>)
> - history | Delete history for a specific user/server or all | Usage: history delete (all | user <user_id> | server <server_id>)
> - localhost | Check current status or Enable/Disable using localhost LLM | Usage: localhost *<True/False>
"""
# > - tts | Check current status or Enable/Disable joining VC and speaking the response | Usage: tts *<True/False>


            #     elif len(parts) > 1 and parts[1].strip() != "":
                
        #         if not is_localhost:
                    
        #             bot_config["API_MODEL"] = parts[1].strip()
        #             save_config(bot_config)
                
        #             return logging.INFO, f"\n✅ Switching API model to: \"{bot_config.get("API_MODEL", {})}\""
                
        #         else:
                    
        #             bot_config["LOCAL_MODEL"] = parts[1].strip()
        #             save_config(bot_config)
                
        #             return logging.INFO, f"\n✅ Switching local model to: \"{bot_config.get("LOCAL_MODEL", {})}\""
                
        #     else:
        #         return logging.WARNING, "\n❌ Please provide a model name. Usage: model *<model_name>"
        
        # except IndexError:
        #     return logging.WARNING, "\n❌ You are missing the text. Usage: model <text>"
        
        except Exception as e:
            return logging.ERROR, f"\n❌ Something completely unexpected broke: {e}"
    
    if command.startswith("model"):
        try:
            parts = command.split(" ", 1)
            is_localhost = bot_config.get("is_localhost")
            
            if command.strip() == "model":
                if not is_localhost:
                    current_model = bot_config.get("API_MODEL")
                    return logging.INFO, f"\n📋 Current API LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}"
                else:
                    current_model = bot_config.get("LOCAL_MODEL")
                    return logging.INFO, f"\n📋 Current localhost LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}"
                
            elif len(parts) > 1 and parts[1].strip() != "":
                if not is_localhost:
                    
                    bot_config["API_MODEL"] = parts[1].strip()
                    await asyncio.to_thread(save_config, bot_config)
                
                    return logging.INFO, f"\n✅ Switching API model to: \"{bot_config.get("API_MODEL", {})}\""
                
                else:
                    
                    bot_config["LOCAL_MODEL"] = parts[1].strip()
                    await asyncio.to_thread(save_config, bot_config)
                
                    return logging.INFO, f"\n✅ Switching local model to: \"{bot_config.get("LOCAL_MODEL", {})}\""
                
            else:
                return logging.WARNING, "\n❌ Please provide a model name. Usage: model *<model_name>"
        
        except IndexError:
            return logging.WARNING, "\n❌ You are missing the text. Usage: model <text>"
        
        except Exception as e:
            return logging.ERROR, f"\n❌ Something completely unexpected broke: {e}"
        
    elif command.startswith("instruct"):
        try:
            parts = command.split(" ", 2)
            
            if len(parts) > 1 and parts[1].strip() != "":
                
                action = parts[1].strip()
                
                # List all existing instructions
                if action == "list":
                    if "instructions" in bot_config and bot_config["instructions"]:
                        instruction_lines = [
                            f"{index}. {instruction}" 
                            for index, instruction in enumerate(bot_config["instructions"], start=1)
                        ]
                        formatted_list = "\n".join(instruction_lines)
                        return logging.INFO, f"\n📜 Current Instructions:\n{formatted_list}"
                    else:
                        return logging.WARNING, "\n⚠️ There are currently no instructions saved."

                # Experiment, unfinished...
                # if action == "list":
                #     if len(parts) > 2 and parts[2].strip() == "selected":
                #         if "instructions" in bot_config and bot_config["instructions"]:
                #             instruction_lines = [
                #                 f"{index}. {instruction}" 
                #                 for index, instruction in enumerate(bot_config["instructions"], start=1)
                #             ]
                #             formatted_list = "\n".join(instruction_lines)
                #             return logging.INFO, f"\n📜 Current Instructions:\n{formatted_list}"
                #         else:
                #             return logging.WARNING, "\n⚠️ There are currently no instructions saved."
                    
                #     if len(parts) > 2 and parts[2].strip() == "all":
                #         if "instructions" in bot_config and bot_config["instructions"]:
                #             instruction_lines = [
                #                 f"{index}. {instruction}" 
                #                 for index, instruction in enumerate(bot_config["instructions"], start=1)
                #             ]
                #             formatted_list = "\n".join(instruction_lines)
                #             return logging.INFO, f"\n📜 Current Instructions:\n{formatted_list}"
                #         else:
                #             return logging.WARNING, "\n⚠️ There are currently no instructions saved."     
                
                # Delete/remove an instruction
                elif action in {"delete", "remove"}:
                    if len(parts) > 2 and parts[2].strip() != "":
                        try:
                            index_to_remove = int(parts[2].strip()) - 1
                            
                            if "instructions" in bot_config and 0 <= index_to_remove < len(bot_config["instructions"]):
                                removed_value = bot_config["instructions"].pop(index_to_remove)
                                await asyncio.to_thread(save_config, bot_config)
                                return logging.INFO, f"\n🗑️  Removed instruction: Pos. {parts[2].strip()} | {removed_value}"
                            else:
                                return logging.WARNING, f"\n❌ No instruction exists in position: {parts[2].strip()}"
                                
                        except ValueError:
                            return logging.WARNING, f"\n❌ Invalid position number: {parts[2].strip()}"
                    else:
                        return logging.WARNING, "\n❌ Please provide a position number. Usage: instruct delete <number>"

                # Add an additional instruction entry
                elif action == "add":
                    if len(parts) > 2 and parts[2].strip() != "":
                        if "instructions" not in bot_config:
                            bot_config["instructions"] = []
                            
                        # If it loads as a dictionary, convert to list
                        elif isinstance(bot_config["instructions"], dict):
                            bot_config["instructions"] = list(bot_config["instructions"].values())
                            
                        new_instruction = parts[2].strip()
                        bot_config["instructions"].append(new_instruction)
                        await asyncio.to_thread(save_config, bot_config)
                        
                        new_position = len(bot_config["instructions"])
                        return logging.INFO, f"\n✅ Added new instruction at Pos. {new_position}: \"{new_instruction}\""
                        
                    else:
                        return logging.WARNING, "\n❌ Please provide the instruction text. Usage: instruct add <text>"
                 
                # Replace an instruction
                elif action.isdigit():
                    if len(parts) > 2 and parts[2].strip() != "":
                        index_to_replace = int(action) - 1
                        
                        if "instructions" in bot_config and 0 <= index_to_replace < len(bot_config["instructions"]):
                            bot_config["instructions"][index_to_replace] = parts[2].strip()
                            await asyncio.to_thread(save_config, bot_config)
                            return logging.INFO, f"\n✅ Switched instruction {action} to: \"{parts[2].strip()}\""
                        else:
                            return logging.WARNING, f"\n❌ No instruction exists in position: {action}"
                    else:
                        return logging.WARNING, "\n❌ Please provide the replacement text. Usage: instruct <number> <text>"
                
                # Catch-all error
                else:
                    return logging.WARNING, "\n❌ Invalid command. Usage: instruct [list | add <text> | delete <num> | <num> <text>]"
        
        except ValueError:
            return logging.WARNING, "\n❌ That is not a valid number! Please use digits."
        
        except IndexError:
            return logging.WARNING, "\n❌ You are missing the text. Usage: instruct add <text>"
        
        except Exception as e:
            return logging.ERROR, f"\n❌ Something completely unexpected broke: {e}"

    elif command.startswith("history"):
        try:
            parts = command.split(" ", 3)
            
            if len(parts) > 2 and parts[1].strip() in ["delete", "clear"] and parts[2].strip() != "":
                target = parts[2].strip()
                
                if target == "all":
                    serverData["user"].clear()
                    serverData["server"].clear()
                    await asyncio.to_thread(save_history, serverData)
                    
                    return logging.INFO, f"\n✅ Cleared all history!"
                
                elif target in ["user", "server"] and len(parts) > 3 and parts[3].strip() != "":
                    ID = parts[3].strip()
                    
                    if serverData[target].pop(ID, None):
                        await asyncio.to_thread(save_history, serverData)
                    
                        return logging.INFO, f"\n✅ Cleared history for {target}: \"{ID}\""
                    
                    else:
                        return logging.WARNING, f"\n❌ {target.capitalize()} \"{ID}\" doesn't have history. Usage: history delete <all/user/server> *<user_id/server_id>"
                else:
                    return logging.WARNING, "\n❌ Please provide all arguments. Usage: history delete <all/user/server> *<user_id/server_id>"

            else:
                return logging.WARNING, "\n❌ Please provide all arguments. Usage: history delete <all/user/server> *<user_id/server_id>"
        except (KeyError, ValueError):
            return logging.WARNING, "\n❌ Please provide all arguments. Usage: history delete <all/user/server> *<user_id/server_id>"

    elif command == "status":
        return logging.INFO, f"\n⚡ Bot is active. Connected as: {bot.user}\n🔢 Active sessions: {len(active_sessions)}"
    
    elif command.startswith("localhost"):
        try:
            BOOLEAN_TRUE = {"true", "yes", "y", "on"}
            BOOLEAN_FALSE = {"false", "no", "n", "off"}
            parts = command.split(" ", 1)
            
            if command.strip() == "localhost":
                if bot_config.get("is_localhost"):
                    return logging.INFO, f"\n📋 Currently using localhost LLM: {bot_config.get('LOCAL_MODEL', {})}"
                else:
                    return logging.INFO, f"\n📋 Currently using API LLM: {bot_config.get('API_MODEL', {})}"
                
            arg = parts[1].strip().lower() if len(parts) > 1 else ""

            if arg in BOOLEAN_TRUE:
                    bot_config["is_localhost"] = True
                    await asyncio.to_thread(save_config, bot_config)
                    return logging.INFO, f"\n✅ Now using localhost LLM"
            elif arg in BOOLEAN_FALSE:
                    bot_config["is_localhost"] = False
                    await asyncio.to_thread(save_config, bot_config)
                    return logging.INFO, f"\n✅ Now using API LLM: {bot_config.get('API_MODEL', {})}"
            else:
                return logging.WARNING, "\n❌ Please provide all arguments. Usage: localhost *<True/False>"
        except (KeyError, ValueError):
            return logging.WARNING, "\n❌ Please provide all arguments. Usage: localhost *<True/False>"

    elif command.startswith("sync"):
        try:
            parts = command.split(" ", 1)
            if len(parts) > 1 and parts[1].strip():
                server_id = parts[1].strip()
                guild = discord.Object(id=int(server_id))
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                return logging.INFO, f"\n✅ Synced {len(synced)} commands to server ID {server_id}"
            else:
                synced = await bot.tree.sync()
                return logging.INFO, f"\n✅ Synced {len(synced)} commands globally (may take up to an hour to propagate)"
        except Exception as e:
            return logging.ERROR, f"\n❌ Failed to sync: {e}"
    
    # elif command.startswith("tts"):
    #     try:
    #         BOOLEAN_TRUE = {"true", "yes", "y", "on"}
    #         BOOLEAN_FALSE = {"false", "no", "n", "off"}
    #         parts = command.split(" ", 1)
            
    #         if command.strip() == "tts":
    #             return logging.INFO, f"\n📋 TTS is currently {'ON' if bot_config.get('TTS_enabled') else 'OFF'}"

    #         arg = parts[1].strip().lower() if len(parts) > 1 else ""

    #         if arg in BOOLEAN_TRUE:
    #                 bot_config["TTS_enabled"] = True
    #                 await asyncio.to_thread(save_config, bot_config)
    #                 return logging.INFO, f"\n✅ TTS has been enabled"
    #         elif arg in BOOLEAN_FALSE:
    #                 bot_config["TTS_enabled"] = False
    #                 await asyncio.to_thread(save_config, bot_config)
    #                 return logging.INFO, f"\n✅ TTS has been disabled"

    #         else:
    #             return logging.WARNING, f"\n❌ Please provide all arguments. Usage: tts *<True/False>"
    #     except (KeyError, ValueError):
    #         return logging.WARNING, f"\n❌ Please provide all arguments. Usage: tts *<True/False>"
        
    elif command != "":
        return logging.WARNING, f"\n🤨 Unknown command: {command}"

async def terminal_listener(bot):
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            user_input = await asyncio.to_thread(input)
            command = normalize_command(user_input.strip())
            
            result = await process_admin_commands(command)
            
            match result:
                case (level, message):
                    # If it returns a tuple
                    log_level, log_message = level, message
                    
                case message if isinstance(message, str):
                    # If it returns just a string
                    log_level = logging.INFO
                    log_message = message
                    
                case None:
                    continue 
                    
                case _:
                    log_level = logging.WARNING
                    log_message = f"Command returned an unexpected format: {result}"

            # This will now only execute if log_level and log_message were actually set
            logging.log(log_level, log_message)
                
        except asyncio.CancelledError:
            break
        
        except Exception as e:
            logging.error(f"\n❗ Terminal listener error: {e}")


# -----------------------------
#     Response Generation
# -----------------------------

async def AIprompt(user_message, allPrompts, allResponses, is_reply_to_bot=False, reference_msg=None):
    global bot_config, _api_client, _local_client
    bot_config = load_config()
    is_localhost = bot_config.get("is_localhost")

    # Get and validate model
    if not is_localhost:
        AIprompt.model = bot_config.get("API_MODEL", None)
        
        if AIprompt.model is None:
            raise ValueError("No API model has been set. Use 'model <model_name>' to set one.")
            
        if _api_client is None:
            _api_client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ.get("OPENROUTER_API_KEY")
            )
        chatClient = _api_client
        
    else:
        AIprompt.model = bot_config.get("LOCAL_MODEL", None)
        
        if AIprompt.model is None:
            raise ValueError("No local model has been set. Use 'model <model_name>' to set one.")
        
        if _local_client is None:
            local_ip = os.environ.get("LM_STUDIO_IP", "127.0.0.1")
            _local_client = AsyncOpenAI(
                base_url=f"http://{local_ip}:1234/v1",
                api_key="lm-studio"
            )
        chatClient = _local_client
    
    # Build full prompt
    messages = []
    
    if bot_config.get("instructions"):
        combined_instructions = "\n".join(bot_config["instructions"])

        if combined_instructions.strip():
            messages.append({
                'role': 'system',
                'content': combined_instructions,
            })
    
    past_prompts = allPrompts[-3:]
    past_responses = allResponses[-3:]
    
    for p, r in zip(past_prompts, past_responses):
        messages.append({'role': 'user', 'content': p})
        messages.append({'role': 'assistant', 'content': r})

    if is_reply_to_bot and reference_msg is not None and reference_msg.content not in past_responses:
        messages.append({
            'role': 'assistant',
            'content': reference_msg.content
        })

    messages.append({
        'role': 'user',
        'content': user_message
    })
    
    # Start chatCompletion with STREAMING ENABLED
    response_stream = await chatClient.chat.completions.create(
        model=AIprompt.model,
        temperature=0.6,
        messages=messages,
        stream=True,
    )
    
    in_think_tag = False
    is_thinking = True 
    buffer = ""

    async for chunk in response_stream:
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        buffer += delta

        if is_thinking:
            if not in_think_tag and "<think>" in buffer:
                in_think_tag = True

            if "</think>" in buffer:
                _, clean_text = buffer.split("</think>", 1)
                buffer = clean_text.lstrip()
                is_thinking = False
            elif not in_think_tag and len(buffer) > 1:
                is_thinking = False

        if not is_thinking:
            if buffer:
                yield buffer
                buffer = ""


# -----------------------------
#       Discord Events
# -----------------------------

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ask", description="Ask Flowstate a question")
    @app_commands.describe(question="Your question")
    async def ask_command(self, interaction: discord.Interaction, question: str):
        if not question:
            await interaction.response.send_message("Please provide a question.")
            return

        await interaction.response.defer()
        
        userID = str(interaction.user.id)
        
        # Initialize user data if it doesn't exist
        if userID not in serverData["user"]:
            logging.info(f"Initializing data for {userID}")
            serverData["user"][userID] = {
                'allPrompts': [],
                'allResponses': [],
            }

        allPrompts = serverData["user"][userID]['allPrompts']
        allResponses = serverData["user"][userID]['allResponses']

        response = ""
        try:
            stream = AIprompt(question, allPrompts, allResponses)
            async for chunk in stream:
                response += chunk
        except Exception as e:
            logging.error(f"Error generating AI response: {e}")
            await interaction.followup.send(f"❌ Error generating response: {e}")
            return

        if not response:
            await interaction.followup.send("AI returned an empty response.")
            return

        # Cap message length for Discord limits (2000 chars max)
        if len(response) > 2000:
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)
        
        logging.info(f"""
==========================
User:
{question}

Response:
{response}
==========================""")
        allPrompts.append(question)
        allResponses.append(response)
        
        # Cap history to prevent memory leaks
        MAX_HISTORY = 50
        if len(allPrompts) > MAX_HISTORY:
            allPrompts[:] = allPrompts[-MAX_HISTORY:]
            allResponses[:] = allResponses[-MAX_HISTORY:]
            
        await asyncio.to_thread(save_history, serverData)

    @app_commands.command(name="status", description="Check the bot status")
    async def status_command(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"⚡ Bot is active. Connected as: {self.bot.user}")

    @app_commands.command(name="sync", description="Sync slash commands to a specific server, or globally if blank")
    @app_commands.describe(server_id="The ID of the server to sync to (leave blank for global sync)")
    @app_commands.default_permissions(administrator=True)
    async def sync_command(self, interaction: discord.Interaction, server_id: str = None):
        await interaction.response.defer()
        try:
            if server_id:
                guild = discord.Object(id=int(server_id))
                self.bot.tree.copy_global_to(guild=guild)
                synced = await self.bot.tree.sync(guild=guild)
                await interaction.followup.send(f"✅ Synced {len(synced)} commands to server ID {server_id}")
            else:
                synced = await self.bot.tree.sync()
                await interaction.followup.send(f"✅ Synced {len(synced)} commands globally (may take up to an hour to propagate)")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to sync: {e}")

    @app_commands.command(name="model", description="View or Change the current LLM model")
    @app_commands.describe(model_name="The name of the model to use (leave empty to view current)")
    @app_commands.default_permissions(administrator=True)
    async def model_command(self, interaction: discord.Interaction, model_name: str = None):
        await interaction.response.defer(ephemeral=True)
        is_localhost = bot_config.get("is_localhost")
        
        if not model_name:
            if not is_localhost:
                current_model = bot_config.get("API_MODEL")
                await interaction.followup.send(f"📋 Current API LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}")
            else:
                current_model = bot_config.get("LOCAL_MODEL")
                await interaction.followup.send(f"📋 Current localhost LLM: {f'\"{current_model}\"' if current_model else 'None (Not Set)'}")
            return
            
        if not is_localhost:
            bot_config["API_MODEL"] = model_name
            await asyncio.to_thread(save_config, bot_config)
            await interaction.followup.send(f"✅ Switching API model to: \"{model_name}\"")
        else:
            bot_config["LOCAL_MODEL"] = model_name
            await asyncio.to_thread(save_config, bot_config)
            await interaction.followup.send(f"✅ Switching local model to: \"{model_name}\"")

    @app_commands.command(name="localhost", description="Check or toggle using localhost LLM")
    @app_commands.describe(enabled="True to use localhost, False to use API")
    @app_commands.default_permissions(administrator=True)
    async def localhost_command(self, interaction: discord.Interaction, enabled: bool = None):
        await interaction.response.defer(ephemeral=True)
        if enabled is None:
            if bot_config.get("is_localhost"):
                await interaction.followup.send(f"📋 Currently using localhost LLM: {bot_config.get('LOCAL_MODEL', {})}")
            else:
                await interaction.followup.send(f"📋 Currently using API LLM: {bot_config.get('API_MODEL', {})}")
            return
            
        bot_config["is_localhost"] = enabled
        await asyncio.to_thread(save_config, bot_config)
        if enabled:
            await interaction.followup.send(f"✅ Now using localhost LLM")
        else:
            await interaction.followup.send(f"✅ Now using API LLM: {bot_config.get('API_MODEL', {})}")

# -----------------------------
#         Misc. Start
# -----------------------------

# kokoro = Kokoro(model_path, voices_path)
# Kokoro.audiofile = os.path.join(DATA_DIR, "output.wav")

bot.run(os.getenv('BOT_TOKEN'))
