#!/usr/bin/env python3
"""RSS 피드에서 관심 주제 글만 골라 digest/YYYY-MM-DD.md 요약 파일을 만든다.

- 피드의 제목/요약만 사용한다 (기사 본문 페이지는 열지 않음).
- 요약은 Claude가 새로 쓴다:
    * ANTHROPIC_API_KEY(또는 ANTHROPIC_AUTH_TOKEN)가 있으면 Anthropic SDK 사용
    * 없으면 로그인된 `claude` CLI를 도구 없이(--tools "") 호출
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

FEED_URL = "https://news.hada.io/rss/news"
TOPICS = ["AI 에이전트", "업무 자동화", "클로드"]
MAX_ITEMS = 5
MODEL = "claude-opus-5-5"
OUT_DIR = Path(__file__).resolve().parent / "digest"

ATOM = "{http://www.w3.org/2005/Atom}"

SCHEMA = {
    "type": "object",
    "properties": {
        "three_line_summary": {"type": "array", "items": {"type": "string"}},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["index", "title", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["three_line_summary", "articles"],
    "additionalProperties": False,
}


def fetch_feed(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "rss-digest/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    items = []
    # Atom
    for e in root.iter(f"{ATOM}entry"):
        link_el = e.find(f"{ATOM}link[@rel='alternate']")
        if link_el is None:
            link_el = e.find(f"{ATOM}link")
        body = e.findtext(f"{ATOM}content") or e.findtext(f"{ATOM}summary") or ""
        items.append({
            "title": (e.findtext(f"{ATOM}title") or "").strip(),
            "link": e.findtext(f"{ATOM}id") or (link_el.get("href") if link_el is not None else ""),
            "summary": body,
        })
    # RSS 2.0
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "summary": it.findtext("description") or "",
        })
    for it in items:
        text = re.sub(r"<[^>]+>", " ", it["summary"])
        it["summary"] = re.sub(r"\s+", " ", html.unescape(text)).strip()[:600]
    return items


def build_prompt(items: list[dict]) -> str:
    lines = [f"[{i}] 제목: {it['title']}\n    피드 요약: {it['summary']}" for i, it in enumerate(items)]
    return (
        "아래는 RSS 피드의 글 목록(제목과 피드 요약)입니다.\n"
        f"관심 주제: {', '.join(TOPICS)}\n\n"
        "규칙:\n"
        f"- 관심 주제와 실제로 관련된 글만 최대 {MAX_ITEMS}건 고르세요. 없으면 articles를 빈 배열로 두세요.\n"
        "- 주어진 제목과 피드 요약만 근거로 쓰고, 없는 내용을 지어내지 마세요.\n"
        "- 각 글의 summary는 한국어 두 문장으로, 원문 문장을 길게 그대로 옮기지 말고 새로 쓰세요.\n"
        "- title은 원래 제목을 그대로 쓰고, index는 목록 번호입니다.\n"
        "- three_line_summary는 고른 글 전체를 아우르는 한국어 세 문장(배열 3개)입니다. 글이 없으면 빈 배열.\n\n"
        + "\n".join(lines)
    )


def summarize_with_sdk(prompt: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("모델이 요청을 거절했습니다.")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def summarize_with_cli(prompt: str) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--tools", "",                      # 도구 없음: 웹/파일 접근 불가
        "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True).stdout
    data = json.loads(out)
    if isinstance(data.get("structured_output"), dict):
        return data["structured_output"]
    result = data.get("result", "")
    m = re.search(r"\{.*\}", result, re.S)
    if not m:
        raise RuntimeError(f"CLI 응답을 해석하지 못했습니다: {result[:200]}")
    return json.loads(m.group(0))


def summarize(items: list[dict]) -> dict:
    prompt = build_prompt(items)
    has_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if has_key:
        try:
            return summarize_with_sdk(prompt)
        except ImportError:
            pass  # SDK 미설치 → CLI로
    if shutil.which("claude"):
        return summarize_with_cli(prompt)
    sys.exit("요약할 방법이 없습니다: ANTHROPIC_API_KEY 설정 후 `pip install anthropic`, 또는 claude CLI 로그인이 필요합니다.")


def render(items: list[dict], result: dict) -> tuple[str, int]:
    picked = []
    seen = set()
    for a in result.get("articles", []):
        i = a.get("index")
        if isinstance(i, int) and 0 <= i < len(items) and i not in seen:
            seen.add(i)
            picked.append((items[i], a["summary"].strip()))
        if len(picked) == MAX_ITEMS:
            break
    if not picked:
        return "해당 없음\n", 0

    md = [f"# {date.today().isoformat()} 다이제스트", "", "## 오늘의 세 줄 요약", ""]
    md += [f"{n}. {s.strip()}" for n, s in enumerate(result.get("three_line_summary", [])[:3], 1)]
    md += ["", "## 기사", ""]
    for it, summary in picked:
        md += [f"### {it['title']}", "", summary, "", f"원문: {it['link']}", ""]
    return "\n".join(md), len(picked)


def main() -> None:
    items = fetch_feed(FEED_URL)
    result = summarize(items) if items else {"articles": []}
    text, count = render(items, result)
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{date.today().isoformat()}.md"
    path.write_text(text, encoding="utf-8")  # 같은 날짜 파일은 덮어씀
    print(f"{path} 에 저장, 고른 기사 {count}건")


if __name__ == "__main__":
    main()
