# Push to GitHub: checklist

## Before you commit

- [ ] Replace the placeholders: `grep -rn "YOUR_USERNAME\|YOUR NAME" .` (README badge, LICENSE).
- [ ] Make sure no secrets are tracked: `.env` is git-ignored; only `.env.example` is committed. Run `git status` and
      look for any `.env` file before the first commit.
- [ ] Run everything once on your machine:
  ```bash
  docker compose up -d db && make test        # backend
  make test-ui                                 # frontend
  make eval                                    # offline evaluation gate
  ```
- [ ] Build and open the stack once: `docker compose up -d --build`, then http://localhost:3000.
      (The Docker images and the CI workflow are the parts that could not be exercised before you received this project.)
- [ ] Run `make eval-live` with your real key and put the score in the README's evaluation table.

## Create the repository

```bash
cd ai-data-analyst
git init -b main
git add .
git status                 # sanity check: no .env, no node_modules
git commit -m "Verity: AI data analyst that executes and verifies SQL"
git remote add origin git@github.com:YOUR_USERNAME/verity.git
git push -u origin main
```

## On GitHub

- [ ] **Actions** tab: confirm the first CI run is green (backend tests + offline eval, frontend typecheck/tests/build).
      If the backend job fails on login to Postgres, check `docker compose up --wait db` ran before the tests.
- [ ] Add a description: *AI data analyst that writes SQL, runs it read-only, and verifies the answer against a known result.*
- [ ] Add topics: `text-to-sql`, `llm`, `fastapi`, `react`, `postgresql`, `sqlglot`, `evaluation`, `ai-safety`.
- [ ] Pin the repo to your profile. The first screenshot in the README is your thumbnail, so keep it current.
- [ ] Optional: set the social preview image to `docs/screenshots/03-answer-and-proof.png`.

## If you deploy a public demo

- Use `LLM_PROVIDER=replay` for a free, safe public demo, or keep `DAILY_LLM_BUDGET` low with a real model.
- Store `LLM_API_KEY` in your host's secret manager, not in the repo or an image.
- Publish **only** the frontend port (nginx). Don't expose the API port while `TRUST_PROXY=true`.
- Rotate the default database passwords from `.env.example`.
- Remember the rate limit and budget are per process; run a single backend instance.

## Talking about it

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md). The README's "Limitations" section is deliberate: naming your project's limits
is a strength in an interview.
