from fastapi import APIRouter

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.get("/")
async def get_projects():
    return {"message": "Projects endpoint"}