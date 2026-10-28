# Push to GitHub

## The fast path (two commands)

```bash
# 1. Prove it works on your machine, with your own API key (a few cents; ~30-80 model calls)
cp .env.example .env            # then set LLM_PROVIDER and LLM_API_KEY inside .env
docker compose up -d db
make eval-live                  # runs the 26 questions against your model, then writes the score into the README

# 2. Fill in your name/username, run the safety checks, commit, create the GitHub repo and push
gh auth login                   # once, if you haven't (https://cli.github.com)
scripts/publish.sh "Your Name" your-github-username verity --push
```

`scripts/publish.sh` does the following, and stops if anything looks wrong:

- fills in `YOUR NAME` / `YOUR_USERNAME` (README badge and LICENSE only)
- refuses to continue if it finds an API-key-shaped string anywhere that would be committed
- refuses to commit `.env`, `node_modules`, `dist` or `.zip` files
- makes the first commit (uses a private `@users.noreply.github.com` address if git has no identity set)
- with `--push`: creates a **public** repo, pushes, and sets the topics

Run it **without** `--push` first if you want to inspect the commit, then push by hand:

```bash
git remote add origin git@github.com:<your-username>/verity.git
git push -u origin main
```

## What has and hasn't been verified

Verified in the environment this was built in:

- the full backend suite (313 tests) and frontend (77 tests, typecheck, production build), from a clean extraction
- the database init files on a **brand-new** Postgres cluster: schema, seed, read-only role, all tests, and the evaluation gate pass
- the real nginx config (syntax, SPA fallback, caching, security headers on every route, `X-Forwarded-For` overwriting,
  events streamed 1 s apart), `docker compose config`, and the CI workflow with `actionlint`
- the backend running with only the files its Dockerfile copies, as a non-root user
- `scripts/publish.sh`, in throwaway copies (including secret detection and awkward names)

**Not verified, so check these on your machine:**

- [ ] `docker compose up -d --build` end to end: the base images could not be downloaded here, so the Dockerfiles
      were never built. Then open http://localhost:3000.
- [ ] The first GitHub Actions run is green (Actions tab). Two bugs in this area were already found and fixed
      (a missing `bash` in the Postgres Alpine image, and a healthcheck that reported ready too early), so a
      third is possible.
- [ ] `make eval-live` against a real model. Until you run it, the only scores in the README are replay scores,
      which validate the harness, not a model.

## After pushing

- [ ] Open the Actions tab and confirm CI is green.
- [ ] Pin the repository to your profile.
- [ ] Optional: Settings, Social preview: upload `docs/screenshots/03-answer-and-proof.png`.
- [ ] If you add a public demo: use `LLM_PROVIDER=replay` (free, safe) or keep `DAILY_LLM_BUDGET` low; keep
      `LLM_API_KEY` in your host's secret manager; publish only the nginx port (not 8000); rotate the default DB passwords.

## Talking about it

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md). The README's "Limitations" section is deliberate: naming a project's limits is a
strength in an interview.
