from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
import httpx
import json
import os
import re
import time
import random

load_dotenv()

app = Flask(__name__)

# ── ENV KEYS
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
TENOR_API_KEY = os.getenv("TENOR_API_KEY", "")   # get free at tenor.com/developer
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "")   # get free at developers.giphy.com

GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"
MODEL     = "llama-3.3-70b-versatile"

# ── CORS
@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "*"
    return r

# ── IN-MEMORY TEMPLATE CACHE
_cache = {
    "imgflip":  {"data": [], "ts": 0},
    "reddit":   {"data": [], "ts": 0},
    "tenor":    {"data": [], "ts": 0},
    "giphy":    {"data": [], "ts": 0},
}
CACHE_TTL = 3600  # 1 hour

# ─────────────────────────────────────────────
# TEMPLATE FETCHERS
# ─────────────────────────────────────────────

def fetch_imgflip():
    if time.time() - _cache["imgflip"]["ts"] < CACHE_TTL and _cache["imgflip"]["data"]:
        return _cache["imgflip"]["data"]
    try:
        with httpx.Client(timeout=8) as c:
            r = c.get("https://api.imgflip.com/get_memes")
            memes = r.json()["data"]["memes"]
            result = [{"id": f"imgflip_{m['id']}", "name": m["name"], "url": m["url"], "source": "imgflip", "tags": m["name"].lower().replace("-"," ").split()} for m in memes]
            _cache["imgflip"] = {"data": result, "ts": time.time()}
            return result
    except:
        return []

def fetch_reddit():
    if time.time() - _cache["reddit"]["ts"] < CACHE_TTL and _cache["reddit"]["data"]:
        return _cache["reddit"]["data"]
    subreddits = ["memes", "dankmemes", "IndianDankMemes", "desimemes", "me_irl", "Unexpected"]
    results = []
    headers = {"User-Agent": "MemeCraftAI/1.0"}
    try:
        with httpx.Client(timeout=10, headers=headers, follow_redirects=True) as c:
            for sub in subreddits:
                try:
                    r = c.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=50")
                    posts = r.json()["data"]["children"]
                    for p in posts:
                        d = p["data"]
                        url = d.get("url", "")
                        # Only image posts
                        if any(url.endswith(ext) for ext in [".jpg",".jpeg",".png",".gif",".webp"]):
                            results.append({
                                "id": f"reddit_{d['id']}",
                                "name": d.get("title","")[:60],
                                "url": url,
                                "source": "reddit",
                                "subreddit": sub,
                                "score": d.get("score", 0),
                                "tags": d.get("title","").lower().split()[:10],
                            })
                except:
                    continue
        # Sort by score (most popular first)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        _cache["reddit"] = {"data": results[:200], "ts": time.time()}
        return results[:200]
    except:
        return []

def fetch_tenor():
    if not TENOR_API_KEY:
        return []
    if time.time() - _cache["tenor"]["ts"] < CACHE_TTL and _cache["tenor"]["data"]:
        return _cache["tenor"]["data"]
    queries = ["funny meme", "reaction meme", "desi meme", "india meme", "student meme", "work meme", "relatable"]
    results = []
    try:
        with httpx.Client(timeout=8) as c:
            for q in queries:
                try:
                    r = c.get(f"https://tenor.googleapis.com/v2/search?q={q}&key={TENOR_API_KEY}&limit=20&media_filter=gif")
                    for item in r.json().get("results", []):
                        gif_url = item.get("media_formats", {}).get("gif", {}).get("url", "")
                        if gif_url:
                            results.append({
                                "id": f"tenor_{item['id']}",
                                "name": item.get("content_description", q)[:60],
                                "url": gif_url,
                                "source": "tenor",
                                "tags": (item.get("tags") or []) + q.split(),
                                "isGif": True,
                            })
                except:
                    continue
        _cache["tenor"] = {"data": results, "ts": time.time()}
        return results
    except:
        return []

