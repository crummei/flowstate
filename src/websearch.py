import os
import httpx
import logging

try:
    from tavily import AsyncTavilyClient, UsageLimitExceededError
except ImportError:
    AsyncTavilyClient = None
    UsageLimitExceededError = Exception

async def get_search_query(user_message: str, client, is_localhost: bool, past_prompts: list = None, past_responses: list = None) -> str | None:
    # Asks a small free model to extract key components for a web search from the user_message.
    # Returns the extracted search query string.
    past_context = ""
    if past_prompts and past_responses:
        past_context = "Conversation History:\n"
        for p, r in zip(past_prompts, past_responses):
            past_context += f"User: {p}\nAssistant: {r}\n"
            
    prompt = (
        "Determine if the user's latest message requires a web search to answer accurately (e.g., looking up current facts, stats, or specific settings). "
        "If a search is needed, generate an optimal web search query. "
        "Make sure the search is related to the game 'Rocket League' when applicable. "
        "If the user is just conversing, asking for clarification on previous points, or if no search is needed, reply exactly with the word 'NONE'.\n"
        "Reply ONLY with the search query, or 'NONE'. Do not include quotes or any other text.\n\n"
    )
    if past_context:
        prompt += f"{past_context}\n"
        
    prompt += f"Latest User message: {user_message}"

    try:
        # For localhost, we might just use whatever model is currently loaded.
        # But for API, we use the free llama-3.1-8b-instruct
        model = "meta-llama/llama-3.1-8b-instruct" if not is_localhost else getattr(client, "model", None)
        
        # Some local clients might ignore the model parameter, but we'll pass it.
        # We need to make sure we handle it gracefully if localhost model is not specified properly.
        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 50
        }
        if model:
            kwargs["model"] = model

        response = await client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content.strip()
        
        # If the model wraps the output in think tags (e.g., deepseek), we should clean it
        if "</think>" in result:
            _, clean_text = result.split("</think>", 1)
            result = clean_text.strip()
            
        # Strip any surrounding quotes the model might have added
        result = result.strip('"\'')
        logging.info(f"Websearch: {result}")
        
        if result.upper() == "NONE":
            return None

        return result
    except Exception as e:
        logging.error(f"Error determining search query: {e}")
        return None

async def serper_search(query: str) -> str:
    """
    Fallback search using Google Serper API.
    """
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return "Serper API key not found."

    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    payload = {"q": query}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Format the output similar to tavily
            results = []
            if "organic" in data:
                for item in data["organic"][:5]: # Take top 5
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    link = item.get("link", "")
                    results.append(f"Title: {title}\nSnippet: {snippet}\nSource: {link}\n")
            
            if not results:
                return "No search results found."
            return "\n".join(results)
    except Exception as e:
        logging.error(f"Serper search failed: {e}")
        return f"Web search failed: {e}"

async def perform_web_search(query: str) -> str:
    """
    Performs a web search using Tavily.
    Falls back to Serper if UsageLimitExceededError is raised.
    """
    if not AsyncTavilyClient:
        logging.warning("tavily-python not installed, falling back to Serper.")
        return await serper_search(query)

    tavily_api_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_api_key:
        logging.warning("TAVILY_API_KEY not found, attempting Serper fallback.")
        return await serper_search(query)

    try:
        client = AsyncTavilyClient(api_key=tavily_api_key)
        # Using basic search, returning top 5 results
        response = await client.search(query=query, search_depth="basic", max_results=5)
        
        results = []
        for result in response.get("results", []):
            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")
            results.append(f"Title: {title}\nContent: {content}\nSource: {url}\n")
            
        if not results:
            return "No search results found."
        return "\n".join(results)
        
    except UsageLimitExceededError:
        logging.warning("Tavily usage limit exceeded, falling back to Serper.")
        return await serper_search(query)
    except Exception as e:
        logging.error(f"Tavily search failed with unexpected error: {e}, attempting Serper fallback.")
        return await serper_search(query)
