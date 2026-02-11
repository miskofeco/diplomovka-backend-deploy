import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
FACT_CHECK_MODEL = os.getenv("OPENAI_FACT_CHECK_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
CLIENT = OpenAI(api_key=API_KEY)
