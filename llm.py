import os
import sys
import re
import json
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")

if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY is missing from your .env file.")
    sys.exit(1)

if not OPENROUTER_MODEL:
    print("Error: OPENROUTER_MODEL is missing from your .env file.")
    sys.exit(1)


def ask_llm(prompt: str) -> Optional[str]:
    """Sends a prompt to OpenRouter API and returns the response text."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    model_name = OPENROUTER_MODEL.strip()

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 400,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if not response.ok:
            print(f"OpenRouter Error [Model: {model_name}] Status: {response.status_code}")
            print(f"Response: {response.text}")
            return None

        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        print(f"Error: OpenRouter request timed out for model: {model_name}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling OpenRouter API [Model: {model_name}]: {e}")
        return None
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error reading OpenRouter response [Model: {model_name}]: {e}")
        return None


def analyze_topic(title: str, text: str, source_name: str) -> Dict[str, Any]:
    """Analyzes a topic using the LLM and returns summary, key points, claims, notes, and suggested status."""
    fallback: Dict[str, Any] = {
        "summary": (text or "")[:300] if text else "No content available.",
        "key_points": "",
        "claims": [],
        "evidence_notes": "No evidence analyzed.",
        "suggested_status": "Needs Verification",
    }

    prompt = f"""You are an elite research analyst preparing editorial briefs for an automated content agent and human tech writers.
Analyze this development and synthesize a content-ready brief.

Title: {title}
Source Name: {source_name}
Content:
{text}

Return ONLY a valid JSON object with exactly these keys:
{{
  "summary": "A high-impact editorial briefing (3-4 well-structured sentences) written specifically for content creators. Explain: 1) What core breakthrough, model release, or major development occurred, 2) The practical significance, industry impact, or benchmark metrics, and 3) The strategic takeaway for developers, businesses, or researchers. Write in engaging, professional prose free of Markdown artifacts (###), navigation text, or generic filler.",
  "key_points": "- Core Announcement: [What specifically was launched or discovered]\\n- Key Evidence/Data: [Exact metrics, benchmark scores, or dates]\\n- Content Angle: [Suggested hook or narrative angle for writers]",
  "claims": ["List of main factual claims extracted from the source"],
  "evidence_notes": "Specific evidence supporting or questioning these claims from the text",
  "suggested_status": "Likely Supported" or "Needs Verification"
}}

CRITICAL RULES:
1. You must NEVER declare any topic or claim verified. You only provide preliminary analysis.
2. If evidence is weak, unclear, missing, or comes only from a short snippet, you MUST set suggested_status to "Needs Verification".
3. Return ONLY raw JSON without any markdown code fences, headers, or conversational text.
"""

    raw_reply = ask_llm(prompt)
    if not raw_reply:
        return fallback

    # 2. Remove any ``` code fences, then keep only the text from first "{" to last "}"
    cleaned = re.sub(r"```[a-zA-Z]*", "", raw_reply)
    cleaned = cleaned.replace("```", "").strip()

    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        cleaned = cleaned[start_idx : end_idx + 1]

    # 3. Parse JSON; if it fails, print first 300 chars of raw reply and return fallback
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            print("LLM reply was not a JSON object. Raw reply (first 300 chars):")
            print(raw_reply[:300])
            return fallback

        # Enforce status options
        suggested = parsed.get("suggested_status", "Needs Verification")
        if suggested != "Likely Supported":
            suggested = "Needs Verification"

        key_pts = parsed.get("key_points", "")
        if isinstance(key_pts, list):
            key_pts = "\n".join(f"- {pt}" for pt in key_pts)

        return {
            "summary": parsed.get("summary") or fallback["summary"],
            "key_points": str(key_pts),
            "claims": parsed.get("claims", []),
            "evidence_notes": parsed.get("evidence_notes", "No evidence notes provided."),
            "suggested_status": suggested,
        }
    except Exception as e:
        print(f"Error parsing JSON from LLM: {e}")
        print("Raw reply (first 300 chars):")
        print(raw_reply[:300])
        return fallback


if __name__ == "__main__":
    print("Testing analyze_topic()...\n")
    sample_title = "Google DeepMind Releases New Biology Architecture"
    sample_source = "Google DeepMind Research"
    sample_text = (
        "Researchers at Google DeepMind today announced a new multi-agent architecture for biological analysis. "
        "The model accurately predicts protein mutations and accelerated candidate screening by 40%. "
        "Benchmark data was released openly for researchers."
    )

    result = analyze_topic(sample_title, sample_text, sample_source)
    print(json.dumps(result, indent=2))
