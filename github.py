# Made by TFX | @visualtfx on all platforms
# this bot contains upload analysation, image generation, and AI ability

import discord
from discord import app_commands # Required for slash commands
from discord.ext import commands
import os
import json
import asyncio # For deferring responses
import aiohttp # For making HTTP requests to Gemini API
import base64 # For encoding images for Gemini Vision (used in /aiupload)
from googleapiclient.discovery import build # For Google Search
import io # For handling image bytes for discord.File
import time # For retry mechanism
import random # For jitter in retry mechanism

# --- Configuration ---
# It's highly recommended to use environment variables for sensitive keys
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE") # Replace with your bot token
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")    # Used for Gemini text, Vision, and Imagen

# --- Google Search Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_GOOGLE_API_KEY_FOR_SEARCH_HERE") # Replace if different from GEMINI_API_KEY
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "YOUR_GOOGLE_CSE_ID_HERE")

# File for guild conversation histories
GUILD_CONVERSATION_HISTORY_FILE = "conversation_histories.json"
DM_HISTORY_DIR = "dm_histories"
if not os.path.exists(DM_HISTORY_DIR):
    os.makedirs(DM_HISTORY_DIR)

# --- Permission Configuration ---
# These IDs are no longer strictly enforced by can_use_command if it always returns True,
# but are kept here for potential future use or if other logic might use them.
# Replace with your own IDs if you intend to use them for specific permission logic.
SPECIAL_USER_ID = 0 # Example: 123456789012345678
TARGET_GUILD_ID = 0 # Example: 987654321098765432
TARGET_CHANNEL_ID = 0 # Example: 112233445566778899

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Conversation History Management ---
guild_conversation_histories = {}
dm_conversation_histories = {}

def load_guild_conversation_histories():
    """Loads guild conversation histories from the JSON file."""
    global guild_conversation_histories
    try:
        if os.path.exists(GUILD_CONVERSATION_HISTORY_FILE):
            with open(GUILD_CONVERSATION_HISTORY_FILE, 'r') as f:
                guild_conversation_histories = json.load(f)
                # Ensure keys are integers after loading
                guild_conversation_histories = {int(k): v for k, v in guild_conversation_histories.items()}
        else:
            guild_conversation_histories = {}
    except json.JSONDecodeError:
        print(f"Error decoding {GUILD_CONVERSATION_HISTORY_FILE}. Starting with empty histories.")
        guild_conversation_histories = {}

def save_guild_conversation_histories():
    """Saves guild conversation histories to the JSON file."""
    with open(GUILD_CONVERSATION_HISTORY_FILE, 'w') as f:
        json.dump(guild_conversation_histories, f, indent=4)

def load_dm_conversation_history(user_id):
    """Loads a DM conversation history for a specific user."""
    filepath = os.path.join(DM_HISTORY_DIR, f"{user_id}.json")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return []
    except json.JSONDecodeError:
        print(f"Error decoding DM history for user {user_id}. Starting fresh.")
        return []

def save_dm_conversation_history(user_id, history):
    """Saves a DM conversation history for a specific user."""
    filepath = os.path.join(DM_HISTORY_DIR, f"{user_id}.json")
    with open(filepath, 'w') as f:
        json.dump(history, f, indent=4)

def get_user_dm_history(user_id):
    """Gets or initializes DM history for a user."""
    if user_id not in dm_conversation_histories:
        dm_conversation_histories[user_id] = load_dm_conversation_history(user_id)
    return dm_conversation_histories[user_id]

def add_to_conversation_history(message_content, role, guild_id=None, user_id=None, is_dm=False):
    """Adds a message to the appropriate conversation history."""
    history_entry = {"role": role, "parts": [{"text": message_content}]}

    if is_dm and user_id:
        history = get_user_dm_history(user_id)
        history.append(history_entry)
        if len(history) > 40: # Keep history to last 40 entries
            history = history[-40:]
        dm_conversation_histories[user_id] = history
        save_dm_conversation_history(user_id, history)
    elif guild_id:
        if guild_id not in guild_conversation_histories:
            guild_conversation_histories[guild_id] = []
        guild_conversation_histories[guild_id].append(history_entry)
        if len(guild_conversation_histories[guild_id]) > 40: # Keep history to last 40 entries
            guild_conversation_histories[guild_id] = guild_conversation_histories[guild_id][-40:]
        save_guild_conversation_histories()

