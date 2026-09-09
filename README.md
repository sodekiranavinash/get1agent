# get1agent

Monorepo for get1agent.

## Layout

```
.
├── frontend/   # React + TypeScript + Tailwind (Vite)
├── backend/    # Python Lambdas + shared layers (health-check, etc.)
├── infra/      # Terraform + deploy scripts (API Gateway, RDS, S3)
├── tools/      # Go Lambda tools
└── README.md
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (usually `http://localhost:5173`).

## Infrastructure

```bash
bash infra/aws/deploy-all.sh
```

See [infra/DEPLOY.md](infra/DEPLOY.md) for Cloudflare DNS, API Gateway, and DBeaver setup.
