import json
from datetime import datetime
from typing import Any, TypedDict

import httpx


class TrelloBoard(TypedDict):
    id: str
    name: str
    url: str


class TrelloList(TypedDict):
    id: str
    name: str
    closed: bool


class TrelloCard(TypedDict):
    id: str
    id_short: int
    short_link: str
    name: str
    description: str
    list_id: str
    due: str | None
    due_complete: bool
    url: str
    labels: list[dict[str, Any]]
    raw: dict[str, Any]


class TrelloCredentials(TypedDict):
    api_key: str
    token: str


def parse_trello_credentials(value: str) -> TrelloCredentials:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Trello credentials must contain an API key and token") from exc
    if not isinstance(parsed, dict):
        raise TypeError("Trello credentials must contain an API key and token")
    api_key = str(parsed.get("api_key") or "").strip()
    token = str(parsed.get("token") or "").strip()
    if not api_key or not token:
        raise ValueError("Trello API key and token are required")
    return TrelloCredentials(api_key=api_key, token=token)


class TrelloClient:
    def __init__(self, credential: str, client: httpx.AsyncClient | None = None) -> None:
        credentials = parse_trello_credentials(credential)
        self._authorization = (
            'OAuth oauth_consumer_key="'
            + credentials["api_key"]
            + '", oauth_token="'
            + credentials["token"]
            + '"'
        )
        self._client = client

    async def _get(self, path: str, **params: str) -> object:
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            response = await client.get(
                f"https://api.trello.com/1{path}",
                headers={"Authorization": self._authorization, "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            return response.json()
        finally:
            if self._client is None:
                await client.aclose()

    async def list_boards(self) -> list[TrelloBoard]:
        payload = await self._get("/members/me/boards", fields="id,name,url", filter="open")
        if not isinstance(payload, list):
            raise TypeError("Trello returned an invalid board list")
        return [
            TrelloBoard(id=str(item["id"]), name=str(item["name"]), url=str(item["url"]))
            for item in payload
            if isinstance(item, dict) and item.get("id") and item.get("name")
        ]

    async def list_lists(self, board_id: str) -> list[TrelloList]:
        payload = await self._get(
            f"/boards/{board_id}/lists", fields="id,name,closed", filter="open"
        )
        if not isinstance(payload, list):
            raise TypeError("Trello returned an invalid list collection")
        return [
            TrelloList(
                id=str(item["id"]),
                name=str(item["name"]),
                closed=bool(item.get("closed", False)),
            )
            for item in payload
            if isinstance(item, dict) and item.get("id") and item.get("name")
        ]

    async def list_cards(self, board_id: str, list_ids: set[str]) -> list[TrelloCard]:
        payload = await self._get(
            f"/boards/{board_id}/cards",
            fields="id,idShort,shortLink,name,desc,idList,due,dueComplete,url,labels",
        )
        if not isinstance(payload, list):
            raise TypeError("Trello returned an invalid card collection")
        cards: list[TrelloCard] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("id") or not item.get("idList"):
                continue
            list_id = str(item["idList"])
            if list_ids and list_id not in list_ids:
                continue
            cards.append(
                TrelloCard(
                    id=str(item["id"]),
                    id_short=int(item.get("idShort") or 0),
                    short_link=str(item.get("shortLink") or item["id"]),
                    name=str(item.get("name") or "Untitled Trello card"),
                    description=str(item.get("desc") or ""),
                    list_id=list_id,
                    due=str(item["due"]) if item.get("due") else None,
                    due_complete=bool(item.get("dueComplete", False)),
                    url=str(item.get("url") or ""),
                    labels=list(item.get("labels") or []),
                    raw=dict(item),
                )
            )
        return cards


def trello_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def trello_priority(labels: list[dict[str, Any]]) -> int:
    text = " ".join(str(label.get("name") or "").casefold() for label in labels)
    if any(value in text for value in ("urgent", "critical", "p0")):
        return 1
    if any(value in text for value in ("high", "p1")):
        return 2
    if any(value in text for value in ("low", "p3")):
        return 4
    return 3
