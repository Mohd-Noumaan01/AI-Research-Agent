import sqlite3
from typing import List, Dict, Optional, Any

DB_NAME = "research.db"

VALID_STATUSES = [
    "Needs Verification",
    "Verified",
    "Approved",
    "Rejected",
    "Duplicate",
]


# Helper function to open a database connection with dictionary-like row access
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# Initializes the database and creates the topics table if it doesn't exist,
# and migrates new columns if they do not exist in an existing database.
def init_db() -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    summary TEXT,
                    evidence TEXT,
                    status TEXT NOT NULL DEFAULT 'Needs Verification' CHECK(status IN ('Needs Verification', 'Verified', 'Approved', 'Rejected', 'Duplicate')),
                    score REAL DEFAULT 0.0,
                    published_date TEXT,
                    primary_source_url TEXT,
                    primary_source_name TEXT,
                    secondary_source_url TEXT,
                    secondary_source_name TEXT,
                    key_points TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Ensure new columns exist if the table was created under an older schema
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(topics)")
            existing_columns = {row["name"] for row in cursor.fetchall()}

            new_columns = [
                ("published_date", "TEXT"),
                ("primary_source_url", "TEXT"),
                ("primary_source_name", "TEXT"),
                ("secondary_source_url", "TEXT"),
                ("secondary_source_name", "TEXT"),
                ("key_points", "TEXT"),
            ]

            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    conn.execute(f"ALTER TABLE topics ADD COLUMN {col_name} {col_type}")
    finally:
        conn.close()


# Inserts a new topic into the database and returns its new ID
def add_topic(
    title: str,
    source_url: str,
    summary: str = "",
    evidence: str = "",
    status: str = "Needs Verification",
    score: float = 0.0,
    published_date: Optional[str] = None,
    primary_source_url: Optional[str] = None,
    primary_source_name: Optional[str] = None,
    secondary_source_url: Optional[str] = None,
    secondary_source_name: Optional[str] = None,
    key_points: Optional[str] = None,
) -> int:
    # Handle swapped status/score arguments flexibly
    if isinstance(status, (int, float)) and isinstance(score, str):
        score, status = status, score

    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}"
        )

    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO topics (
                    title,
                    source_url,
                    summary,
                    evidence,
                    status,
                    score,
                    published_date,
                    primary_source_url,
                    primary_source_name,
                    secondary_source_url,
                    secondary_source_name,
                    key_points
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    source_url,
                    summary,
                    evidence,
                    status,
                    score,
                    published_date,
                    primary_source_url,
                    primary_source_name,
                    secondary_source_url,
                    secondary_source_name,
                    key_points,
                ),
            )
            return cursor.lastrowid
    finally:
        conn.close()


# Retrieves topics from the database, optionally filtered by status
def get_topics(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM topics WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor.execute("SELECT * FROM topics ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# Updates the status of an existing topic by its ID
def update_status(id: int, status: str) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}"
        )

    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE topics SET status = ? WHERE id = ?",
                (status, id),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


# Checks if a topic with the given source URL already exists
def url_exists(url: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM topics WHERE source_url = ? LIMIT 1", (url,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


# Returns the newest created_at timestamp from topics, or None if table is empty
def get_last_run_time() -> Optional[str]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM topics ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        return row["created_at"] if row else None
    finally:
        conn.close()


# Quick test script to verify database functionality
if __name__ == "__main__":
    print("Testing database setup...")
    init_db()
    print("[OK] Database initialized.")

    test_url = "https://example.com/ai-agent-guide"
    if not url_exists(test_url):
        topic_id = add_topic(
            title="Building Autonomous Research Agents",
            source_url=test_url,
            summary="An overview of multi-agent architecture for web research.",
            evidence="Key finding: Agents decompose tasks into search, verify, summarize.",
            score=8.5,
            published_date="2026-10-29",
            primary_source_url="https://openai.com/research",
            primary_source_name="OpenAI Research/Newsroom",
            secondary_source_url="https://techcrunch.com/article",
            secondary_source_name="TechCrunch",
            key_points="Multi-agent orchestration, verification loops",
        )
        print(f"[OK] Added sample topic with ID: {topic_id}")
    else:
        print("[OK] Sample topic already exists.")

    print(f"[OK] url_exists check: {url_exists(test_url)}")

    topics = get_topics()
    print(f"[OK] Total topics found: {len(topics)}")
    if topics:
        first_id = topics[0]["id"]
        update_status(first_id, "Verified")
        print(f"[OK] Updated topic ID {first_id} status to 'Verified'.")

    verified_topics = get_topics(status="Verified")
    print(f"[OK] Verified topics count: {len(verified_topics)}")
    print("All database tests passed successfully!")
