from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from src.api.routes import router


CHAT_PAGE = Path(__file__).parent / "static" / "index.html"

app = FastAPI(
	title="Dexian Medical Doctor",
	description="Local, source-grounded medical guideline chat prototype.",
)
app.include_router(router)


@app.get("/", include_in_schema=False)
def chat_page() -> FileResponse:
	return FileResponse(CHAT_PAGE)