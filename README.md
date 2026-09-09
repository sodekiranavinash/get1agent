# get1agent

Monorepo for get1agent.

## Layout

```
.
├── frontend/   # React + TypeScript + Tailwind (Vite)
├── infra/      # Terraform + deploy scripts (Kong, RDS, S3)
├── tools/      # Lambda tools
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

See [infra/DEPLOY.md](infra/DEPLOY.md) for Cloudflare DNS, Kong Manager UI, and DBeaver setup.
