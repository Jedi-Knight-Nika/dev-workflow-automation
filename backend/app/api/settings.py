from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.application.manage_settings import ManageAccountSettings
from app.application.ports.account_settings import AccountSettingsStore
from app.bootstrap.dependencies import get_account_settings_store
from app.schemas.settings import SETTINGS_SECTION_SCHEMAS

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(
    store: AccountSettingsStore = Depends(get_account_settings_store),
) -> dict[str, Any]:
    return await ManageAccountSettings(store).get()


@router.patch("/{section}")
async def update_settings(
    section: str,
    body: dict[str, Any],
    store: AccountSettingsStore = Depends(get_account_settings_store),
) -> dict[str, Any]:
    schema = SETTINGS_SECTION_SCHEMAS.get(section)
    if schema is None:
        raise HTTPException(status_code=404, detail="Settings section not found")
    try:
        values = schema.model_validate(body).model_dump(mode="json")
        return await ManageAccountSettings(store).update(section, values)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False),
        ) from exc
