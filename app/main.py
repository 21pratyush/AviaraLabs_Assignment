from fastapi import FastAPI

app = FastAPI(
    title="Contract Intelligence API",
    version="0.1.0",
)

@app.get("/healthz", tags=["admin"])
def health_check():
    return {"status": "ok"}
