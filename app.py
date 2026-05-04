import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

load_dotenv(Path(__file__).resolve().parent / ".env")

import db
import ingest
import rag

templates = Jinja2Templates(directory="templates")

# In-memory diagnostic sessions: { session_id: { "question": str, "history": list[dict] } }
# History entries follow the {"role": "user"|"assistant", "content": str} shape.
_diag_sessions: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Technician AI", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    entries = db.list_knowledge_entries(limit=20)
    topics = db.list_topics(include_documents=True)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"knowledge_entries": entries, "topics": topics},
    )


@app.post("/ask", response_class=HTMLResponse)
def ask(request: Request, question: str = Form(...)):
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="empty question")
    result = rag.answer_question(question)
    return templates.TemplateResponse(request, "_answer.html", result)


@app.post("/feedback/{conversation_id}", response_class=HTMLResponse)
def feedback(
    request: Request,
    conversation_id: int,
    kind: str = Form(...),
    note: Optional[str] = Form(None),
):
    if kind not in ("worked", "failed", "learned"):
        raise HTTPException(status_code=400, detail="invalid kind")

    if kind == "worked":
        return HTMLResponse(
            '<div class="msg ok">Marked as worked. Thanks!</div>'
        )

    note = (note or "").strip()
    if not note:
        return HTMLResponse(
            '<div class="msg warn">Add a note describing what you learned, then submit again.</div>'
        )

    entry = rag.record_knowledge_from_feedback(conversation_id, kind, note)
    if entry is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    return templates.TemplateResponse(request, "_entry_added.html", {"entry": entry})


@app.post("/diagnose", response_class=HTMLResponse)
def diagnose_start(request: Request, question: str = Form(...)):
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="empty question")

    session_id = str(uuid.uuid4())
    result = rag.diagnose_step(question, history=[], questions_asked=0)
    _diag_sessions[session_id] = {
        "question": question,
        "history": [{"role": "assistant", "content": result["message"]}],
    }
    return templates.TemplateResponse(
        request,
        "_diagnostic.html",
        {
            **result,
            "session_id": session_id,
            "history": [],
            "step": 1,
        },
    )


@app.post("/diagnose/step", response_class=HTMLResponse)
def diagnose_continue(
    request: Request,
    session_id: str = Form(...),
    answer: str = Form(...),
):
    answer = answer.strip()
    if not answer:
        return HTMLResponse(
            '<div class="msg warn">Please describe what you see before continuing.</div>'
        )

    session = _diag_sessions.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=400,
            detail="diagnostic session not found or expired — please start a new diagnosis",
        )

    question = session["question"]
    history = list(session["history"])
    questions_asked = sum(1 for m in history if m["role"] == "assistant")

    history.append({"role": "user", "content": answer})
    result = rag.diagnose_step(question, history, questions_asked=questions_asked)

    if result["is_resolved"]:
        # Don't append the resolution message to history; it renders as diag-final
        session["history"] = history
        display_history = history
    else:
        history.append({"role": "assistant", "content": result["message"]})
        session["history"] = history
        # Exclude the latest AI question from the history panel; it renders as diag-current
        display_history = history[:-1]

    step = sum(1 for m in session["history"] if m["role"] == "assistant")

    return templates.TemplateResponse(
        request,
        "_diagnostic.html",
        {
            **result,
            "session_id": session_id,
            "history": display_history,
            "step": step,
        },
    )


@app.post("/ingest")
async def ingest_endpoint(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ingest.SUPPORTED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type {ext} (supported: {', '.join(sorted(ingest.SUPPORTED_EXTS))})",
        )
    dest = Path("manuals") / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    chunks = ingest.ingest_file(dest)
    return JSONResponse({"filename": file.filename, "chunks": chunks})


@app.get("/knowledge")
def knowledge():
    return {"entries": db.list_knowledge_entries(limit=200)}


@app.get("/topics")
def topics():
    return {"topics": db.list_topics()}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=True)
