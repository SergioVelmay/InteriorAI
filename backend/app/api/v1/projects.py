"""Proyectos: un espacio de la casa cada uno."""

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.api.deps import RepositoryDep
from shared.models import ProjectCreate, ProjectMetadata, ProjectSummary, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["proyectos"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectMetadata)
async def create_project(
    data: ProjectCreate, repo: RepositoryDep, request: Request, response: Response
) -> ProjectMetadata:
    project = await repo.create(data)
    response.headers["Location"] = str(request.url_for("get_project", project_id=project.id))
    return project


@router.get("", response_model=list[ProjectSummary])
async def list_projects(repo: RepositoryDep) -> list[ProjectSummary]:
    return await repo.list_projects()


@router.get("/{project_id}", response_model=ProjectMetadata, name="get_project")
async def get_project(project_id: UUID, repo: RepositoryDep) -> ProjectMetadata:
    return await repo.get(project_id)


@router.patch("/{project_id}", response_model=ProjectMetadata)
async def update_project(
    project_id: UUID, changes: ProjectUpdate, repo: RepositoryDep
) -> ProjectMetadata:
    return await repo.update(project_id, changes)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, repo: RepositoryDep) -> Response:
    """Borrado suave: el proyecto se mueve a `data/.papelera/`."""
    await repo.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
