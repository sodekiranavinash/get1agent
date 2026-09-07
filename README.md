# get1agent

Monorepo for get1agent.

## Layout

```
.
├── frontend/       # React + TypeScript + Tailwind (Vite)
├── control_plane/  # FastAPI backend (monolith)
├── infra/          # Terraform + deploy scripts
├── tools/          # Lambda tools
└── README.md
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (usually `http://localhost:5173`).
