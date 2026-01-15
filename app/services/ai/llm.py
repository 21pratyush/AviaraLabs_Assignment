import os
from langchain_google_genai import ChatGoogleGenerativeAI
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions

logger = logging.getLogger(__name__)

def get_gemini():
    return ChatGoogleGenerativeAI(
        model="models/gemini-2.5-flash",
        temperature=0,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )

# This decorator captures specific Gemini quota and service errors
@retry(
    stop=stop_after_attempt(3), # Try up to 3 times
    wait=wait_exponential(multiplier=1, min=4, max=10), # Wait 4s, 8s, 10s...
    retry=retry_if_exception_type((
        exceptions.ResourceExhausted, # Quota/Rate Limit
        exceptions.ServiceUnavailable, # Temporary Server issue
        exceptions.DeadlineExceeded    # Timeout
    )),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying LLM call... Attempt {retry_state.attempt_number}. "
        f"Reason: {retry_state.outcome.exception()}"
    )
)
def call_gemini_with_retry(llm, messages):
    """
    Wraps the LangChain/Gemini invoke call with production-grade 
    retry logic and exponential backoff.
    """
    return llm.invoke(messages)