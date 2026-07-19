"""
API de raccourcissement d'URL — volontairement simple.

Le but de ce projet n'est pas la complexité de l'application (3 routes
suffisent), mais tout ce qu'on construit AUTOUR : conteneurisation,
déploiement Kubernetes, CI/CD, supervision. Voir le README du repo.
"""
import string
import random
import sqlite3
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

DB_PATH = "urls.db"
ALPHABET = string.ascii_letters + string.digits


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                code TEXT PRIMARY KEY,
                target_url TEXT NOT NULL,
                clicks INTEGER NOT NULL DEFAULT 0
            )
        """)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(ALPHABET, k=length))


app = FastAPI(title="URL Shortener", version="1.0.0")

# Expose /metrics au format Prometheus (requêtes, latence, codes de statut...)
Instrumentator().instrument(app).expose(app)


class ShortenRequest(BaseModel):
    url: str


class ShortenResponse(BaseModel):
    code: str
    short_url: str


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    """Utilisé par Kubernetes (liveness/readiness probes)."""
    return {"status": "ok"}


@app.post("/shorten", response_model=ShortenResponse)
def shorten(req: ShortenRequest):
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="L'URL doit commencer par http:// ou https://")

    code = generate_code()
    with get_db() as conn:
        # Évite (de façon simple) les collisions de code
        while conn.execute("SELECT 1 FROM urls WHERE code = ?", (code,)).fetchone():
            code = generate_code()
        conn.execute(
            "INSERT INTO urls (code, target_url, clicks) VALUES (?, ?, 0)",
            (code, req.url),
        )
        conn.commit()

    return ShortenResponse(code=code, short_url=f"/{code}")


@app.get("/stats/{code}")
def stats(code: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT target_url, clicks FROM urls WHERE code = ?", (code,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Code inconnu")
    return {"code": code, "target_url": row[0], "clicks": row[1]}


@app.get("/{code}")
def redirect(code: str):
    with get_db() as conn:
        row = conn.execute("SELECT target_url FROM urls WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Code inconnu")
        conn.execute("UPDATE urls SET clicks = clicks + 1 WHERE code = ?", (code,))
        conn.commit()
    return RedirectResponse(url=row[0])
