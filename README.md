Made by TFX | @visualtfx on Discord
If you need any support, don't hesitate to contact me on there.

Setup Guide

Prepare Project Files:
If you have a git repository link: git clone <your-repository-link> cd <your-repository-directory>
If you downloaded files: Place them in a new project directory.
Create a Virtual Environment (Recommended):
python -m venv venv

Activate the Virtual Environment:
On Linux/macOS: source venv/bin/activate
On Windows: venv\Scripts\activate

Install Dependencies:
Create a file named requirements.txt in your project directory with the following content:
discord.py
google-api-python-client
aiohttp
Run the command: pip install -r requirements.txt
Configure API Keys & Tokens:

Recommended Method (Environment Variables): Set the following environment variables in your system:
DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_FOR_SEARCH_HERE" (can be the same as GEMINI_API_KEY if applicable)
GOOGLE_CSE_ID="YOUR_GOOGLE_CSE_ID_HERE"

Alternative Method (Edit ff.py - Not for public repositories): Open ff.py and find these lines, then replace the placeholder strings with your actual keys:
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_GOOGLE_API_KEY_FOR_SEARCH_HERE")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "YOUR_GOOGLE_CSE_ID_HERE")
Optional: Configure Bot Settings (Edit ff.py):

To set user IDs that bypass command cooldowns, find and edit this line in ff.py: COOLDOWN_BYPASS_USER_IDS = [0] (Replace 0 with actual user IDs, e.g., [123456789012345678, 987654321098765432])
If you plan to use specific permission logic, you can update SPECIAL_USER_ID, TARGET_GUILD_ID, and TARGET_CHANNEL_ID in ff.py.
Running the Bot

Execute the Main Script:
Open your terminal or command prompt (ensure your virtual environment is active if you created one) and run:
python ff.py

Invite Bot to Discord Server:

Go to the Discord Developer Portal, select your bot's application.
Go to the "OAuth2" > "URL Generator" section.
Select the bot and applications.commands scopes.
Under "Bot Permissions," select "Send Messages," "Read Message History," "Embed Links," and "Attach Files" (and any others you deem necessary, like "Administrator" for simplicity if it's your own server).
Copy the generated URL and paste it into your web browser. Select the server you want to add the bot to and authorize it.
