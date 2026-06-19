import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env.local")

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

MODEL_PATH = str(BASE_DIR / "mobilenet_v2_plant_disease")

QWEN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
