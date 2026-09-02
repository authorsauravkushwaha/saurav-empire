import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_books, load_heroes, load_course, save_json, daily_path, today_str
from utils.ai_router import ai_reason
def generate_reel_hook(book: dict, trend_keywords: list) -> dict:
    # Use book data from heroes + books merged, or fallback to books
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    price = book.get('price_inr', 199)
    prompt = f'''Create a 15-30 second Instagram Reel hook for this book:
Title: {title}
Category: {book.get('category', 'General')}
Hook: {hook}
Price: ₹{price}
Trending keywords: {', '.join(trend_keywords[:5])}
Return JSON:
- hook: opening 3 seconds (visual + audio)
- script: 30-second script with timestamps
- cta: call to action (link in bio / comment / save)
- hashtags: 10 relevant tags
- caption: full Instagram caption
'''
    response = ai_reason(prompt, 'You are a viral Reels scriptwriter. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'hook': 'ERROR', 'script': 'Parse failed', 'cta': '', 'hashtags': [], 'caption': ''}
def generate_short_script(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    prompt = f'''Create a 60-second YouTube Short script for this book:
Title: {title}
Category: {category}
Hook: {hook}
Trending: {', '.join(trend_keywords[:5])}
Return JSON:
- title: catchy Short title (<60 chars)
- script: 60-second script with visual cues
- cta: subscribe / link in description
- hashtags: 10 tags
- description: YouTube description
'''
    response = ai_reason(prompt, 'You are a YouTube Shorts expert. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'title': 'ERROR', 'script': 'Parse failed', 'cta': '', 'hashtags': [], 'description': ''}
def generate_tweet_thread(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    prompt = f'''Create a viral Twitter/X thread (8-12 tweets) for this book:
Title: {title}
Category: {category}
Hook: {hook}
Trending: {', '.join(trend_keywords[:5])}
Return JSON:
- tweets: array of tweet texts (each <280 chars)
- final_cta: tweet with Gumroad link placeholder
- hashtags: 5 tags
'''
    response = ai_reason(prompt, 'You are a Twitter growth strategist. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'tweets': ['ERROR'], 'final_cta': '', 'hashtags': []}
def generate_blog_outline(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    prompt = f'''Create an SEO blog post outline targeting this book:
Title: {title}
Category: {category}
Hook: {hook}
Trending keywords: {', '.join(trend_keywords[:5])}
Return JSON:
- title: SEO-optimized title (<60 chars)
- target_keyword: primary keyword
- secondary_keywords: 5 related
- outline: array of {{heading, word_count, key_points}}
- meta_description: <160 chars
- internal_links: 3 other book titles to link
'''
    response = ai_reason(prompt, 'You are an SEO content strategist. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'title': 'ERROR', 'target_keyword': '', 'secondary_keywords': [], 'outline': [], 'meta_description': '', 'internal_links': []}
def generate_email_draft(heroes: list, trend_keywords: list) -> dict:
    top_heroes = heroes[:3]
    books_context = '\n'.join([f"- {h['title']}: {h['content_angles'][0]}" for h in top_heroes])
    prompt = f'''
Write a welcome/indocrination email (email #2 of sequence) for new subscribers.
Author: Saurav Kushwaha (50 books, finance/psychology/writing/business)
Top books this week:
{books_context}
Trending topics: {', '.join(trend_keywords[:5])}
Return JSON:
- subject: 3 variants (A/B test)
- preview_text: <90 chars
- body: full email HTML (personalized, story-driven, one clear CTA)
- cta_text: button text
- cta_url: placeholder (Gumroad product)
'''
    response = ai_reason(prompt, 'You are an email copywriter. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'subject': ['ERROR'], 'preview_text': '', 'body': '', 'cta_text': '', 'cta_url': ''}
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    print(f'[{datetime.now(IST)}] Content Generation starting...')
    books = load_books()
    heroes = load_heroes()
    course = load_course()
    trends = {}
    try:
        import json
        with open(Path(__file__).parent.parent.parent / 'data/trends.json', 'r') as f:
            trends = json.load(f).get('analysis', {})
    except:
        trends = {}
    trend_keywords = trends.get('top_keywords', ['writing', 'money', 'mindset', 'productivity', 'books'])
    
    # Merge hero data with full book data from books.json
    books_by_asin = {b['asin']: b for b in books}
    enriched_heroes = []
    for h in heroes:
        book_data = books_by_asin.get(h['asin'], {})
        enriched = {**h, 'category': book_data.get('category', 'General'), 'price_inr': book_data.get('price_inr', 199), 'hook': h.get('content_angles', [''])[0] if h.get('content_angles') else ''}
        enriched_heroes.append(enriched)
    
    day_num = int(today_str().split('-')[2])
    selected_books = enriched_heroes[day_num % len(enriched_heroes):day_num % len(enriched_heroes) + 3]
    if len(selected_books) < 3:
        selected_books = enriched_heroes[:3]
    reels = [generate_reel_hook(b, trend_keywords) for b in selected_books[:3]]
    short = generate_short_script(selected_books[0], trend_keywords)
    thread = generate_tweet_thread(selected_books[1], trend_keywords)
    blog = generate_blog_outline(selected_books[2], trend_keywords)
    email = generate_email_draft(enriched_heroes, trend_keywords)
    date_dir = Path(__file__).parent.parent.parent / 'content' / 'daily' / today_str()
    date_dir.mkdir(parents=True, exist_ok=True)
    save_json(f'content/daily/{today_str()}/reels.json', reels)
    save_json(f'content/daily/{today_str()}/shorts.json', [short])
    save_json(f'content/daily/{today_str()}/tweets.json', thread)
    save_json(f'content/daily/{today_str()}/blog.json', blog)
    save_json(f'content/daily/{today_str()}/email.json', email)
    print(f'[{datetime.now(IST)}] Content Generation complete → content/daily/{today_str()}/')
if __name__ == '__main__':
    main()