def get_conversation_history(guild_id=None, user_id=None, is_dm=False):
    """Retrieves the conversation history."""
    if is_dm and user_id:
        return get_user_dm_history(user_id)
    elif guild_id:
        return guild_conversation_histories.get(guild_id, [])
    return []

# --- Google Search Function ---
async def search_google(query: str, num_results: int = 3) -> str | None:
    """Performs a Google search using the Custom Search API."""
    if not query or not query.strip():
        return "Search query was empty."
    if not GOOGLE_CSE_ID or GOOGLE_CSE_ID == "YOUR_GOOGLE_CSE_ID_HERE":
        print("Google CSE ID is not configured. Skipping search.")
        return "Search is not configured by the bot owner."
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY_FOR_SEARCH_HERE": # Ensure this placeholder matches
        print("Google API Key for Search is not configured. Skipping search.")
        return "Search API key is not configured by the bot owner."

    try:
        service = await asyncio.to_thread(build, "customsearch", "v1", developerKey=GOOGLE_API_KEY)
        result = await asyncio.to_thread(
            service.cse().list(q=query, cx=GOOGLE_CSE_ID, num=num_results).execute
        )
        items = result.get('items', [])
        if not items:
            return "No relevant search results found."
        search_results_str = ""
        for i, item in enumerate(items):
            title = item.get('title', 'N/A')
            snippet = item.get('snippet', 'N/A').replace('\n', ' ')
            link = item.get('link', '#')
            search_results_str += f"{i+1}. {title}: {snippet} (Source: {link})\n"
        return search_results_str.strip()
    except Exception as e:
        print(f"Google Search API error: {e}")
        return f"An error occurred while trying to search: {str(e)[:200]}"

