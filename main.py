from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
import httpx
import json
import os

load_dotenv()

app = Flask(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

def groq(messages, max_tokens=1000):
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "temperature": 0.8,
                "max_tokens": max_tokens,
                "messages": messages
            },
        )
    return r.json()["choices"][0]["message"]["content"].strip().replace("json", "").replace("```", "").strip()


@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "*"
    return r


@app.route("/")
def root():
    return jsonify({"status": "MemeCraft AI is live 🔥", "version": "1.0.0"})


@app.route("/api/generate-meme", methods=["POST", "OPTIONS"])
def generate_meme():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not set"}), 500

    data = request.get_json()
    prompt = data.get("prompt", "")
    language = data.get("language", "English")
    templates = data.get("templates", [])

    template_list = "\n".join([f"{t['id']}:{t['name']}" for t in templates[:100]])

    system = f"""You are a viral meme expert. Return ONLY raw valid JSON, no markdown, no backticks.
{{
    "selectedTemplateIds": ["EXACT_ID_FROM_LIST","EXACT_ID_FROM_LIST","EXACT_ID_FROM_LIST","EXACT_ID_FROM_LIST"],
    "topText": "max 6 words",
    "bottomText": "max 6 words",
    "instagramCaption": "2-3 sentence caption with emojis",
    "hashtags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
    "improvements": ["tip1","tip2","tip3","tip4"]
}}
CRITICAL: selectedTemplateIds MUST be EXACT IDs copied from the template list below. NOT "id1" or "id2". REAL IDs only.
Pick templates that VISUALLY MATCH the topic. Example: two-choice topics = "Two Buttons" template.
All text in {language}. Meme text = SHORT PUNCHY MAX 6 WORDS. Hashtags without #."""
    raw = groq([
        {"role": "system", "content": system},
        {"role": "user", "content": f'Topic: "{prompt}"\nTemplates:\n{template_list}'},
    ])

    try:
        return jsonify(json.loads(raw))
    except Exception:
        return jsonify({
            "selectedTemplateIds": [],
            "topText": "When you realize",
            "bottomText": prompt[:40],
            "instagramCaption": f"{prompt} 😂 Tag someone who relates!",
            "hashtags": ["memes", "funny", "viral", "relatable", "lol", "trending", "memesdaily", "humor", "comedy", "funnymemes"],
            "improvements": ["Be more specific", "Add emotion", "Mention audience", "Add cultural refs"],
        })


@app.route("/api/templates")
def get_templates():
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get("https://api.imgflip.com/get_memes")
            data = r.json()
            if data.get("success"):
                return jsonify({"templates": data["data"]["memes"]})
    except Exception:
        pass
    return jsonify({"templates": [
        {"id": "181913649", "name": "Drake Hotline Bling", "url": "https://i.imgflip.com/30b1gx.jpg"},
        {"id": "87743020", "name": "Two Buttons", "url": "https://i.imgflip.com/1g8my4.jpg"},
        {"id": "112126428", "name": "Distracted Boyfriend", "url": "https://i.imgflip.com/1ur9b0.jpg"},
        {"id": "131087935", "name": "Running Away Balloon", "url": "https://i.imgflip.com/261o3j.jpg"},
        {"id": "93895088", "name": "Expanding Brain", "url": "https://i.imgflip.com/1jwhww.jpg"},
        {"id": "129242436", "name": "Change My Mind", "url": "https://i.imgflip.com/24y43o.jpg"},
    ]})


@app.route("/api/regenerate-caption", methods=["POST", "OPTIONS"])
def regenerate_caption():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not set"}), 500

    data = request.get_json()
    prompt = data.get("prompt", "")
    language = data.get("language", "English")

    raw = groq([
        {"role": "system", "content": f"Return ONLY raw JSON in {language}. No markdown.\n{{\"caption\": \"...\", \"hashtags\": [\"tag1\",\"tag2\"]}}"},
        {"role": "user", "content": f"Caption for meme about: {prompt}"},
    ], max_tokens=400)

    try:
        return jsonify(json.loads(raw))
    except Exception:
        return jsonify({
            "caption": f"{prompt} 😂 Tag someone who gets this!",
            "hashtags": ["memes", "funny", "viral", "trending", "relatable", "lol", "memesdaily", "humor", "comedy", "reels"],
        })


@app.route("/api/proxy-image")
def proxy_image():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
        return Response(
            r.content,
            content_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
