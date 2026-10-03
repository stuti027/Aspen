from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get("/status")
async def auth_status():
    return {"message": "Authentication endpoint"}