# --- Gemini API Interaction ---
async def get_ai_response(original_prompt: str, perform_search: bool, guild_id=None, user_id=None, is_dm=False) -> str:
    """Gets a response from the Gemini API, optionally performing a web search first."""
    # UPDATED MODEL TO gemini-2.5-pro-preview-05-06
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-preview-05-06:generateContent?key={GEMINI_API_KEY}"
    
    current_turn_user_text = original_prompt
    if perform_search and original_prompt and original_prompt.strip():
        print(f"Performing search for: {original_prompt}")
        search_results_output = await search_google(original_prompt)
        if search_results_output:
            if search_results_output.startswith("No relevant search results found."):
                current_turn_user_text = f"I searched for '{original_prompt}' but found no relevant results. Please answer based on your general knowledge: {original_prompt}"
            elif search_results_output.startswith(("Search is not configured", "Search API key is not configured", "An error occurred", "Search query was empty")):
                current_turn_user_text = f"Regarding your request for '{original_prompt}': I encountered an issue with web search ('{search_results_output}'). Please answer based on your general knowledge: {original_prompt}"
            else:
                current_turn_user_text = f"Web Search Results:\n{search_results_output}\n\nBased on these results, please answer: {original_prompt}"
    
    add_to_conversation_history(current_turn_user_text, "user", guild_id, user_id, is_dm)
    conversation_history = get_conversation_history(guild_id, user_id, is_dm)

    payload = {
        "contents": conversation_history,
        "generationConfig": {"temperature": 0.7, "topK": 1, "topP": 1, "maxOutputTokens": 8192},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("candidates") and data["candidates"][0].get("content", {}).get("parts"):
                    ai_response_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    add_to_conversation_history(ai_response_text, "model", guild_id, user_id, is_dm)
                    return ai_response_text
                elif data.get("promptFeedback", {}).get("blockReason"):
                    return f"I couldn't generate a response because the prompt was blocked. Reason: {data['promptFeedback']['blockReason']}."
                else:
                    print(f"Unexpected Gemini API response structure: {data}")
                    return "Sorry, I received an unexpected response from the AI. No content found."
        except aiohttp.ClientResponseError as e:
            # FIXED AttributeError: 'ClientResponseError' object has no attribute 'text'
            print(f"HTTP error calling Gemini API: {e.status} {e.message}")
            print(f"URL: {e.request_info.url}") # Log the URL that was called
            print(f"Headers: {e.headers}") # Log response headers if needed
            # e.message usually contains the server's error message for 4xx/5xx
            return f"Sorry, I encountered an error trying to reach the AI service (HTTP {e.status}: {e.message}). Please check the model name and API key."
        except Exception as e:
            print(f"Error in get_ai_response: {e}")
            return "Sorry, an unexpected error occurred."

async def get_multimodal_ai_response(image_bytes: bytes, image_content_type: str, text_prompt: str = None, perform_search: bool = False) -> str:
    """Gets a response from Gemini Vision API, with optional search."""
    # UPDATED MODEL TO gemini-2.5-pro-preview-05-06
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-preview-05-06:generateContent?key={GEMINI_API_KEY}"

    final_text_prompt_for_llm = text_prompt if text_prompt and text_prompt.strip() else "Describe this image."

    if perform_search and text_prompt and text_prompt.strip():
        print(f"Performing search for (multimodal): {text_prompt}")
        search_results_output = await search_google(text_prompt)
        if search_results_output:
            if search_results_output.startswith("No relevant search results found."):
                final_text_prompt_for_llm = f"I searched for '{text_prompt}' (related to the image) but found no relevant results. Please respond based on the image and your general knowledge: {text_prompt if text_prompt else 'Describe the image.'}"
            elif search_results_output.startswith(("Search is not configured", "Search API key is not configured", "An error occurred", "Search query was empty")):
                final_text_prompt_for_llm = f"Regarding your text '{text_prompt}' (related to the image): I encountered an issue with web search ('{search_results_output}'). Please respond based on the image and your general knowledge: {text_prompt if text_prompt else 'Describe the image.'}"
            else:
                final_text_prompt_for_llm = f"Web Search Results:\n{search_results_output}\n\nBased on these search results and the image, please respond to: {text_prompt}"
    
    parts = [{"inline_data": {"mime_type": image_content_type, "data": base64.b64encode(image_bytes).decode('utf-8')}}]
    parts.insert(0, {"text": final_text_prompt_for_llm})
    
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.4, "topK": 32, "topP": 1, "maxOutputTokens": 4096},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("candidates") and data["candidates"][0].get("content", {}).get("parts"):
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                elif data.get("promptFeedback", {}).get("blockReason"):
                    return f"Image analysis blocked. Reason: {data['promptFeedback']['blockReason']}."
                else:
                    print(f"Unexpected Gemini Vision API response structure: {data}")
                    return "Sorry, I received an unexpected response from the AI for the image."
        except aiohttp.ClientResponseError as e:
            # FIXED AttributeError
            print(f"HTTP error calling Gemini Vision API: {e.status} {e.message}")
            print(f"URL: {e.request_info.url}")
            print(f"Headers: {e.headers}")
            return f"Sorry, I encountered an error trying to reach the AI vision service (HTTP {e.status}: {e.message})."
        except Exception as e:
            print(f"Error in get_multimodal_ai_response: {e}")
            return "Sorry, an unexpected error occurred with image processing."