def fetch_giphy():
    if not GIPHY_API_KEY:
        return []
    if time.time() - _cache["giphy"]["ts"] < CACHE_TTL and _cache["giphy"]["data"]:
        return _cache["giphy"]["data"]
    queries = ["funny", "reaction", "meme", "india", "student life", "monday", "work"]
    results = []
    try:
        with httpx.Client(timeout=8) as c:
            for q in queries:
                try:
                    r = c.get(f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={q}&limit=20&rating=g")
                    for item in r.json().get("data", []):
                        gif_url = item.get("images",{}).get("fixed_height",{}).get("url","")
                        if gif_url:
                            results.append({
                                "id": f"giphy_{item['id']}",
                                "name": item.get("title", q)[:60],
                                "url": gif_url,
                                "source": "giphy",
                                "tags": q.split() + item.get("title","").lower().split()[:5],
                                "isGif": True,
                            })
                except:
                    continue
        _cache["giphy"] = {"data": results, "ts": time.time()}
        return results
    except:
        return []

# ─────────────────────────────────────────────
# SMART SEMANTIC MATCHING ENGINE
# ─────────────────────────────────────────────

def get_all_templates():
    """Merge all sources into one pool"""
    imgflip = fetch_imgflip()
    reddit  = fetch_reddit()
    tenor   = fetch_tenor()
    giphy   = fetch_giphy()
    return imgflip + reddit + tenor + giphy

def semantic_score(template, ai_tags, prompt_words):
    """Score a template against AI-generated tags"""
    score = 0
    t_tags  = [str(t).lower() for t in (template.get("tags") or [])]
    t_name  = template.get("name","").lower()
    t_src   = template.get("source","")

    for tag in ai_tags:
        tag = tag.lower().strip()
        if tag in t_name:
            score += 12
        if tag in t_tags:
            score += 8
        # Partial match
        for tt in t_tags:
            if tag in tt or tt in tag:
                score += 3

    for word in prompt_words:
        word = word.lower()
        if len(word) > 3:
            if word in t_name:
                score += 6
            for tt in t_tags:
                if word in tt:
                    score += 2

    # Source bonuses
    if t_src == "imgflip": score += 5   # Classic templates are reliable
    if t_src == "reddit":  score += 3   # Real memes, popular
    if t_src == "tenor":   score += 1
    if t_src == "giphy":   score += 1

    # Popularity bonus for reddit
    reddit_score = template.get("score", 0)
    if reddit_score > 10000: score += 4
    elif reddit_score > 1000: score += 2

    return score

def smart_match_templates(prompt, ai_tags, count=8):
    """Main matching function"""
    all_templates = get_all_templates()
    if not all_templates:
        return []

    prompt_words = prompt.lower().split()

    # Score all templates
    scored = []
    for t in all_templates:
        s = semantic_score(t, ai_tags, prompt_words)
        if s > 0:
            scored.append((s, t))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top results with some variety (mix sources)
    top = [t for _, t in scored[:50]]

    # Ensure source variety in final 4
    result = []
    sources_used = []
    for t in top:
        src = t.get("source")
        if len(result) < count:
            result.append(t)
            sources_used.append(src)

    # If not enough, fill with random from pool
    if len(result) < count:
        extras = [t for t in all_templates if t not in result]
        random.shuffle(extras)
        result.extend(extras[:count - len(result)])

    return result[:count]

# ─────────────────────────────────────────────
# GROQ HELPER
# ─────────────────────────────────────────────

def call_groq(messages, max_tokens=1000):
    with httpx.Client(timeout=30) as c:
        r = c.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "temperature": 0.8, "max_tokens": max_tokens, "messages": messages},
        )
    return r.json()["choices"][0]["message"]["content"].strip().replace("```json","").replace("```","").strip()

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def root():
    total = len(get_all_templates())
    return jsonify({
        "status": "MemeCraft AI is live 🔥",
        "version": "2.0.0",
        "templates_available": total,
        "sources": ["imgflip", "reddit", "tenor", "giphy"]
    })

@app.route("/api/templates")
def get_templates():
    """Returns merged templates from all sources"""
    all_t = get_all_templates()
    # Return sample for frontend fallback display
    return jsonify({
        "templates": all_t[:150],
        "total": len(all_t),
        "sources": {
            "imgflip": len([t for t in all_t if t.get("source")=="imgflip"]),
            "reddit":  len([t for t in all_t if t.get("source")=="reddit"]),
            "tenor":   len([t for t in all_t if t.get("source")=="tenor"]),
            "giphy":   len([t for t in all_t if t.get("source")=="giphy"]),
        }
    })

