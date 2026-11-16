"""FastAPI app. Run: uvicorn venture_os.api.main:app --reload  (docs at /docs)"""

from fastapi import FastAPI

from venture_os import __version__
from venture_os.api import onboarding
from venture_os.api.registry import admin, router

app = FastAPI(title="Venture OS API", version=__version__)
app.include_router(router)
app.include_router(admin)
app.include_router(onboarding.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}