# --- Imagen API Interaction (Image Generation) with Retries ---
async def generate_image_from_prompt(
    prompt: str, 
    max_retries: int = 3, 
    backoff_factor: float = 1.0
) -> str | None:
    """
    Generates an image using Imagen 3 model with retries and exponential backoff.
    Returns base64 encoded string or an error message string.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("Error: Gemini API Key for Imagen is not configured.")
        return "Image generation failed: API Key not configured."

    # Using the generativelanguage.googleapis.com endpoint for Imagen as per original user code structure.
    # Ensure GEMINI_API_KEY is authorized for imagen-3.0-generate-002 via this endpoint.
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GEMINI_API_KEY}"

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1}
    }

    for attempt in range(max_retries):
        print(f"Attempt {attempt + 1} of {max_retries} to generate image for prompt: \"{prompt[:50]}...\"")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(api_url, json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()

                    if data.get("predictions") and len(data["predictions"]) > 0 and data["predictions"][0].get("bytesBase64Encoded"):
                        print("Image generated successfully.")
                        return data["predictions"][0]["bytesBase64Encoded"]
                    else:
                        error_detail = "No image data in response."
                        if data.get("error", {}).get("message"):
                            error_detail = data["error"]["message"]
                        elif data.get("promptFeedback", {}).get("blockReason"):
                            block_reason = data['promptFeedback']['blockReason']
                            print(f"Imagen API blocked prompt. Reason: {block_reason}")
                            return f"Image generation blocked. Reason: {block_reason}"
                        
                        print(f"Imagen API did not return image data on attempt {attempt + 1}. Details: {error_detail}")
                        if "No image data in response" in error_detail and attempt < max_retries - 1:
                            pass
                        elif attempt == max_retries -1:
                             return f"Failed to generate image after {max_retries} attempts: {error_detail}"

            except aiohttp.ClientResponseError as e:
                error_message_text = f"HTTP error calling Imagen API on attempt {attempt + 1}: {e.status} {e.message}"
                try:
                    # For aiohttp.ClientResponseError, e.message often contains the server's text
                    # If you need the full response body for debugging, you'd typically read it *before* raise_for_status
                    # or catch it and then read. Here, we'll rely on e.message.
                    print(f"{error_message_text} - URL: {e.request_info.url}")
                except Exception as e_detail:
                    print(f"{error_message_text} (could not get further details: {e_detail})")

                if attempt == max_retries - 1:
                    return f"Failed to generate image due to API error after {max_retries} attempts: {e.status} {e.message}"
            except Exception as e:
                print(f"Unexpected error in generate_image_from_prompt (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return f"Sorry, an unexpected error occurred during image generation after {max_retries} attempts."

            if attempt < max_retries - 1:
                delay = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                print(f"Waiting {delay:.2f} seconds before next retry...")
                await asyncio.sleep(delay)
            else:
                print(f"All {max_retries} retries failed for prompt: \"{prompt[:50]}...\"")
    
    return f"Failed to generate image after {max_retries} attempts. Please check logs."

# --- Bot Events ---
@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors from slash commands."""
    try:
        if isinstance(error, app_commands.CommandOnCooldown):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"You are on cooldown. Try again in {error.retry_after:.1f} seconds.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"You are on cooldown. Try again in {error.retry_after:.1f} seconds.",
                    ephemeral=True
                )
            return
        
        error_message_str = str(error)
        print(f"Unhandled command error: {error_message_str}")
        print(f"Error type: {type(error)}")
        
        user_error_message = "An unexpected error occurred with that command."
        
        if hasattr(error, 'original'):
            original_error = error.original
            if isinstance(original_error, aiohttp.ClientResponseError):
                user_error_message = f"The AI service returned an error: {original_error.status} - {original_error.message}. Please try again later or check the model configuration."
            else:
                 user_error_message = f"An internal error occurred: {str(original_error)[:100]}" # Show first 100 chars of original error
        else: # If no 'original' attribute, use the string representation of the error itself.
            user_error_message = f"An error occurred: {error_message_str[:150]}"


        if not interaction.response.is_done():
            await interaction.response.send_message(user_error_message, ephemeral=True)
        else:
            await interaction.followup.send(user_error_message, ephemeral=True)

    except Exception as e_handler:
        print(f"Error in on_application_command_error handler itself: {e_handler}")
        try:
            # Fallback message
            fallback_msg = "An error occurred processing your command and handling the error."
            if not interaction.response.is_done():
                await interaction.response.send_message(fallback_msg, ephemeral=True)
            else:
                await interaction.followup.send(fallback_msg, ephemeral=True)
        except discord.errors.InteractionResponded:
             pass 
        except Exception:
            pass

