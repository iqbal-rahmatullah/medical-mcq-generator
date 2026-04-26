import logging

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.config import settings

root_logger = logging.getLogger()
if not root_logger.handlers:
    logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.project_name)

app.include_router(api_router)
