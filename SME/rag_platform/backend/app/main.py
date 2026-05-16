from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.app_version)

allowed_origins = ['*']
if settings.cors_allowed_origins.strip() != '*':
    allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(',') if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    return {'status': 'ok', 'service': settings.app_name, 'version': settings.app_version}


app.include_router(router, prefix='/api/v1', tags=['rag'])
