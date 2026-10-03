from fastapi import APIRouter

router = APIRouter(
    prefix="/tests",
    tags=["Tests"],
)


@router.get("/")
async def get_tests():
    return {"message": "Tests endpoint"}