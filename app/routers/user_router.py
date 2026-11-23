from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.dependencies import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserSearchResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/search", response_model=list[UserSearchResponse])
async def search_users(
    q: Annotated[str, Query(min_length=2, max_length=50)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await UserRepository.search_users(
        db=db,
        query=q,
        exclude_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
