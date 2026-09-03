import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_policy, save_json, daily_path, today_str, get_env
from utils.ai_router import ai_reason
IST = timezone(timedelta(hours=5, minutes=30))
TREND_SOURCES = {
    'google_trends_in': 'https://trends.google.com/trends/api/dailytrends?hl=en-IN&geo=IN',
    'reddit_entrepreneur': 'https://www.reddit.com/r/Entrepreneur/hot.json?limit=25',
    'reddit_selfpublish': 'https://www.reddit.com/r/selfpublish/hot.json?limit=25',
    'reddit_writing': 'https://www.reddit.com/r/writing/hot.json?limit=25',
    'amazon_bestsellers_finance': 'https://www.amazon.in/gp/bestsellers/digital-text/1571271031',
}
def fetch_google_trends() -> list:
    try:
        r = requests.get(TREND_SOURCES['google_trends_in'], timeout=10)
        text = r.text
        start = text.find('{')
        end = text.rfind('}') + 1
        data = json.loads(text[start:end])
        trends = []
        for topic in data.get('default', {}).get('trendingSearchesDays', [{}])[0].get('trendingSearches', [])[:10]:
            trends.append({
                'source': 'google_trends',
                'keyword': topic.get('title', {}).get('query', ''),
                'traffic': topic.get('formattedTraffic', ''),
                'related': [r.get('query', '') for r in topic.get('relatedQueries', [])[:3]]
            })
        return trends
    except Exception as e:
        return [{'source': 'google_trends', 'error': str(e)}]
def fetch_reddit(subreddit: str) -> list:
    url = TREND_SOURCES.get(f'reddit_{subreddit}', '')
    if not url:
        return []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        posts = []
        for post in data.get('data', {}).get('children', [])[:15]:
            p = post.get('data', {})
            posts.append({
                'source': f'reddit_{subreddit}',
                'title': p.get('title', ''),
                'score': p.get('score', 0),
                'comments': p.get('num_comments', 0),
                'url': f"https://reddit.com{p.get('permalink', '')}",
                'selftext': p.get('selftext', '')[:500]
            })
        return posts
    except Exception as e:
        return [{'source': f'reddit_{subreddit}', 'error': str(e)}]
def fetch_amazon_bestsellers() -> list:
    return [{'source': 'amazon_bestsellers', 'note': 'Manual CSV import needed'}]
def analyze_with_ai(raw_data: dict) -> dict:
    policy = load_policy()
    prompt = f'''
Analyze these market signals for a self-publishing author (50 books in finance, psychology, writing, business, poetry, relationships, society).
RAW DATA:
{json.dumps(raw_data, indent=2)[:3000]}
Return JSON with:
- top_keywords (10): trending search terms
- content_gaps (5): topics competitors miss
- audience_questions (10): what readers ask
- recommended_angles (5): content hooks for our books
- urgency_score (1-10): how time-sensitive
'''
    try:
        response = ai_reason(prompt, 'You are a market intelligence analyst. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {'error': f'AI analysis failed: {e}', 'top_keywords': [], 'content_gaps': []}
def main():
    print(f'[{datetime.now(IST)}] Market Scan starting...')
    raw = {
        'google_trends': fetch_google_trends(),
        'reddit_entrepreneur': fetch_reddit('entrepreneur'),
        'reddit_selfpublish': fetch_reddit('selfpublish'),
        'reddit_writing': fetch_reddit('writing'),
        'amazon_bestsellers': fetch_amazon_bestsellers(),
        'timestamp': datetime.now(IST).isoformat()
    }
    # Filter out error entries for AI analysis
    clean_raw = {}
    for key, value in raw.items():
        if key != 'timestamp':
            clean_raw[key] = [item for item in value if 'error' not in item]
    # If all sources failed, still call AI with empty data for deterministic fallback
    analysis = analyze_with_ai(clean_raw)
    output = {
        'date': today_str(),
        'raw_signals': raw,
        'analysis': analysis
    }
    save_json('data/trends.json', output)
    print(f'[{datetime.now(IST)}] Market Scan complete → data/trends.json')
if __name__ == '__main__':
    main()
