import json

import httpx
import pytest

from app.integrations.trello import TrelloClient, parse_trello_credentials, trello_priority


def test_trello_credentials_require_key_and_token() -> None:
    with pytest.raises(ValueError, match="required"):
        parse_trello_credentials(json.dumps({"api_key": "key"}))


@pytest.mark.asyncio
async def test_trello_uses_authorization_header_and_filters_cards() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == (
            'OAuth oauth_consumer_key="key", oauth_token="token"'
        )
        assert "key" not in request.url.params
        assert "token" not in request.url.params
        return httpx.Response(
            200,
            json=[
                {
                    "id": "card-1",
                    "idShort": 1,
                    "shortLink": "abc",
                    "name": "Import me",
                    "desc": "Task details",
                    "idList": "ready",
                    "due": None,
                    "dueComplete": False,
                    "url": "https://trello.test/c/abc",
                    "labels": [{"name": "High"}],
                },
                {"id": "card-2", "name": "Ignore me", "idList": "backlog"},
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cards = await TrelloClient(
            json.dumps({"api_key": "key", "token": "token"}), client
        ).list_cards("board", {"ready"})

    assert [card["id"] for card in cards] == ["card-1"]
    assert trello_priority(cards[0]["labels"]) == 2


@pytest.mark.asyncio
async def test_trello_moves_card_to_workflow_list() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/1/cards/card-1"
        assert request.url.params["idList"] == "in-progress"
        return httpx.Response(200, json={"id": "card-1", "idList": "in-progress"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await TrelloClient(
            json.dumps({"api_key": "key", "token": "token"}), client
        ).update_card_list("card-1", "in-progress")
