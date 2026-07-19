# --- Étape 1 : installation des dépendances ---
FROM python:3.12-slim AS builder

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Étape 2 : image finale, allégée ---
FROM python:3.12-slim

WORKDIR /app

# Utilisateur non-root — bonne pratique de sécurité en conteneur
RUN useradd --create-home appuser
COPY --from=builder /root/.local /home/appuser/.local
COPY app/main.py .

# Le dossier /app doit appartenir à appuser, sinon SQLite ne peut pas
# créer son fichier de base de données (erreur "unable to open database file")
RUN chown -R appuser:appuser /app

ENV PATH=/home/appuser/.local/bin:$PATH
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
