# Deploying the Avengers Capital DealRoom console

Free hosting on Streamlit Community Cloud; works in any phone browser.

1. Create an empty **private** repo on GitHub (e.g. `avengers-dealroom`), with no README.
2. Push this folder:
   ```
   git remote add origin https://github.com/<you>/avengers-dealroom.git
   git push -u origin main
   ```
3. Go to https://share.streamlit.io, sign in with GitHub, **Create app** -> pick the repo, branch `main`, file `dealroom_app.py`.
4. **Advanced settings -> Secrets**: paste the contents of `.streamlit/secrets.example.toml` with your real Groq (and optional Fanar) key.
5. Deploy. Share the `*.streamlit.app` link with the team; for a private repo, invite teammates in the app's sharing settings.

Re-running web research needs the local search engine, so do it on the laptop
(`docker compose -p dealroom up -d searxng`, then `python -m dealroom.research`), commit `data/research/`, and push.
