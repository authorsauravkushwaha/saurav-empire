import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_books, load_heroes, load_course, save_json, daily_path, today_str

def _local_reel_hook(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    price = book.get('price_inr', 199)
    
    hooks = [
        f"Stop writing books nobody reads. Here's the 30-day system that got me 50+ published.",
        f"Most authors fail because they write what THEY want, not what READERS want.",
        f"This book outline template helped me publish 50+ books. Here's the exact structure.",
        f"The pricing mistake that costs authors ₹50k+ per book. Don't make it.",
        f"I wrote 50 books while you're still 'researching'. Here's the system.",
    ]
    hook_text = hooks[hash(title) % len(hooks)]
    
    scripts = [
        f"0-3s: Hook - {hook_text}\n3-10s: Show the 5-phase system on screen\n10-20s: Walk through each phase with visuals\n20-25s: Show your 50-book shelf\n25-30s: CTA",
        f"0-3s: Hook - {hook_text}\n3-15s: Show the #1 mistake authors make\n15-25s: Reveal the research-first method\n25-30s: CTA with free template",
    ]
    
    ctas = [
        "🎓 Free lesson: 'Write & Publish in 30 Days' → Link in bio",
        "📋 Free outline template → Link in bio",
        "📚 Get my 50-book system → Link in bio",
    ]
    
    hashtags = ["#writerlife", "#selfpublishing", "#authorlife", "#bookmarketing", "#writeyourbook", "#30daybook", "#authorlife", "#indieauthor", "#kdp", "#booklaunch"]
    
    return {
        'hook': hooks[0],
        'script': scripts[0],
        'cta': ctas[0],
        'hashtags': hashtags,
        'caption': f"{hooks[0]}\n\nThe 5-phase system that published 50+ books:\n\nPhase 1: Research (Days 1-7)\nPhase 2: Outline (Days 8-14)\nPhase 3: Draft (Days 15-21)\nPhase 4: Edit (Days 22-26)\nPhase 5: Publish (Days 27-30)\n\nWant the full system? Free lesson in bio 👆\n\n#writerlife #selfpublishing #authorlife #bookmarketing #writeyourbook #30daybook #authorlife #indieauthor #kdp #booklaunch"
    }

def _local_short_script(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    return {
        'title': f"How I Published 50 Books in 30 Days Each",
        'script': "0-3s: Hook - 50 books, one system\n3-10s: Phase 1-5 breakdown\n10-20s: Show real results\n20-50s: Step-by-step walkthrough\n50-60s: CTA - Free course link",
        'cta': "🎓 Free lesson → Link in description",
        'hashtags': ["#shorts", "#writerlife", "#selfpublishing", "#authorlife", "#booktips"],
        'description': "The exact 30-day system that helped me publish 50+ books. Free lesson in bio."
    }

def _local_tweet_thread(book: dict, trend_keywords: list) -> dict:
    tweets = [
        "1/ Most authors fail because they write what THEY want, not what READERS want.",
        "2/ The fix: Research trending topics in your genre FIRST. Then write to that demand.",
        "3/ My 50-book catalog proves this works. Every book started with market research.",
        "4/ Phase 1: Find 50+ keywords readers actually search for. Use Amazon autosuggest + Google Trends.",
        "5/ Phase 2: Outline to match those keywords. Every chapter answers a reader question.",
        "6/ Phase 3: Write 2000 words/day. Don't edit. Just draft. System > motivation.",
        "7/ Phase 4: Edit in passes. Structure → Clarity → Polish. 3 passes max.",
        "8/ Phase 5: Launch with 50+ reviews ready. KDP Select + Amazon ads $5/day.",
        "9/ Want the full system? My 'Write & Publish in 30 Days' course shows every step.",
        "10/ Free lesson in bio. Stop guessing. Start publishing. 🚀",
    ]
    return {
        'tweets': tweets,
        'final_cta': "Free lesson: 'Write & Publish in 30 Days' → Link in bio",
        'hashtags': ["#writerlife", "#selfpublishing", "#authorlife", "#bookmarketing", "#writeyourbook"]
    }

def _local_blog_outline(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'How to Write & Publish a Book')
    return {
        'title': f"How to Write & Publish a Book in 30 Days: The Complete System",
        'target_keyword': "write and publish a book",
        'secondary_keywords': ["self publishing", "write a book fast", "book publishing process", "KDP guide", "author marketing"],
        'outline': [
            {"heading": "Introduction: Why 99% of Manuscripts Never Publish", "word_count": 300, "key_points": ["The dream vs reality", "The system difference", "My 50-book proof"]},
            {"heading": "Phase 1: Market Research (Days 1-7)", "word_count": 800, "key_points": ["Keyword validation", "Competitor analysis", "Reader avatar", "Category selection"]},
            {"heading": "Phase 2: Outline & Structure (Days 8-14)", "word_count": 800, "key_points": ["Chapter framework", "Reader journey map", "Hook per chapter", "Word count targets"]},
            {"heading": "Phase 3: Fast Drafting (Days 15-21)", "word_count": 1000, "key_points": ["2000 words/day system", "No editing while drafting", "Overcoming blocks", "Tracking progress"]},
            {"heading": "Phase 4: Edit & Polish (Days 22-26)", "word_count": 800, "key_points": ["3-pass edit system", "Professional editing", "Cover design", "Formatting"]},
            {"heading": "Phase 5: Publish & Launch (Days 27-30)", "word_count": 800, "key_points": ["KDP setup", "Launch team", "Amazon ads", "Review strategy"]},
            {"heading": "Conclusion: Your Author Business Starts Now", "word_count": 300, "key_points": ["Beyond book 1", "Building a catalog", "Multiple income streams", "Course + coaching"]},
        ],
        'meta_description': "Learn the exact 30-day system to write and publish your book. 50+ books published using this method. Free template included.",
        'internal_links': ["How to Outline a Book in 2 Hours", "KDP Select: My Honest Review", "Amazon Ads for Authors: $5/Day Strategy"]
    }

def _local_email_draft(heroes: list, trend_keywords: list) -> dict:
    return {
        'subject': [
            "The 30-day book system (50 books prove it works)",
            "Free: My exact book outline template",
            "Why most authors fail (and how to fix it)"
        ],
        'preview_text': "The system that published 50+ books in 30 days each...",
        'body': """
        <h2>The 30-Day Book System</h2>
        <p>Most writers spend years on one book. I published 50+ in the same time.</p>
        <p>The difference? A repeatable system.</p>
        <p><strong>Phase 1 (Days 1-7):</strong> Market research & keyword validation</p>
        <p><strong>Phase 2 (Days 8-14):</strong> Detailed outline & structure</p>
        <p><strong>Phase 3 (Days 15-21):</strong> Fast drafting (2000 words/day)</p>
        <p><strong>Phase 4 (Days 22-26):</strong> Edit & polish</p>
        <p><strong>Phase 5 (Days 27-30):</strong> Publish & launch</p>
        <p><a href="https://writernation.com/course" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Get Free Lesson →</a></p>
        <p>Write on,<br>Saurav</p>
        """,
        'cta_text': "Get Free Lesson",
        'cta_url': "https://writernation.com/course"
    }

def generate_reel_hook(book: dict, trend_keywords: list) -> dict:
    return _local_reel_hook(book, trend_keywords)

def _local_reel_hook(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    category = book.get('category', 'General')
    hook = book.get('hook', book.get('content_angles', [''])[0] if book.get('content_angles') else '')
    price = book.get('price_inr', 199)
    
    hooks = [
        f"Stop writing books nobody reads. Here's the 30-day system that got me 50+ published.",
        f"Most authors fail because they write what THEY want, not what READERS want.",
        f"This book outline template helped me publish 50+ books. Here's the exact structure.",
        f"The pricing mistake that costs authors ₹50k+ per book. Don't make it.",
        f"I wrote 50 books while you're still 'researching'. Here's the system.",
    ]
    hook_text = hooks[hash(title) % len(hooks)]
    
    scripts = [
        f"0-3s: Hook - {hook_text}\n3-10s: Show the 5-phase system on screen\n10-20s: Walk through each phase with visuals\n20-25s: Show your 50-book shelf\n25-30s: CTA",
        f"0-3s: Hook - {hook_text}\n3-15s: Show the #1 mistake authors make\n15-25s: Reveal the research-first method\n25-30s: CTA with free template",
    ]
    
    ctas = [
        "🎓 Free lesson: 'Write & Publish in 30 Days' → Link in bio",
        "📋 Free outline template → Link in bio",
        "📚 Get my 50-book system → Link in bio",
    ]
    
    hashtags = ["#writerlife", "#selfpublishing", "#authorlife", "#bookmarketing", "#writeyourbook", "#30daybook", "#authorlife", "#indieauthor", "#kdp", "#booklaunch"]
    
    return {
        'hook': hooks[0],
        'script': scripts[0],
        'cta': ctas[0],
        'hashtags': hashtags,
        'caption': f"{hooks[0]}\n\nThe 5-phase system that published 50+ books:\n\nPhase 1: Research (Days 1-7)\nPhase 2: Outline (Days 8-14)\nPhase 3: Draft (Days 15-21)\nPhase 4: Edit (Days 22-26)\nPhase 5: Publish (Days 27-30)\n\nWant the full system? Free lesson in bio 👆\n\n#writerlife #selfpublishing #authorlife #bookmarketing #writeyourbook #30daybook #authorlife #indieauthor #kdp #booklaunch"
    }

def generate_short_script(book: dict, trend_keywords: list) -> dict:
    return _local_short_script(book, trend_keywords)

def _local_short_script(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'Unknown')
    return {
        'title': f"How I Published 50 Books in 30 Days Each",
        'script': "0-3s: Hook - 50 books, one system\n3-10s: Phase 1-5 breakdown\n10-20s: Show real results\n20-50s: Step-by-step walkthrough\n50-60s: CTA - Free course link",
        'cta': "🎓 Free lesson → Link in description",
        'hashtags': ["#shorts", "#writerlife", "#selfpublishing", "#authorlife", "#booktips"],
        'description': "The exact 30-day system that helped me publish 50+ books. Free lesson in bio."
    }

def generate_tweet_thread(book: dict, trend_keywords: list) -> dict:
    return _local_tweet_thread(book, trend_keywords)

def _local_tweet_thread(book: dict, trend_keywords: list) -> dict:
    tweets = [
        "1/ Most authors fail because they write what THEY want, not what READERS want.",
        "2/ The fix: Research trending topics in your genre FIRST. Then write to that demand.",
        "3/ My 50-book catalog proves this works. Every book started with market research.",
        "4/ Phase 1: Find 50+ keywords readers actually search for. Use Amazon autosuggest + Google Trends.",
        "5/ Phase 2: Outline to match those keywords. Every chapter answers a reader question.",
        "6/ Phase 3: Write 2000 words/day. Don't edit. Just draft. System > motivation.",
        "7/ Phase 4: Edit in passes. Structure → Clarity → Polish. 3 passes max.",
        "8/ Phase 5: Launch with 50+ reviews ready. KDP Select + Amazon ads $5/day.",
        "9/ Want the full system? My 'Write & Publish in 30 Days' course shows every step.",
        "10/ Free lesson in bio. Stop guessing. Start publishing. 🚀",
    ]
    return {
        'tweets': tweets,
        'final_cta': "Free lesson: 'Write & Publish in 30 Days' → Link in bio",
        'hashtags': ["#writerlife", "#selfpublishing", "#authorlife", "#bookmarketing", "#writeyourbook"]
    }

def generate_blog_outline(book: dict, trend_keywords: list) -> dict:
    return _local_blog_outline(book, trend_keywords)

def _local_blog_outline(book: dict, trend_keywords: list) -> dict:
    title = book.get('title', 'How to Write & Publish a Book')
    return {
        'title': f"How to Write & Publish a Book in 30 Days: The Complete System",
        'target_keyword': "write and publish a book",
        'secondary_keywords': ["self publishing", "write a book fast", "book publishing process", "KDP guide", "author marketing"],
        'outline': [
            {"heading": "Introduction: Why 99% of Manuscripts Never Publish", "word_count": 300, "key_points": ["The dream vs reality", "The system difference", "My 50-book proof"]},
            {"heading": "Phase 1: Market Research (Days 1-7)", "word_count": 800, "key_points": ["Keyword validation", "Competitor analysis", "Reader avatar", "Category selection"]},
            {"heading": "Phase 2: Outline & Structure (Days 8-14)", "word_count": 800, "key_points": ["Chapter framework", "Reader journey map", "Hook per chapter", "Word count targets"]},
            {"heading": "Phase 3: Fast Drafting (Days 15-21)", "word_count": 1000, "key_points": ["2000 words/day system", "No editing while drafting", "Overcoming blocks", "Tracking progress"]},
            {"heading": "Phase 4: Edit & Polish (Days 22-26)", "word_count": 800, "key_points": ["3-pass edit system", "Professional editing", "Cover design", "Formatting"]},
            {"heading": "Phase 5: Publish & Launch (Days 27-30)", "word_count": 800, "key_points": ["KDP setup", "Launch team", "Amazon ads", "Review strategy"]},
            {"heading": "Conclusion: Your Author Business Starts Now", "word_count": 300, "key_points": ["Beyond book 1", "Building a catalog", "Multiple income streams", "Course + coaching"]},
        ],
        'meta_description': "Learn the exact 30-day system to write and publish your book. 50+ books published using this method. Free template included.",
        'internal_links': ["How to Outline a Book in 2 Hours", "KDP Select: My Honest Review", "Amazon Ads for Authors: $5/Day Strategy"]
    }

def generate_email_draft(heroes: list, trend_keywords: list) -> dict:
    return _local_email_draft(heroes, trend_keywords)

def _local_email_draft(heroes: list, trend_keywords: list) -> dict:
    return {
        'subject': [
            "The 30-day book system (50 books prove it works)",
            "Free: My exact book outline template",
            "Why most authors fail (and how to fix it)"
        ],
        'preview_text': "The system that published 50+ books in 30 days each...",
        'body': """
        <h2>The 30-Day Book System</h2>
        <p>Most writers spend years on one book. I published 50+ in the same time.</p>
        <p>The difference? A repeatable system.</p>
        <p><strong>Phase 1 (Days 1-7):</strong> Market research & keyword validation</p>
        <p><strong>Phase 2 (Days 8-14):</strong> Detailed outline & structure</p>
        <p><strong>Phase 3 (Days 15-21):</strong> Fast drafting (2000 words/day)</p>
        <p><strong>Phase 4 (Days 22-26):</strong> Edit & polish</p>
        <p><strong>Phase 5 (Days 27-30):</strong> Publish & launch</p>
        <p><a href="https://writernation.com/course" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Get Free Lesson →</a></p>
        <p>Write on,<br>Saurav</p>
        """,
        'cta_text': "Get Free Lesson",
        'cta_url': "https://writernation.com/course"
    }

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
    books = load_books()
    heroes = load_heroes()
    books_by_asin = {b['asin']: b for b in load_books()}
    enriched_heroes = []
    for h in load_heroes():
        book_data = books_by_asin.get(h['asin'], {})
        enriched = {**h, 'category': book_data.get('category', 'General'), 'price_inr': book_data.get('price_inr', 199), 'hook': h.get('content_angles', [''])[0] if h.get('content_angles') else ''}
        enriched_heroes.append(enriched)
    
    day_num = int(today_str().split('-')[2])
    selected_books = enriched_heroes[day_num % len(enriched_heroes):day_num % len(enriched_heroes) + 3]
    if len(selected_books) < 3:
        selected_books = enriched_heroes[:3]
    reels = [generate_reel_hook(b, trend_keywords) for b in selected_books[:3]]
    short = _local_short_script(selected_books[0], trend_keywords)
    thread = _local_tweet_thread(selected_books[1], trend_keywords)
    blog = _local_blog_outline(selected_books[2], trend_keywords)
    email = _local_email_draft(enriched_heroes, trend_keywords)
    date_dir = Path(__file__).parent.parent.parent / 'content' / 'daily' / today_str()
    date_dir.mkdir(parents=True, exist_ok=True)
    save_json(f'content/daily/{today_str()}/reels.json', reels)
    save_json(f'content/daily/{today_str()}/shorts.json', [_local_short_script(selected_books[0], trend_keywords)])
    save_json(f'content/daily/{today_str()}/tweets.json', _local_tweet_thread(selected_books[1], trend_keywords))
    save_json(f'content/daily/{today_str()}/blog.json', _local_blog_outline(selected_books[2], trend_keywords))
    save_json(f'content/daily/{today_str()}/email.json', _local_email_draft(enriched_heroes, trend_keywords))
    print(f'[{datetime.now(IST)}] Content Generation complete → content/daily/{today_str()}/')

if __name__ == '__main__':
    main()