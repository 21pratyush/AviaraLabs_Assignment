import os
from fastapi import FastAPI

from app.db.session import engine
from app.db.base import Base
from app.db import models  
from app.db.vector_db import init_collection

from app.api.ingest import router as document_router
from app.api.retrieval import router as search_router
from app.api.admin import router as admin_router
from app.api.audit import router as analysis_router
from app.api.webhook import router as webhooks_router

app = FastAPI(
    title="Contract Intelligence API",
    version="0.1.0",
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Initialize Qdrant collection on startup
    init_collection()
    
app.include_router(document_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")