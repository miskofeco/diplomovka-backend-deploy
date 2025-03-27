from flask import Flask, request, jsonify
from flask_cors import CORS
from scraping.scraping import scrape_for_new_articles
from data.db import SessionLocal
from sqlalchemy import text

app = Flask(__name__)
CORS(app)  # povolí prístup z frontendu

@app.route("/api/articles", methods=["GET"])
def get_articles():
    session = SessionLocal()
    result = session.execute(
        text("SELECT title, intro, summary, url, category, tags, top_image, scraped_at FROM articles ORDER BY id DESC")
    )
    articles = [{
        "title": r[0],
        "intro": r[1],
        "summary": r[2],
        "url": r[3],
        "category": r[4],
        "tags": r[5],
        "top_image": r[6],
        "scraped_at": r[7],
    } for r in result.fetchall()]
    return jsonify(articles)

@app.route("/api/scrape", methods=["POST"])
def scrape_articles():
    scrape_for_new_articles()
    return jsonify({"message": "Scraping completed"})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)