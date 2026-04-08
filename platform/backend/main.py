from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Bug Daddy API")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Bug Daddy API!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
