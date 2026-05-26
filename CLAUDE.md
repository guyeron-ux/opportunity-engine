# Opportunity Discovery Engine — App MD
Last Updated: 2026-05-25

## Tech Stack
- Framework: Python/FastAPI (backend), React/Vite (frontend)
- Styling: Tailwind CSS
- Backend/DB: Redis (Upstash) in production; local JSON fallback in dev
- Auth: —
- APIs: Minimax M2.7 via OpenAI-compatible SDK (LLM), Tavily (web search)
- Hosting: Render (backend, auto-deploys from GitHub), Netlify (frontend, file deploy API)
- Build tool: Vite (frontend)

## File Structure (key files only)
backend/main.py — FastAPI app entry point
backend/config.py — app configuration
backend/agents/ — LLM agent logic
backend/api/ — API route handlers
backend/models/ — data models
backend/scheduler.py — scheduled tasks
frontend/src/App.tsx — root React component
frontend/src/api.ts — API client
frontend/src/components/ — UI components
frontend/src/hooks/ — custom React hooks
frontend/src/utils/ — utility functions
run.sh — starts full stack locally
render.yaml — Render deployment config
netlify.toml — Netlify deployment config
requirements.txt — Python dependencies

## Environment Variables Required
- LLM_BASE_URL — base URL for Minimax M2.7 OpenAI-compatible endpoint
- LLM_API_KEY — API key for Minimax LLM
- LLM_MODEL — model name (e.g. MiniMax-Text-01 or similar)
- TAVILY_API_KEY — Tavily web search API key
- UPSTASH_REDIS_URL — Upstash Redis connection URL (production)
- UPSTASH_REDIS_TOKEN — Upstash Redis auth token (production)

## Known Issues and Workarounds
-

## Deployment Instructions
- Local dev: `./run.sh` (full stack) — or separately: `PYTHONPATH=. uvicorn backend.main:app` + `cd frontend && npm run dev`
- Build: `cd frontend && npm run build`
- Deploy backend: Render — auto-deploys on push to GitHub (https://opportunity-engine-z2qq.onrender.com)
- Deploy frontend: Netlify file deploy API (site: opportunity-engine-app.netlify.app)
- Deploy frequency rule: per Section 4 of global CLAUDE.md — local-first, deploy only on completed + tested features

## Last Session Summary
- What was completed: —
- What is in progress: —
- Open questions: —

## Rules Specific to This App
- LLM calls go through the backend only — never expose LLM_API_KEY to the frontend
- Redis is production-only; dev falls back to local JSON — do not assume Redis is available locally
- Backend lives on Render free tier — may have cold starts; factor this into testing
