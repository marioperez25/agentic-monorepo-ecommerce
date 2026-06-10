from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    description='Returns `{"status": "ok"}` as long as the process is up.',
    response_description="Service is alive.",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
