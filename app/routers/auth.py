from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import enforce_rate_limit
from app.database.dependencies import get_db
from app.managers.session_manager import SessionManager
from app.managers.user_manager import UserManager
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse
from app.schemas.session import SessionResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    payload: UserCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await enforce_rate_limit(
        request,
        "register",
        limit=settings.RATE_LIMIT_REGISTER,
    )
    try:
        user = await UserManager.create_user(
            db=db,
            username=payload.username,
            email=str(payload.email),
            password=payload.password,
        )

        return user

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login_user(
    payload: UserLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await enforce_rate_limit(
        request,
        "login-ip",
        limit=settings.RATE_LIMIT_LOGIN,
    )
    await enforce_rate_limit(
        request,
        "login-email",
        identity=str(payload.email).lower(),
        limit=settings.RATE_LIMIT_LOGIN,
    )
    user = await UserManager.authenticate_user(
        db=db,
        email=str(payload.email),
        password=payload.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, refresh_token = await SessionManager.create_session(
        db=db,
        user_id=user.id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh_access_token(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await enforce_rate_limit(
        request,
        "refresh",
        limit=settings.RATE_LIMIT_REFRESH,
    )
    try:
        access_token, refresh_token = await SessionManager.rotate_refresh_token(
            db=db,
            refresh_token=payload.refresh_token,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/logout")
async def logout_user(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await SessionManager.logout(
        db=db,
        refresh_token=payload.refresh_token,
    )

    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all_devices(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    revoked_count = await SessionManager.logout_all(
        db=db,
        user_id=current_user.id,
    )

    return {
        "message": "Logged out from all devices",
        "revoked_sessions": revoked_count,
    }


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
)
async def get_my_sessions(
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await SessionManager.get_user_sessions(
        db=db,
        user_id=current_user.id,
    )


@router.delete("/sessions/{session_id}")
async def revoke_my_session(
    session_id: UUID,
    current_user: Annotated[
        User,
        Depends(get_current_user),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    revoked = await SessionManager.revoke_user_session(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return {"message": "Session revoked successfully"}
