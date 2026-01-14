import os
from langchain_google_genai import ChatGoogleGenerativeAI


def get_gemini():
    return ChatGoogleGenerativeAI(
        model="models/gemini-2.5-flash",
        temperature=0,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