@app.route("/api/generate-meme", methods=["POST","OPTIONS"])
def generate_meme():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not set"}), 500

    data     = request.get_json()
    prompt   = data.get("prompt", "")
    language = data.get("language", "English")

    if not prompt.strip():
        return jsonify({"error": "Prompt empty"}), 400

    # ── Step 1: AI generates semantic tags + content
    system = f"""You are a viral meme expert. Return ONLY raw JSON, no markdown.
{{
  "semanticTags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
  "topText": "max 6 words punchy",
  "bottomText": "max 6 words punchy",
  "instagramCaption": "2-3 sentence caption with emojis",
  "hashtags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
  "improvements": ["tip1","tip2","tip3","tip4"]
}}

semanticTags = keywords describing the EMOTION, SITUATION, and VISUAL of the meme.
Example for "Monday morning": ["monday","morning","tired","coffee","work","struggle","office","alarm","sleep","weekend"]
All text in {language}. Meme text SHORT + PUNCHY. Hashtags without #."""

    try:
        raw  = call_groq([
            {"role": "system", "content": system},
            {"role": "user",   "content": f'Generate meme content for: "{prompt}"'},
        ])
        d = json.loads(raw)
    except:
        d = {
            "semanticTags": prompt.lower().split()[:10],
            "topText": "When you realize",
            "bottomText": prompt[:30],
            "instagramCaption": f"{prompt} 😂 Tag someone!",
            "hashtags": ["memes","funny","viral","relatable","lol","trending","memesdaily","humor","comedy","funnymemes"],
            "improvements": ["Be specific","Add emotion","Mention audience","Add cultural refs"],
        }

    # ── Step 2: Smart semantic template matching
    ai_tags   = d.get("semanticTags", [])
    templates = smart_match_templates(prompt, ai_tags, count=8)

    # Return top 4 template IDs + full template data
    top4 = templates[:4]

    return jsonify({
        "selectedTemplateIds": [t["id"] for t in top4],
        "templates": top4,  # Full template objects with URLs
        "topText":          d.get("topText", ""),
        "bottomText":       d.get("bottomText", ""),
        "instagramCaption": d.get("instagramCaption", ""),
        "hashtags":         d.get("hashtags", []),
        "improvements":     d.get("improvements", []),
        "semanticTags":     ai_tags,
        "totalTemplatesSearched": len(get_all_templates()),
    })

@app.route("/api/regenerate-caption", methods=["POST","OPTIONS"])
def regenerate_caption():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not set"}), 500

    data     = request.get_json()
    prompt   = data.get("prompt", "")
    language = data.get("language", "English")

    try:
        raw = call_groq([
            {"role": "system", "content": f"Return ONLY raw JSON in {language}. No markdown.\n{{\"caption\": \"...\", \"hashtags\": [\"tag1\",\"tag2\",\"tag3\",\"tag4\",\"tag5\",\"tag6\",\"tag7\",\"tag8\",\"tag9\",\"tag10\"]}}"},
            {"role": "user",   "content": f"Caption for meme about: {prompt}"},
        ], max_tokens=400)
        return jsonify(json.loads(raw))
    except:
        return jsonify({
            "caption": f"{prompt} 😂 Tag someone who gets this!",
            "hashtags": ["memes","funny","viral","trending","relatable","lol","memesdaily","humor","comedy","reels"],
        })

@app.route("/api/proxy-image")
def proxy_image():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "MemeCraftAI/1.0"})
            return Response(r.content, content_type=r.headers.get("content-type","image/jpeg"),
                          headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cache-stats")
def cache_stats():
    """Debug endpoint to check template counts"""
    return jsonify({
        "imgflip": len(_cache["imgflip"]["data"]),
        "reddit":  len(_cache["reddit"]["data"]),
        "tenor":   len(_cache["tenor"]["data"]),
        "giphy":   len(_cache["giphy"]["data"]),
        "total":   sum(len(_cache[k]["data"]) for k in _cache),
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

