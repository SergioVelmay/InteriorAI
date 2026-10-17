"""Dependencias comunes de FastAPI."""

from typing import Annotated

from fastapi import Depends, Request

from app.storage import ProjectRepository
from shared import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> ProjectRepository:
    return request.app.state.repository


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RepositoryDep = Annotated[ProjectRepository, Depends(get_repository)]