@bot.event
async def on_ready():
    """Event that runs when the bot is ready and connected to Discord."""
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    load_guild_conversation_histories()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

# --- Helper for Permission Check ---
def can_use_command(interaction: discord.Interaction) -> bool:
    """Checks if the user has permission to use the command. (No restrictions)"""
    # Example:
    # if interaction.user.id == SPECIAL_USER_ID:
    #     return True
    # if interaction.guild and interaction.guild.id == TARGET_GUILD_ID:
    #     if interaction.channel and interaction.channel.id == TARGET_CHANNEL_ID:
    #         return True
    #     # Allow in any channel of target guild if channel not specified for restriction
    #     # return True 
    # return False # Or True if you want to allow by default
    return True # Currently allows everyone

# --- Slash Commands ---
# Define your cooldown bypass user IDs here. Example: [12345, 67890]
COOLDOWN_BYPASS_USER_IDS = [0] # Replace 0 with actual user IDs or leave empty if not needed

@bot.tree.command(name="ai", description="Chat with Gemini 2.5 Pro. Optionally, enable web search.")
@app_commands.describe(prompt="Your message or query for the AI.", search="Set to True to allow the AI to search the web based on your prompt.")
@app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id) if i.user.id not in COOLDOWN_BYPASS_USER_IDS else None)
async def ai_command(interaction: discord.Interaction, prompt: str, search: bool = False):
    """Handles the /ai slash command."""
    if not can_use_command(interaction):
        await interaction.response.send_message("Sorry, you don't have permission to use this command here.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    is_dm_context = interaction.guild is None
    guild_id_context = interaction.guild.id if interaction.guild else None
    user_id_context = interaction.user.id

    ai_response = await get_ai_response(prompt, search, guild_id_context, user_id_context, is_dm_context)

    embed = discord.Embed(title="AI Response (Gemini 2.5 Pro)", color=discord.Color.orange())
    embed.add_field(name="You Asked", value=prompt if len(prompt) < 1024 else prompt[:1020]+"...", inline=False)
    
    first_chunk_max_len = 1020 
    response_first_chunk = ai_response[:first_chunk_max_len]
    if len(ai_response) > first_chunk_max_len:
        response_first_chunk += "..."
    
    embed.add_field(name="AI Says", value=response_first_chunk if response_first_chunk else "(No response)", inline=False)
    embed.set_footer(text=f"Made by @visualtfx <3 | Interacting with: {interaction.user.display_name} | Model: gemini-2.5-pro-preview-05-06 | Search: {'Enabled' if search else 'Disabled'}")
    
    await interaction.followup.send(embed=embed)

    if len(ai_response) > first_chunk_max_len:
        remaining_response = ai_response[first_chunk_max_len:]
        for i in range(0, len(remaining_response), 1980): 
            chunk = remaining_response[i:i+1980]
            await interaction.followup.send(content=chunk)


@bot.tree.command(name="aiupload", description="Send an image (and optional text) to Gemini 2.5 Pro. Optionally enable web search.")
@app_commands.describe(image="Upload an image for the AI to see.", text="Optional text or question about the image. This will be searched if 'search' is True.", search="Set to True to search the web based on your 'text' field content.")
@app_commands.checks.cooldown(1, 15.0, key=lambda i: (i.guild_id, i.user.id) if i.user.id not in COOLDOWN_BYPASS_USER_IDS else None)
async def aiupload_command(interaction: discord.Interaction, image: discord.Attachment, text: str = None, search: bool = False):
    """Handles the /aiupload slash command for multimodal input."""
    if not can_use_command(interaction):
        await interaction.response.send_message("Sorry, you don't have permission to use this command here.", ephemeral=True)
        return

    if not image.content_type or not image.content_type.startswith('image/'):
        await interaction.response.send_message("Please upload a valid image file (e.g., PNG, JPG, GIF).", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    if search and (not text or not text.strip()):
        await interaction.followup.send("To use web search with an image, please also provide some text for the search query in the 'text' field.", ephemeral=True)
        return

    search_status_footer_text = "Disabled"
    if search and text and text.strip(): search_status_footer_text = "Enabled"
        
    processing_message_embed = discord.Embed(title="AI Vision Processing (Gemini 2.5 Pro)...", description="The AI is looking at your image. This might take a moment.", color=discord.Color.orange())
    if image.url: processing_message_embed.set_thumbnail(url=image.url)
    processing_message_embed.set_footer(text=f"Made by @visualtfx <3 | Requested by: {interaction.user.display_name} | Model: gemini-2.5-pro-preview-05-06 | Search: {search_status_footer_text}")
    
    processing_message_handle = await interaction.followup.send(embed=processing_message_embed)

    try:
        image_bytes = await image.read()
    except Exception as e:
        print(f"Error reading attachment: {e}")
        error_embed = discord.Embed(title="Error", description="Sorry, I couldn't read the uploaded image file.", color=discord.Color.red())
        error_embed.set_footer(text="Made by @visualtfx <3")
        await processing_message_handle.edit(embed=error_embed)
        return

    ai_vision_response = await get_multimodal_ai_response(image_bytes, image.content_type, text, search)

    reply_embed = discord.Embed(title="AI Vision Response (Gemini 2.5 Pro)", color=discord.Color.orange())
    if text:
        reply_embed.add_field(name="Your Question/Text", value=text if len(text) < 1024 else text[:1020]+"...", inline=False)
    
    first_chunk_max_len = 1020
    response_first_chunk = ai_vision_response[:first_chunk_max_len]
    if len(ai_vision_response) > first_chunk_max_len:
        response_first_chunk += "..."
        
    reply_embed.add_field(name="AI's Response", value=response_first_chunk if response_first_chunk else "(No text response generated)", inline=False)
    
    if image.url: reply_embed.set_image(url=image.url) 
    reply_embed.set_footer(text=f"Made by @visualtfx <3 | Processed for: {interaction.user.display_name} | Model: gemini-2.5-pro-preview-05-06 | Search: {search_status_footer_text}")

    await processing_message_handle.edit(embed=reply_embed)

    if len(ai_vision_response) > first_chunk_max_len:
        remaining_response = ai_vision_response[first_chunk_max_len:]
        for i in range(0, len(remaining_response), 1980):
            chunk = remaining_response[i:i+1980]
            await interaction.followup.send(content=chunk)


@bot.tree.command(name="generateimage", description="Generates an image based on your prompt using AI (Imagen 3).")
@app_commands.checks.cooldown(1, 45.0, key=lambda i: (i.guild_id, i.user.id) if i.user.id not in COOLDOWN_BYPASS_USER_IDS else None)
async def generateimage_command(interaction: discord.Interaction, prompt: str):
    """Handles the /generateimage slash command."""
    if not can_use_command(interaction):
        await interaction.response.send_message("Sorry, you don't have permission to use this command here.", ephemeral=True)
        return

    if not prompt or not prompt.strip():
        await interaction.response.send_message("Please provide a prompt to generate an image.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    generating_embed = discord.Embed(
        title="🎨 Image Generation in Progress (Imagen 3)...",
        description=f"Requesting an image for: \"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\"",
        color=discord.Color.light_grey()
    )
    generating_embed.set_footer(text=f"Made by @visualtfx <3 | Requested by: {interaction.user.display_name}")
    status_message = await interaction.followup.send(embed=generating_embed)

    base64_image_data_or_error_msg = await generate_image_from_prompt(prompt, max_retries=3, backoff_factor=1.0)

    if base64_image_data_or_error_msg:
        if base64_image_data_or_error_msg.startswith(("Failed to generate image:", "Image generation failed:", "Image generation blocked.", "Sorry, an unexpected error occurred")):
            error_embed = discord.Embed(title="Image Generation Failed", description=base64_image_data_or_error_msg, color=discord.Color.red())
            error_embed.set_footer(text=f"Made by @visualtfx <3 | Attempted prompt by {interaction.user.display_name}: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
            await status_message.edit(embed=error_embed)
            return

        try:
            image_bytes = base64.b64decode(base64_image_data_or_error_msg)
            image_file_obj = io.BytesIO(image_bytes)
            discord_image_file = discord.File(fp=image_file_obj, filename="generated_image.png")

            embed = discord.Embed(title="🖼️ Image Generated! (Imagen 3)", color=discord.Color.orange())
            embed.set_image(url="attachment://generated_image.png")
            embed.add_field(name="Prompt", value=prompt if len(prompt) < 1024 else prompt[:1020]+"...", inline=False)
            embed.set_footer(text=f"Made by @visualtfx <3 | Generated for: {interaction.user.display_name}")

            await status_message.edit(embed=embed, attachments=[discord_image_file])
        except Exception as e:
            print(f"Error decoding or sending image: {e}")
            error_embed = discord.Embed(title="Image Display Error", description="Could not decode or display the generated image.", color=discord.Color.red())
            error_embed.set_footer(text="Made by @visualtfx <3")
            await status_message.edit(embed=error_embed)
    else:
        error_embed = discord.Embed(title="Image Generation Failed", description="No image data was returned from the AI, and no specific error message was provided.", color=discord.Color.red())
        error_embed.set_footer(text="Made by @visualtfx <3")
        await status_message.edit(embed=error_embed)


@bot.tree.command(name="resetai", description="Resets your conversation history with the AI.")
async def resetai_command(interaction: discord.Interaction):
    """Handles the /resetai slash command."""
    if not can_use_command(interaction):
        await interaction.response.send_message("Sorry, you don't have permission to use this command here.", ephemeral=True)
        return

    is_dm_context = interaction.guild is None
    user_id_context = interaction.user.id
    guild_id_context = interaction.guild.id if interaction.guild else None

    confirmation_message = ""
    if is_dm_context:
        if user_id_context in dm_conversation_histories and dm_conversation_histories[user_id_context]:
            dm_conversation_histories[user_id_context] = []
            save_dm_conversation_history(user_id_context, [])
            confirmation_message = "Your DM conversation history with the AI has been reset."
        else:
            confirmation_message = "You have no DM conversation history with the AI to reset."
    else:
        if guild_id_context in guild_conversation_histories and guild_conversation_histories[guild_id_context]:
            guild_conversation_histories[guild_id_context] = []
            save_guild_conversation_histories()
            confirmation_message = f"The conversation history for this server ({interaction.guild.name}) with the AI has been reset."
        else:
            confirmation_message = f"There is no conversation history for this server ({interaction.guild.name}) with the AI to reset."
    
    await interaction.response.send_message(confirmation_message, ephemeral=True)

# --- Main Execution ---
if __name__ == "__main__":
    # Basic check for placeholder tokens/keys
    if DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE" or \
       GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE" or \
       GOOGLE_API_KEY == "YOUR_GOOGLE_API_KEY_FOR_SEARCH_HERE" or \
       GOOGLE_CSE_ID == "YOUR_GOOGLE_CSE_ID_HERE":
        print("ERROR: Bot token, API keys, or Google CSE ID might not be correctly configured.")
        print("Please replace placeholder values (like 'YOUR_DISCORD_BOT_TOKEN_HERE') in the script,")
        print("or ensure they are set as environment variables and accessible by the script's environment.")
        print("The script will not run with placeholder values.")
    else:
        bot.run(DISCORD_BOT_TOKEN)
