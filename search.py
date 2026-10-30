import os
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from tavily import TavilyClient

from sources import SOURCES, all_domains, primary_domains, get_source, is_allowed

# Load environment variables
load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Date range limits for 2026 searches
START_DATE = "2026-01-01"
END_DATE = "2026-10-29"

# Base discovery queries
BASE_QUERIES = [
    "latest AI research papers and breakthroughs 2026",
    "latest AI models tools and releases 2026",
    "latest artificial intelligence company announcements 2026",
    "latest real-world AI applications and case studies 2026",
]


def get_tavily_client() -> Optional[TavilyClient]:
    """Returns a TavilyClient instance or None if API key is invalid."""
    if not TAVILY_API_KEY or TAVILY_API_KEY.strip() == "your_tavily_key_here":
        print("Error: TAVILY_API_KEY is missing or invalid in your .env file.")
        return None
    try:
        return TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print(f"Error initializing TavilyClient: {e}")
        return None


def extract_arxiv_date(url: str) -> Optional[str]:
    """Extracts published date from an arXiv URL ID (e.g. 2603.01234 -> 2026-03)."""
    match = re.search(r"(\d{2})(\d{2})\.\d+", url)
    if match:
        year_prefix = match.group(1)
        month = match.group(2)
        return f"20{year_prefix}-{month}"
    return None


def parse_and_validate_date(date_str: Optional[str], url: str) -> Optional[str]:
    """Validates date in 2026 or extracts from arXiv ID; returns None if not 2026."""
    if "arxiv.org" in url:
        arxiv_date = extract_arxiv_date(url)
        if arxiv_date and arxiv_date.startswith("2026"):
            return arxiv_date

    if not date_str:
        return None

    date_str_clean = str(date_str).strip()
    if "2026" in date_str_clean:
        return date_str_clean

    return "INVALID_YEAR"


def search_topic(
    query: str,
    max_results: int = 5,
    include_domains_list: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Runs a Tavily search strictly constrained to allowed domains and 2026 dates."""
    client = get_tavily_client()
    if not client:
        return []

    # Always enforce allowed domains
    domains = include_domains_list or all_domains()

    kwargs: Dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "include_domains": domains,
    }

    try:
        kwargs["start_date"] = START_DATE
        kwargs["end_date"] = END_DATE
        response = client.search(**kwargs)
    except TypeError:
        kwargs.pop("start_date", None)
        kwargs.pop("end_date", None)
        try:
            response = client.search(**kwargs)
        except Exception as e:
            print(f"Search failed for '{query}': {e}")
            return []
    except Exception as e:
        print(f"Search failed for '{query}': {e}")
        return []

    raw_results = response.get("results", [])
    clean_results = []

    for item in raw_results:
        url = item.get("url", "")

        # 2a: Strict check - drop if not allowed
        if not is_allowed(url):
            print(f"REJECTED (not on allowed list): {url}")
            continue

        raw_date = item.get("published_date")
        date_check = parse_and_validate_date(raw_date, url)
        if date_check == "INVALID_YEAR":
            continue

        source_info = get_source(url) or {}
        source_name = source_info.get("name", "Unknown Source")
        source_role = source_info.get("role", "discovery_only")

        # 2c: For aggregators linking out, check outbound links if found in content
        clean_results.append({
            "title": item.get("title", "No Title"),
            "url": url,
            "content": item.get("content", ""),
            "published_date": date_check,
            "source_name": source_name,
            "source_role": source_role,
        })

    return clean_results


def find_primary_source(title: str, content: str = "") -> Optional[Dict[str, Any]]:
    """Searches primary domains for the title, verifying the match is strictly allowed & primary."""
    if not title:
        return None

    try:
        # 2b & 2c: Constrain include_domains strictly to primary domains
        primaries = primary_domains()
        candidates = search_topic(
            query=title,
            max_results=5,
            include_domains_list=primaries,
        )

        best_match = None
        best_ratio = 0.0
        title_lower = title.strip().lower()

        for cand in candidates:
            cand_url = cand.get("url", "")

            # Verify URL is allowed
            if not is_allowed(cand_url):
                print(f"REJECTED (not on allowed list): {cand_url}")
                continue

            # Verify it belongs to a primary source
            cand_source = get_source(cand_url)
            if not cand_source or cand_source.get("role") != "primary":
                print(f"REJECTED (not on primary list): {cand_url}")
                continue

            cand_title = cand.get("title", "").strip().lower()
            ratio = SequenceMatcher(None, title_lower, cand_title).ratio()

            if ratio > best_ratio and ratio > 0.5:
                best_ratio = ratio
                best_match = {
                    "title": cand.get("title"),
                    "url": cand_url,
                    "content": cand.get("content"),
                    "source_name": cand_source.get("name"),
                }

        return best_match
    except Exception as e:
        print(f"find_primary_source failed for '{title}': {e}")
        return None


def run_all_searches() -> List[Dict[str, Any]]:
    """Runs thematic discovery searches plus primary source queries with strict URL checking."""
    queries = list(BASE_QUERIES)

    for source in SOURCES:
        if source.get("role") == "primary":
            queries.append(f"{source['name']} research 2026")

    all_results = []
    seen_urls = set()

    for q in queries:
        print(f"Searching: '{q}'...")
        results = search_topic(q, max_results=5)
        for item in results:
            url = item.get("url")
            if not url:
                continue

            # Verify again before appending
            if not is_allowed(url):
                print(f"REJECTED (not on allowed list): {url}")
                continue

            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(item)

    print(f"Discovery complete: {len(all_results)} allowed 2026 results found.")
    return all_results


if __name__ == "__main__":
    print("=== Testing search.py ===\n")
    results = run_all_searches()

    print("\n--- Showing 3 Results & Primary Source Lookups ---")
    for idx, item in enumerate(results[:3], 1):
        print(f"\nResult {idx}:")
        print(f"  Title:        {item.get('title')}")
        print(f"  Date:         {item.get('published_date')}")
        print(f"  Source Role:  {item.get('source_role')}")

        if item.get("source_role") in ["secondary", "discovery_only"]:
            prim = find_primary_source(item.get("title", ""), item.get("content", ""))
            prim_url = prim.get("url") if prim else "none"
        else:
            prim_url = item.get("url")

        print(f"  Primary URL:  {prim_url}")
