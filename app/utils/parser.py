from typing import Any

## utility function to truncate large document text for LLM context window optimization
def smart_truncate(text: str, max_chars: int = 40000) -> str:
    """Take first 25k and last 15k characters for large documents to stay in context."""
    if len(text) <= max_chars:
        return text
    head = text[:25000]
    tail = text[-15000:]
    return f"{head}\n\n[... TEXT TRUNCATED FOR CONTEXT LIMITS ...]\n\n{tail}"

## util function to parse JSON from Gemini response
def parse_json_garbage(text: str) -> Any:
    """
    Improved helper to clean Gemini's markdown backticks and find JSON.
    Supports both JSON Objects {} and JSON Lists [].
    """
    import re, json
    # Search for either [...] or {...}
    # [ \t\r\n]* allows for leading whitespace inside the match
    json_match = re.search(r'(\[.*\]|\{.*\})', text.strip(), re.DOTALL)
    
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            # Fallback: try to strip markdown code blocks manually if regex was too greedy
            clean_text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
            
    raise json.JSONDecodeError("No JSON found in LLM response", text, 0)
