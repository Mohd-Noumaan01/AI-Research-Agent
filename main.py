import os
import io
import csv
from typing import Optional, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from database import init_db, get_topics, update_status
from processing import run_research
from scheduler import start_scheduler, stop_scheduler, catch_up_if_missed


# 1. Initialize SQLite database and background scheduler when the FastAPI app starts
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    catch_up_if_missed()
    yield
    stop_scheduler()


app = FastAPI(title="AI Research Agent API", lifespan=lifespan)

# 2. Add CORS middleware to allow all origins (for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# NOTE: The dashboard frontend (in static/index.html) will call these endpoints
# to trigger research runs, display topics, filter by status, and approve/reject.
# ---------------------------------------------------------------------------


# Endpoint to run the research agent
@app.post("/run")
def run_research_endpoint(max_topics: int = Query(default=10, ge=1)):
    """Runs web searches, LLM analysis, and saves new topics to the database."""
    counts = run_research(max_topics=max_topics)
    return counts


# Endpoint to fetch topics from database, optionally filtered by status
@app.get("/topics")
def get_topics_endpoint(status: Optional[str] = Query(default=None)):
    """Returns all topics, or filters by status if provided."""
    return get_topics(status=status)


# Endpoint to approve a topic by ID
@app.post("/topics/{topic_id}/approve")
def approve_topic(topic_id: int):
    """Sets the topic status to 'Approved'."""
    updated = update_status(topic_id, "Approved")
    if not updated:
        raise HTTPException(status_code=404, detail=f"Topic with ID {topic_id} not found")
    return {"message": f"Topic {topic_id} approved", "topic_id": topic_id, "status": "Approved"}


# Endpoint to reject a topic by ID
@app.post("/topics/{topic_id}/reject")
def reject_topic(topic_id: int):
    """Sets the topic status to 'Rejected'."""
    updated = update_status(topic_id, "Rejected")
    if not updated:
        raise HTTPException(status_code=404, detail=f"Topic with ID {topic_id} not found")
    return {"message": f"Topic {topic_id} rejected", "topic_id": topic_id, "status": "Rejected"}


# Endpoint to export topics in JSON or downloadable CSV format for content agent
@app.get("/export")
def export_topics(
    status: Optional[str] = Query(default="Approved"),
    format: Literal["json", "csv"] = Query(default="json"),
):
    """Exports topics with content agent fields only, in JSON or downloadable CSV format."""
    EXPORT_FIELDS = [
        "title",
        "published_date",
        "summary",
        "key_points",
        "primary_source_name",
        "primary_source_url",
        "secondary_source_name",
        "secondary_source_url",
        "status",
    ]

    all_topics = get_topics(status=status)
    export_data = [
        {field: topic.get(field) for field in EXPORT_FIELDS}
        for topic in all_topics
    ]

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(export_data)
        csv_content = output.getvalue()
        output.close()

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="research_export.csv"'
            },
        )

    return export_data


# Health check endpoint
@app.get("/health")
def health_check():
    """Simple health check endpoint returning status ok."""
    return {"status": "ok"}


# Serve static assets folder
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve the dashboard home page (static/index.html)
@app.get("/")
def serve_index():
    """Serves static/index.html. Does not crash if index.html is currently empty."""
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "message": "static/index.html not found"}


# Allows running directly via 'python main.py'
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
