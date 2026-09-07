# Control Plane (FastAPI)

Backend API for get1agent.

## Stack

- FastAPI + SQLAlchemy 2 async + asyncpg
- **Production:** RDS IAM auth via EC2 instance role (no DB password)
- **Local dev:** `DATABASE_URL` with password

## Local run

```bash
cd control_plane
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Ready: http://localhost:8000/ready

## Deploy to AWS

```bash
bash infra/aws/deploy-all.sh
```

Or see `infra/DEPLOY.md`.

## Layout

```
app/
  main.py
  config.py
  core/database.py   # IAM or password engine
  api/v1/            # Route modules
  models/
  schemas/
```
