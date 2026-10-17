"""Dependencias comunes de FastAPI."""

from typing import Annotated

from fastapi import Depends, Request

from app.foundry import FoundryClient
from app.storage import ProjectRepository
from shared import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> ProjectRepository:
    return request.app.state.repository


def get_foundry(request: Request) -> FoundryClient:
    return request.app.state.foundry


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RepositoryDep = Annotated[ProjectRepository, Depends(get_repository)]
FoundryDep = Annotated[FoundryClient, Depends(get_foundry)]
