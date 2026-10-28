.PHONY: up down reset test logs eval eval-naive eval-live dev-api dev-ui test-ui

up:            ## Start Postgres + API (http://localhost:8000/docs)
	docker compose up -d --build

down:
	docker compose down

reset:         ## Wipe the database volume and re-seed
	docker compose down -v && docker compose up -d --build

test:          ## Backend tests (needs the db container running)
	cd backend && pip install -q -r requirements-dev.txt && python -m pytest -q

test-ui:       ## Frontend typecheck, unit tests and production build
	cd frontend && npm ci && npm run typecheck && npm test && npm run build

dev-api:       ## API with hot reload; keyless demo mode (needs `docker compose up -d db`)
	cd backend && LLM_PROVIDER=replay uvicorn app.main:app --reload --port 8000

dev-ui:        ## Vite dev server on http://localhost:5173 (proxies /api to :8000)
	cd frontend && npm install && npm run dev

logs:
	docker compose logs -f

eval:          ## Offline eval: replay the reference recording (validates harness + pipeline)
	cd backend && python -m evals.run --min-accuracy 1.0

eval-naive:    ## Replay a careless model: the harness MUST report failures
	cd backend && python -m evals.run --recording evals/recordings/naive.json

eval-live:     ## Evaluate your real LLM (needs LLM_API_KEY); saves a replayable recording and updates the README score
	cd backend && python -m evals.run --mode live --record evals/recordings/live.json --markdown eval-report.md --json eval-report.json
	cd backend && python -m evals.readme_score eval-report.json
