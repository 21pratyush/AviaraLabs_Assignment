import os
from fastapi import FastAPI

from app.db.session import engine
from app.db.base import Base
from app.db import models  
from app.db.vector_db import init_collection

from app.api.ingest import router as ingest_router

app = FastAPI(
    title="Contract Intelligence API",
    version="0.1.0",
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Initialize Qdrant collection on startup
    init_collection()
    
app.include_router(ingest_router)

@app.get("/healthz", tags=["admin"])
def health_check():
    return {"status": "ok"}
