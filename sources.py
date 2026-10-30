from typing import List, Dict, Optional, Any
from urllib.parse import urlparse

# Single place that defines all allowed websites and their roles
SOURCES: List[Dict[str, Any]] = [
    {
        "name": "OpenAI Research/Newsroom",
        "domains": ["openai.com"],
        "role": "primary",
    },
    {
        "name": "Google DeepMind Research",
        "domains": ["deepmind.google", "deepmind.com"],
        "role": "primary",
    },
    {
        "name": "Anthropic Research",
        "domains": ["anthropic.com"],
        "role": "primary",
    },
    {
        "name": "arXiv",
        "domains": ["arxiv.org"],
        "role": "primary",
    },
    {
        "name": "Stanford AI Index",
        "domains": ["hai.stanford.edu"],
        "role": "primary",
    },
    {
        "name": "TechCrunch",
        "domains": ["techcrunch.com"],
        "role": "secondary",
    },
    {
        "name": "The Verge",
        "domains": ["theverge.com"],
        "role": "secondary",
    },
    {
        "name": "WIRED",
        "domains": ["wired.com"],
        "role": "secondary",
    },
    {
        "name": "Hugging Face Papers",
        "domains": ["huggingface.co"],
        "role": "discovery_only",
    },
    {
        "name": "The Rundown AI",
        "domains": ["therundown.ai"],
        "role": "discovery_only",
    },
    {
        "name": "TLDR AI",
        "domains": ["tldr.tech"],
        "role": "discovery_only",
    },
    {
        "name": "Google News",
        "domains": ["news.google.com"],
        "role": "discovery_only",
    },
]


def _extract_host_and_path(url: str):
    """Parses URL with urllib.parse and cleans hostname (removes www. and ports)."""
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path or ""
        return host, path
    except Exception:
        return "", ""


def all_domains() -> List[str]:
    """Returns a list of all recognized domains across all sources."""
    domains: List[str] = []
    for source in SOURCES:
        for d in source.get("domains", []):
            if d not in domains:
                domains.append(d)
    return domains


def primary_domains() -> List[str]:
    """Returns a list of all domains that have the 'primary' role."""
    domains: List[str] = []
    for source in SOURCES:
        if source.get("role") == "primary":
            for d in source.get("domains", []):
                if d not in domains:
                    domains.append(d)
    return domains


def get_source(url: str) -> Optional[Dict[str, Any]]:
    """Returns the matching source dict (or None) using exact hostname and path checks."""
    host, path = _extract_host_and_path(url)
    if not host:
        return None

    for source in SOURCES:
        for d in source.get("domains", []):
            # Host must equal allowed domain or end with '.' + domain (exact subdomain)
            if host == d or host.endswith("." + d):
                # Special rule: Hugging Face Papers only allows path starting with /papers
                if d == "huggingface.co":
                    if not (path == "/papers" or path.startswith("/papers/")):
                        return None
                return source

    return None


def is_allowed(url: str) -> bool:
    """Returns True if the URL strictly belongs to an allowed source."""
    return get_source(url) is not None


if __name__ == "__main__":
    print("=== Testing sources.is_allowed() ===")
    test_cases = [
        ("https://openai.com/research/x", True),
        ("https://www.techcrunch.com/2026/01/01/a", True),
        ("https://blog.mean.ceo/post", False),
        ("https://linkedin.com/posts/x", False),
        ("https://notopenai.com/x", False),
        ("https://huggingface.co/papers/2601.00001", True),
        ("https://huggingface.co/some-model", False),
    ]

    all_passed = True
    for url, expected in test_cases:
        result = is_allowed(url)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"[{status}] {url} -> {result} (expected {expected})")

    if all_passed:
        print("\nAll sources tests PASSED.")
    else:
        print("\nSome tests FAILED.")
