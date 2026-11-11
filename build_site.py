#!/usr/bin/env python3
"""digest/*.md 의 기사들을 카드 한 장씩으로 보여 주는 정적 페이지(site/index.html)를 만든다.

실행: python3 build_site.py && python3 -m http.server 8000 --bind 127.0.0.1 -d site
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "digest"
OUT = ROOT / "site"

CSS = """
:root{
  --grey-50:oklch(0.985 0.002 248);--grey-100:oklch(0.966 0.003 248);--grey-200:oklch(0.930 0.005 248);
  --grey-500:oklch(0.666 0.021 253);--grey-600:oklch(0.562 0.025 254);--grey-700:oklch(0.460 0.028 256);
  --grey-900:oklch(0.237 0.020 258);--blue-500:oklch(0.620 0.191 258);--blue-50:oklch(0.959 0.020 250);
  --bg:var(--grey-100);--surface:oklch(1 0 0);--line:oklch(0 0 0 / 0.08);
  --text:var(--grey-900);--text-2:var(--grey-700);--text-3:var(--grey-600);
  --accent:var(--blue-500);--accent-weak:var(--blue-50);--badge:var(--grey-100);
  --press:oklch(0 0 0 / 0.06);
  --shadow:0 1px 2px oklch(0.155 0.060 261 / 0.04),0 1px 1px oklch(0.155 0.060 261 / 0.04);
  --ease:cubic-bezier(0.22,0.61,0.36,1);
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root{
  --bg:oklch(0.174 0.006 286);--surface:oklch(0.247 0.013 285);--line:oklch(0.361 0.019 285);
  --text:oklch(1 0 0);--text-2:oklch(0.818 0.004 286);--text-3:oklch(0.701 0.009 286);
  --accent:oklch(0.700 0.160 258);--accent-weak:oklch(0.300 0.062 267);--badge:oklch(0.297 0.016 285);
  --press:oklch(1 0 0 / 0.06);--shadow:none;color-scheme:dark;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  font-size:15px;line-height:1.5;letter-spacing:-0.005em;-webkit-font-smoothing:antialiased}
main{max-width:640px;margin:0 auto;padding:40px 16px 80px}
.page-title{font-size:28px;font-weight:700;line-height:1.3;letter-spacing:-0.02em;margin:0 0 4px}
.page-sub{color:var(--text-3);margin:0 0 24px}
.cards{display:flex;flex-direction:column;gap:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:24px;padding:24px;
  box-shadow:var(--shadow)}
.meta{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.badge{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:6px;
  background:var(--badge);color:var(--text-3);font-size:12px;font-weight:500;font-variant-numeric:tabular-nums}
.card h2{font-size:18px;font-weight:600;line-height:1.45;letter-spacing:-0.01em;margin:0 0 8px;word-break:keep-all}
.card p{color:var(--text-2);margin:0 0 16px;word-break:keep-all}
.link{display:inline-flex;align-items:center;gap:4px;min-height:44px;padding:0 16px;margin-left:-16px;
  border-radius:12px;color:var(--accent);font-weight:600;text-decoration:none;
  transition:background-color 120ms var(--ease)}
.link:hover{background:var(--accent-weak)}
.link:active{background:var(--press)}
.link:focus-visible{outline:1.5px solid var(--accent);outline-offset:2px}
.empty{background:var(--surface);border-radius:24px;padding:40px 24px;text-align:center;color:var(--text-3)}
"""


def parse_articles(md: str) -> list[dict]:
    """digest 형식에서 기사(### 제목 / 요약 문단 / 원문: URL)만 뽑는다."""
    articles, cur = [], None
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("### "):
            cur = {"title": s[4:], "summary": [], "link": ""}
            articles.append(cur)
        elif s.startswith("#"):
            cur = None
        elif cur and s.startswith("원문:"):
            cur["link"] = s.split(":", 1)[1].strip()
        elif cur and s:
            cur["summary"].append(s)
    return articles


def card(date: str, a: dict) -> str:
    e = html.escape
    link = (
        f'<a class="link" href="{e(a["link"])}" target="_blank" rel="noopener">원문 보기 <span aria-hidden="true">›</span></a>'
        if a["link"].startswith(("http://", "https://")) else ""
    )
    return (
        '<article class="card">'
        f'<div class="meta"><span class="badge">{e(date)}</span></div>'
        f'<h2>{e(a["title"])}</h2>'
        f'<p>{e(" ".join(a["summary"]))}</p>'
        f"{link}</article>"
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.html"):  # 예전 날짜별 페이지 정리 (site/ 안에서만)
        old.unlink()

    cards = []
    for f in sorted(SRC.glob("*.md"), reverse=True) if SRC.exists() else []:
        cards += [card(f.stem, a) for a in parse_articles(f.read_text(encoding="utf-8"))]

    body = "\n".join(cards) if cards else '<div class="empty">아직 요약된 뉴스가 없어요</div>'
    page = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>뉴스 요약</title>"
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">'
        f"<style>{CSS}</style></head><body><main>"
        '<h1 class="page-title">뉴스 요약</h1>'
        f'<p class="page-sub">관심 주제 기사 {len(cards)}건을 모았어요</p>'
        f'<div class="cards">{body}</div>'
        "</main></body></html>"
    )
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print(f"{OUT / 'index.html'} 생성, 카드 {len(cards)}장")


if __name__ == "__main__":
    main()
