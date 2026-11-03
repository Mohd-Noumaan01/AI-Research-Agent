from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional

from database import init_db, add_topic, get_topics, url_exists
from search import run_all_searches, find_primary_source
from llm import analyze_topic
from sources import is_allowed, get_source


def clean_snippet_text(text: str) -> str:
    """Cleans raw web snippet text by stripping markdown headers, nav artifacts, and excess symbols."""
    if not text:
        return "No content available."
    import re
    # Remove markdown headers and dividers (###, ##, ---)
    cleaned = re.sub(r"[#\-*_]{2,}\s*", "", text)
    cleaned = re.sub(r"#+\s*", "", cleaned)
    # Remove image captions and metadata labels
    cleaned = re.sub(r"Image\s*\d+:?[^\n]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Author\s+[A-Za-z0-9_\-]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"View all|Keep reading|Read more", "", cleaned, flags=re.IGNORECASE)
    # Normalize whitespaces
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 280:
        cut = cleaned[:280]
        last_punct = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        if last_punct > 80:
            cleaned = cut[:last_punct + 1]
        else:
            cleaned = cut.rstrip() + "..."
    return cleaned


# Helper to check title similarity against already known titles
def is_title_duplicate(title: str, existing_titles: List[str], threshold: float = 0.85) -> bool:
    """Returns True if the title is over 85% similar to an existing title."""
    title_clean = title.strip().lower()
    for existing in existing_titles:
        similarity = SequenceMatcher(None, title_clean, existing.strip().lower()).ratio()
        if similarity > threshold:
            return True
    return False


# Calculates a credibility score (0 to 100) based on strict rubric
def calculate_score(
    has_primary: bool,
    published_date: Optional[str],
    claims: List[Any],
    role: str,
    content: str,
) -> float:
    """Calculates score 0-100:
    +35 primary source found
    +20 date in 2026
    +20 at least one claim
    +15 role is primary or secondary
    +10 content longer than 300 characters
    """
    score = 0.0

    if has_primary:
        score += 35.0

    if published_date and "2026" in str(published_date):
        score += 20.0

    if isinstance(claims, list) and len(claims) > 0:
        score += 20.0

    if role in ["primary", "secondary"]:
        score += 15.0

    if isinstance(content, str) and len(content.strip()) > 300:
        score += 10.0

    return min(100.0, score)


# Main research workflow
def run_research(max_topics: int = 10) -> Dict[str, int]:
    """Runs web discovery, resolves primary sources, analyzes content, and saves to database."""
    print("Starting research run...")

    all_results = run_all_searches()

    counts = {
        "found": len(all_results),
        "saved": 0,
        "duplicates": 0,
        "skipped": 0,
        "rejected": 0,
        "failed": 0,
    }

    if not all_results:
        print("No search results to process.")
        return counts

    # Load existing titles to detect duplicates
    existing_topics = get_topics()
    existing_titles = [t["title"] for t in existing_topics if t.get("title")]

    topics_to_process = all_results[:max_topics]
    print(f"Processing up to {len(topics_to_process)} topics out of {len(all_results)} found.\n")

    for idx, item in enumerate(topics_to_process, start=1):
        title = item.get("title", "No Title")
        url = item.get("url", "")
        snippet = item.get("content", "")
        role = item.get("source_role", "discovery_only")
        source_name = item.get("source_name", "Web Source")
        pub_date = item.get("published_date")

        print(f"[{idx}/{len(topics_to_process)}] Processing: '{title}' ({role})")

        try:
            # 3. Final verification: source_url MUST be allowed
            if not is_allowed(url):
                print(f"REJECTED (not on allowed list): {url}")
                counts["rejected"] += 1
                continue

            # a. Skip if URL already exists
            if url_exists(url):
                print(f"  -> Skipped: URL already in database ({url})")
                counts["skipped"] += 1
                continue

            # a. Skip if title is over 85% similar to an existing title and save as Duplicate
            if is_title_duplicate(title, existing_titles):
                print("  -> Duplicate: Title similarity > 0.85. Saving as Duplicate.")
                add_topic(
                    title=title,
                    source_url=url,
                    summary="Duplicate topic detected by title similarity check.",
                    evidence="",
                    status="Duplicate",
                    score=0.0,
                    published_date=pub_date,
                    secondary_source_url=url,
                    secondary_source_name=source_name,
                )
                existing_titles.append(title)
                counts["duplicates"] += 1
                continue

            # b. Primary source resolution
            primary_info: Optional[Dict[str, Any]] = None
            if role == "primary":
                primary_url = url
                primary_name = source_name
                primary_content = snippet
                secondary_url = None
                secondary_name = None
            else:
                secondary_url = url
                secondary_name = source_name
                print("  -> Looking up primary source on primary domains...")
                primary_info = find_primary_source(title, snippet)
                if primary_info:
                    candidate_primary_url = primary_info.get("url")
                    # Check that found primary URL is strictly allowed
                    if candidate_primary_url and is_allowed(candidate_primary_url):
                        primary_url = candidate_primary_url
                        primary_name = primary_info.get("source_name")
                        primary_content = primary_info.get("content") or snippet
                        print(f"  -> Found primary source: {primary_name} ({primary_url})")
                    else:
                        if candidate_primary_url:
                            print(f"REJECTED (not on allowed list): {candidate_primary_url}")
                        primary_url = None
                        primary_name = None
                        primary_content = None
                else:
                    primary_url = None
                    primary_name = None
                    primary_content = None
                    print("  -> No matching primary source found.")

            # Validate secondary_url if present
            if secondary_url and not is_allowed(secondary_url):
                print(f"REJECTED (not on allowed list): {secondary_url}")
                secondary_url = None
                secondary_name = None

            # d. Analysis text selection
            analysis_text = primary_content if primary_content else snippet
            analysis_source_name = primary_name if primary_name else source_name

            # Call analyze_topic
            print("  -> Analyzing with LLM...")
            try:
                analysis = analyze_topic(title, analysis_text, analysis_source_name)
            except Exception as e:
                print(f"  -> analyze_topic failed: {e}")
                analysis = None

            # e. Safe fallback summary
            if not analysis or not isinstance(analysis, dict):
                summary = clean_snippet_text(snippet)
                evidence = "AI analysis unavailable - snippet only"
                key_points = ""
                claims = []
                suggested_status = "Needs Verification"
            else:
                raw_summary = analysis.get("summary", "")
                if not raw_summary or raw_summary.startswith("Analysis failed") or "###" in raw_summary:
                    summary = clean_snippet_text(snippet)
                    evidence = "AI analysis unavailable - snippet only"
                else:
                    summary = raw_summary
                    evidence = analysis.get("evidence_notes", "AI analysis unavailable - snippet only")

                key_points = analysis.get("key_points", "")
                claims = analysis.get("claims", [])
                suggested_status = analysis.get("suggested_status", "Needs Verification")

            # f. STATUS RULE:
            # Verified ONLY if a primary source URL was found AND the LLM suggested "Likely Supported".
            # Search snippets alone never make something Verified. All others default to Needs Verification.
            if primary_url and suggested_status == "Likely Supported":
                status = "Verified"
            else:
                status = "Needs Verification"

            # g. Score 0-100 calculation
            score = calculate_score(
                has_primary=bool(primary_url),
                published_date=pub_date,
                claims=claims,
                role=role,
                content=analysis_text,
            )

            # h. Save topic to SQLite database
            add_topic(
                title=title,
                source_url=url,
                summary=summary,
                evidence=evidence,
                status=status,
                score=score,
                published_date=pub_date,
                primary_source_url=primary_url,
                primary_source_name=primary_name,
                secondary_source_url=secondary_url,
                secondary_source_name=secondary_name,
                key_points=key_points,
            )

            existing_titles.append(title)
            counts["saved"] += 1
            print(f"  -> Saved topic #{counts['saved']} as '{status}' with score {score}/100")

        except Exception as e:
            print(f"  -> Error processing '{title}': {e}")
            counts["failed"] += 1

    print("\nResearch run completed.")
    return counts


if __name__ == "__main__":
    print("=== Testing processing.py ===")
    init_db()
    counts = run_research(max_topics=3)
    print("\n=== Research Run Summary ===")
    print(f"Found:      {counts['found']}")
    print(f"Saved:      {counts['saved']}")
    print(f"Duplicates: {counts['duplicates']}")
    print(f"Skipped:    {counts['skipped']}")
    print(f"Rejected:   {counts['rejected']}")
    print(f"Failed:     {counts['failed']}")
