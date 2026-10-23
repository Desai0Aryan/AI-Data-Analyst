.PHONY: up down reset test logs

up:            ## Start Postgres + API (http://localhost:8000/docs)
	docker compose up -d --build

down:
	docker compose down

reset:         ## Wipe the database volume and re-seed
	docker compose down -v && docker compose up -d --build

test:          ## Run the whole test suite (needs the db container running)
	cd backend && pip install -q -r requirements-dev.txt && python -m pytest -q

logs:
	docker compose logs -f
