from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.api.settings import get_settings

openapi_tags = [
    {
        "name": "video-editor",
        "description": "Video editor domain: projects, media, timeline tracks/clips, trims, transitions, exports.",
    }
]

app = FastAPI(
    title="Modern Video Editor Backend",
    description=(
        "FastAPI backend for a multi-container video editor.\n\n"
        "Key capabilities:\n"
        "- Project CRUD\n"
        "- Media registration + upload stub\n"
        "- Timeline tracks/clips CRUD\n"
        "- Clip trims CRUD\n"
        "- Transitions CRUD\n"
        "- Export jobs + events, with a background export stub\n\n"
        "Real-time updates: this iteration uses polling; see /api/docs/websockets."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=settings.allowed_methods,
    allow_headers=settings.allowed_headers,
    max_age=settings.cors_max_age,
)

app.include_router(api_router)


@app.get("/", tags=["video-editor"], summary="Health Check", description="Simple root health check.", operation_id="health_check_root")
def health_check():
    """Health check entrypoint.

    Returns:
        dict: {"message": "Healthy"} when the service is up.
    """
    return {"message": "Healthy"}
