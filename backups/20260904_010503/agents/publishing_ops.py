import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_books, load_heroes, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))

def generate_kdp_metadata(book: dict, trend_keywords: list) -> dict:
    category = book.get('category', 'GENERAL')
    title = book.get('title', 'Untitled')
    description = book.get('description', '')
    
    prompt = f'''OPTIMIZE KDP METADATA FOR: {title}
CATEGORY: {category}
CURRENT DESCRIPTION: {description[:500]}
TRENDING KEYWORDS: {trend_keywords[:10]}
PRICE: ₹{book.get('price_inr', 299)}
HERO STATUS: {book.get('is_hero', False)}

Return JSON with:
- title: optimized title (max 200 chars)
- subtitle: compelling subtitle (max 200 chars)
- description: HTML-formatted description (max 4000 chars) with hooks, benefits, social proof
- keywords: 7 backend keywords (comma-separated, each <50 chars)
- categories: 2 Amazon browse categories (format: "Category > Subcategory")
- price_recommendation: {{current_price, suggested_price, rationale}}
- kdp_select: {{enroll: true/false, rationale}}'''
    try:
        response = ai_reason(prompt, 'You are a KDP optimization expert. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'title': title,
            'subtitle': '',
            'description': description,
            'keywords': ', '.join(trend_keywords[:7]),
            'categories': ['Nonfiction > Self-Help', 'Nonfiction > Business'],
            'price_recommendation': {'current_price': book.get('price_inr', 299), 'suggested_price': book.get('price_inr', 299), 'rationale': 'AI optimization failed'},
            'kdp_select': {'enroll': False, 'rationale': 'Default conservative'}
        }

def prepare_price_changes(books: list, policy: dict) -> list:
    max_pct = policy['publishing']['max_price_change_pct_per_week']
    changes = []
    for book in books:
        if not book.get('is_hero', False):
            continue
        current = book.get('price_inr', 299)
        # Conservative: test 10% increase for high performers
        suggested = round(current * 1.1)
        pct = round((suggested - current) / current * 100)
        if abs(pct) <= max_pct:
            changes.append({
                'asin': book.get('asin', ''),
                'title': book.get('title', ''),
                'current_price': current,
                'suggested_price': suggested,
                'pct_change': pct,
                'rationale': 'Hero book price test within 15% band',
                'requires_approval': True
            })
    return changes

def prepare_keyword_updates(books: list, trend_keywords: list) -> list:
    updates = []
    for book in books[:5]:  # Top 5 heroes
        current_keywords = book.get('keywords', '').split(', ')
        new_keywords = [k for k in trend_keywords if k not in current_keywords][:3]
        if new_keywords:
            updates.append({
                'asin': book.get('asin', ''),
                'title': book.get('title', ''),
                'current_keywords': current_keywords[:7],
                'suggested_keywords': current_keywords[:7] + new_keywords,
                'rationale': 'Add trending keywords for discoverability'
            })
    return updates

def prepare_category_tweaks(books: list) -> list:
    tweaks = []
    category_map = {
        'FINANCE': ['Business & Money > Personal Finance', 'Business & Money > Investing'],
        'PSYCHOLOGY': ['Health & Fitness > Psychology', 'Self-Help > Personal Growth'],
        'BUSINESS': ['Business & Money > Entrepreneurship', 'Business & Money > Small Business'],
        'SELF_HELP': ['Self-Help > Personal Growth', 'Self-Help > Motivational'],
        'RELATIONSHIPS': ['Self-Help > Relationships', 'Health & Fitness > Family'],
    }
    for book in books[:5]:
        cat = book.get('category', 'GENERAL')
        if cat in category_map:
            tweaks.append({
                'asin': book.get('asin', ''),
                'title': book.get('title', ''),
                'current_categories': book.get('categories', []),
                'suggested_categories': category_map[cat],
                'rationale': 'Optimize category placement for target audience'
            })
    return tweaks

def main():
    print(f'[{datetime.now(IST)}] Publishing Ops starting...')
    books = load_books()
    heroes = load_heroes()
    policy = load_policy()
    trends = load_json('data/trends.json')
    trend_keywords = trends.get('analysis', {}).get('top_keywords', [])[:10]

    hero_books = [b for b in books if b.get('is_hero', False)]
    
    # Generate optimized metadata for hero books
    metadata_updates = []
    for book in hero_books:
        meta = generate_kdp_metadata(book, trend_keywords)
        meta['asin'] = book.get('asin', '')
        meta['book_title'] = book.get('title', '')
        metadata_updates.append(meta)

    # Prepare autonomous changes
    price_changes = prepare_price_changes(hero_books, policy)
    keyword_updates = prepare_keyword_updates(hero_books, trend_keywords)
    category_tweaks = prepare_category_tweaks(hero_books)

    # Changes requiring your approval
    approvals_needed = {
        'cover_uploads': [b for b in hero_books if not b.get('cover_approved', False)],
        'new_titles': [b for b in books if b.get('status') == 'draft'],
        'kdp_select': [b for b in hero_books if b.get('kdp_select_pending', False)],
        'price_changes_gt_15': [c for c in price_changes if abs(c['pct_change']) > 15],
        'rights_changes': []
    }

    output = {
        'date': today_str(),
        'metadata_updates': metadata_updates,
        'autonomous_changes': {
            'price_changes': price_changes,
            'keyword_updates': keyword_updates,
            'category_tweaks': category_tweaks
        },
        'approvals_needed': approvals_needed,
        'summary': {
            'books_optimized': len(metadata_updates),
            'price_tests': len(price_changes),
            'keyword_updates': len(keyword_updates),
            'category_tweaks': len(category_tweaks),
            'approvals_required': sum(len(v) for v in approvals_needed.values())
        }
    }

    save_json('data/publishing_changes.json', output)
    print(f'[{datetime.now(IST)}] Publishing Ops complete → data/publishing_changes.json ({output["summary"]["books_optimized"]} books optimized)')

if __name__ == '__main__':
    main()