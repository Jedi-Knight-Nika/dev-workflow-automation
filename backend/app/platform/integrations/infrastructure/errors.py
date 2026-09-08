"""Actionable integration failures without upstream URLs or response bodies."""

import httpx


def connection_error(provider: str, error: Exception) -> str:
    name = {"trello": "Trello", "github": "GitHub", "openai": "OpenAI"}.get(
        provider, provider.title()
    )
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 401:
            if provider == "trello":
                return (
                    "Trello rejected the API key or token. Check both values and use a Trello "
                    "user token, not an Atlassian account API token."
                )
            return f"{name} rejected the credentials. Check the key or token and try again."
        if status == 403:
            return f"{name} denied access. Check the account permissions and token access."
        if status == 429:
            return f"{name} is rate limiting requests. Wait a moment and try again."
        if status >= 500:
            return f"{name} is temporarily unavailable. Try again shortly."
    if isinstance(error, httpx.TimeoutException):
        return f"{name} took too long to respond. Try again shortly."
    if isinstance(error, httpx.RequestError):
        return f"Cannot reach {name}. Check the server network connection and try again."
    if isinstance(error, (TypeError, ValueError)) and provider == "trello":
        return "Enter both a Trello API key and its Trello user token, then try again."
    return f"Could not verify {name}. Check the connection settings and try again."
