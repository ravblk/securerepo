import os
from typing import Union, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import numpy as np

app = FastAPI()

MODEL_NAME = os.getenv("MODEL_NAME", "BAAI/bge-m3")
DIMENSIONS = 1024  # bge-m3 returns 1024 dimension vectors

model = None


class EmbedRequest(BaseModel):
    inputs: Union[str, List[str]]


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]


@app.on_event("startup")
def load_model():
    global model
    print(f"Loading model: {MODEL_NAME}", flush=True)
    model = SentenceTransformer(MODEL_NAME)
    print(f"Model loaded. Embedding dimension: {DIMENSIONS}", flush=True)


@app.get("/health")
def health():
    return {"status": "healthy", "model": MODEL_NAME, "dimensions": DIMENSIONS}


@app.get("/")
def root():
    return {
        "service": "embedding-service",
        "model": MODEL_NAME,
        "dimensions": DIMENSIONS,
        "capabilities": ["code", "text", "multilingual"]
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    inputs = request.inputs if isinstance(request.inputs, list) else [request.inputs]

    embeddings = model.encode(inputs, convert_to_numpy=True)

    result = embeddings.tolist()

    return {"embeddings": result}
