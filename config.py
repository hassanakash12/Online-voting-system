import os
from dotenv import load_dotenv

# Loads variables from a local .env file (never commit .env to git)
load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "ai_online_voting_system")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
