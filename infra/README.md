# infra/ — Docker & Azure Deployment

## Purpose
All infrastructure-as-code for local dev (Docker Compose) and cloud deployment
(Azure Container Apps via `azure_setup.sh`).

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage backend image (`python:3.11-slim`). Copies `backend/` and installs `requirements/base.txt`. |
| `docker-compose.yml` | Local stack: `redis:7-alpine` (6379) + `backend` (8000) + `frontend` (8080). |
| `azure_setup.sh` | One-time Azure infra provisioning: Container Registry, Container Apps environment, Key Vault. |

## Local dev

```bash
# From Stage/ root — compose file lives in infra/
docker compose -f infra/docker-compose.yml up --build

# Ports:
#   Frontend  → http://localhost:8080
#   Backend   → http://localhost:8000
#   Redis     → localhost:6379
```

## Environment variables
Inject via `.env` in the repo root (local) or Container Apps Configuration panel (Azure).
See `.env.example` for the full list.

## Azure deployment
```bash
# One-time setup
bash infra/azure_setup.sh

# Push image
az acr build --registry <registry> --image codara-backend:latest backend/
```
