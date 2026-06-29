import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_memory")
DB_PATH = os.getenv("DB_PATH", "user_profile.db")

MAX_THINKING_STEPS = int(os.getenv("MAX_THINKING_STEPS", "5"))
MAX_HISTORY_LENGTH = int(os.getenv("MAX_HISTORY_LENGTH", "40"))
MEMORY_CACHE_TTL = int(os.getenv("MEMORY_CACHE_TTL", "3600"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "北京")

VALID_TOOLS = [
    "get_weather", "get_forecast",
    "query_tasks", "add_task", "complete_task",
    "display_notification",
    "get_clothing_advice",
    "show_profile", "update_profile",
    "web_search"
]