#!/usr/bin/env python3
"""
Manual Post Helper - Formats copy-paste ready content for Instagram
Zero API dependencies - creates ready-to-post text files
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_books, load_heroes

IST = timezone(timedelta(hours=5, minutes=30))

# Post templates
REEL_TEMPLATES = {
    'system': """{hook}

{body}

{cta}

{hashtags}""",
    'education': """{hook}

{body}

Key takeaway: {takeaway}

{cta}

{hashtags}""",
    'story': """{hook}

{body}

{cta}

{hashtags}""",
}

POST_TEMPLATES = {
    'quote': """{quote}

— {author}

{caption}

{cta}

{hashtags}""",
    'carousel': """{title}

{body}

Slide through → 

{cta}

{hashtags}""",
    'announcement': """{title}

{body}

{cta}

{hashtags}""",
}

STORY_TEMPLATES = {
    'default': """{hook}

{cta}

Swipe up / Link in bio""",
    'poll': """{question}

A) {option_a}
B) {option_b}

Vote! 👆""",
    'qna': """Ask me anything about {topic}!

I'll answer in next story 📩""",
}

# CTA library
CTAS = {
    'course': '🎓 Free lesson: "Write & Publish in 30 Days" → Link in bio',
    'lead_magnet': '📋 Free template → Link in bio',
    'book': '📚 Grab my book → Link in bio',
    'newsletter': '📧 Join 5000+ authors → Link in bio',
    'generic': '👇 Link in bio for free resources',
}

# Hashtag sets
HASHTAG_SETS = {
    'writing': ['#writerlife', '#amwriting', '#writetip', '#amwritingfiction', '#writedaily', '#authorslife', '#writingcommunity', '#writer'],
    'publishing': ['#selfpublishing', '#kdp', '#kindlepublishing', '#indieauthor', '#booklaunch', '#amazonKDP', '#publish', '#author'],
    'marketing': ['#bookmarketing', '#authormarketing', '#bookpromotion', '#booklaunch', '#bookads', '#bookstagram', '#bookish', '#reader'],
    'business': ['#authorbusiness', '#writerbusiness', '#passiveincome', '#digitalproducts', '#coursecreator', '#entrepreneur', '#sidehustle', '#freedom'],
    'mindset': ['#writermindset', '#discipline', '#consistency', '#habits', '#productivity', '#deepwork', '#focus', '#success'],
}

def format_hashtags(category, count=10):
    """Format hashtags for a category"""
    tags = HASHTAG_SETS.get(category, HASHTAG_SETS['writing'])
    selected = tags[:count]
    return ' '.join(selected)

def get_cta(type='generic'):
    return CTAS.get(type, CTAS['generic'])

def load_today_content(date_str=None):
    """Load all content for today"""
    if date_str is None:
        date_str = today_str()
    
    base = Path(__file__).parent.parent
    
    # Load content_gen output
    content_path = base / 'content' / 'daily' / date_str
    reels = load_json(f'content/daily/{date_str}/reels.json') if (content_path / 'reels.json').exists() else []
    tweets = load_json(f'content/daily/{date_str}/tweets.json') if (content_path / 'tweets.json').exists() else []
    blogs = load_json(f'content/daily/{date_str}/blogs.json') if (content_path / 'blogs.json').exists() else []
    emails = load_json(f'content/daily/{date_str}/emails.json') if (content_path / 'emails.json').exists() else []
    
    # Load visual content
    visuals = load_json(f'content/daily/{date_str}/visuals.json') if (content_path / 'visuals.json').exists() else {}
    
    # Load calendar
    calendar = load_json(f'content/calendar/{today_str()[:4]}-W{datetime.now().isocalendar()[1]:02d}.json')
    daily_plan = calendar.get('days', {}).get(date_str, {}) if calendar else {}
    
    return {
        'date': date_str,
        'reels': reels,
        'tweets': tweets,
        'blogs': blogs,
        'emails': emails,
        'visuals': visuals,
        'plan': daily_plan
    }

def format_reel_post(reel, plan, type='system'):
    """Format a reel for posting"""
    hook = reel.get('hook', '')
    # Reel data uses 'script' field, template expects 'body'
    body = reel.get('script', reel.get('body', ''))
    cta = reel.get('cta', get_cta('course'))
    hashtags = reel.get('hashtags', [])
    
    if isinstance(hashtags, list):
        hashtags = ' '.join(hashtags)
    
    template = REEL_TEMPLATES.get(type, REEL_TEMPLATES['system'])
    return template.format(
        hook=hook,
        body=body,
        cta=cta,
        hashtags=hashtags,
        takeaway=reel.get('takeaway', '')
    )

def format_post(post, plan, type='quote'):
    """Format a static post"""
    template = POST_TEMPLATES.get(type, POST_TEMPLATES['quote'])
    
    if type == 'quote':
        return template.format(
            quote=post.get('quote', ''),
            author=post.get('author', ''),
            caption=post.get('caption', ''),
            cta=get_cta('course'),
            hashtags=format_hashtags('writing')
        )
    elif type == 'carousel':
        return template.format(
            title=post.get('title', ''),
            body=post.get('body', ''),
            cta=get_cta('course'),
            hashtags=format_hashtags('writing')
        )
    return template.format(
        title=post.get('title', ''),
        body=post.get('body', ''),
        cta=get_cta('course'),
        hashtags=format_hashtags('writing')
    )

def format_story(story, plan, type='default'):
    """Format a story"""
    template = STORY_TEMPLATES.get(type, STORY_TEMPLATES['default'])
    return template.format(
        hook=story.get('hook', ''),
        cta=story.get('cta', get_cta('generic')),
        question=story.get('question', ''),
        option_a=story.get('option_a', ''),
        option_b=story.get('option_b', ''),
        topic=story.get('topic', 'writing')
    )

def generate_post_ready_file(date_str=None):
    """Generate the post_ready.txt file with all formatted content"""
    if date_str is None:
        date_str = today_str()
    
    content = load_today_content(date_str)
    plan = content.get('plan', {})
    reels = content.get('reels', [])
    tweets = content.get('tweets', [])
    blogs = content.get('blogs', [])
    emails = content.get('emails', [])
    visuals = content.get('visuals', {})
    
    day_name = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')
    pillar = plan.get('pillar', 'Book Writing System')
    hashtags_list = format_hashtags('writing', 10).split()
    hashtags = ' '.join(hashtags_list)
    cta = get_cta('course')
    
    lines = []
    lines.append("=" * 60)
    lines.append(f"📅 POST READY - {day_name}, {date_str}")
    lines.append(f"🎯 Pillar: {pillar}")
    lines.append("=" * 60)
    lines.append("")
    
    # --- REELS ---
    lines.append("🎬 REELS")
    lines.append("-" * 40)
    for i, reel in enumerate(reels[:3], 1):
        formatted = format_reel_post(reel, plan)
        lines.append(f"\n--- REEL {i} ---")
        lines.append(formatted)
        lines.append("")
        # Visual reference
        if visuals.get('reel_cover'):
            lines.append(f"📸 Cover: {visuals['reel_cover']}")
        if visuals.get('reel_cover'):
            lines.append(f"📸 Reel cover: content/daily/{date_str}/images/reel_cover.png")
    
    lines.append("")
    lines.append("📸 STATIC POSTS")
    lines.append("-" * 40)
    
    # Quote post - use reel hook as quote
    if visuals.get('quote_square') or reels:
        quote_img = f"content/daily/{date_str}/images/quote_square.png"
        lines.append(f"\n--- QUOTE POST ---")
        lines.append(f"📸 Image: {quote_img}")
        lines.append(f"📝 Caption:")
        # Use first reel hook as quote
        if reels:
            quote = reels[0].get('hook', 'Write the book you want to read.')
            author = "Saurav Kushwaha"
            caption = reels[0].get('caption', 'Your book won\'t write itself. But a system will write it for you. The 30-day system that helped me publish 50+ books.')
            lines.append(f'"{quote}"')
            lines.append(f"— {author}")
            lines.append("")
            lines.append(caption)
            lines.append("")
            lines.append(cta)
            lines.append(hashtags)
    
    # Carousel post
    if visuals.get('carousel'):
        lines.append(f"\n--- CAROUSEL POST ---")
        lines.append(f"📸 Images: {len(visuals['carousel'])} slides")
        for i, img in enumerate(visuals['carousel'], 1):
            lines.append(f"  Slide {i}: {img}")
        lines.append(f"📝 Caption:")
        lines.append("The 30-Day Book System:")
        lines.append("Phase 1: Research (Days 1-7)")
        lines.append("Phase 2: Outline (Days 8-14)")
        lines.append("Phase 3: Draft (Days 15-21)")
        lines.append("Phase 4: Edit (Days 22-26)")
        lines.append("Phase 5: Publish (Days 27-30)")
        lines.append("")
        lines.append("Slide through for the full system →")
        lines.append("")
        lines.append(cta)
        lines.append(' '.join(hashtags_list))
    
    # Blog post
    blogs = content.get('blogs', [])
    if blogs:
        blog = blogs if isinstance(blogs, dict) else (blogs[0] if blogs else {})
        lines.append(f"\n--- BLOG POST ---")
        lines.append(f"📝 Title: {blog.get('title', 'How to Write & Publish a Book in 30 Days')}")
        lines.append(f"🔑 Target Keyword: {blog.get('target_keyword', 'write and publish a book')}")
        lines.append(f"📝 Meta Description: {blog.get('meta_description', '')}")
        lines.append(f"📝 Outline:")
        for section in blog.get('outline', []):
            lines.append(f"  {section.get('heading', '')} ({section.get('word_count', 0)} words)")
            for point in section.get('key_points', []):
                lines.append(f"    • {point}")
        lines.append("")
        lines.append(cta)
        lines.append(' '.join(hashtags_list))
    
    # Tweet thread
    tweets_data = content.get('tweets', {})
    tweets_list = tweets_data.get('tweets', []) if isinstance(tweets_data, dict) else tweets_data
    if tweets_list:
        lines.append(f"\n--- TWEET THREAD ---")
        for tweet in tweets_list:
            lines.append(tweet)
        lines.append("")
        lines.append(tweets_data.get('final_cta', cta) if isinstance(tweets_data, dict) else cta)
        lines.append(' '.join(tweets_data.get('hashtags', hashtags_list)) if isinstance(tweets_data, dict) else ' '.join(hashtags_list))
    
    # Email
    emails = content.get('emails', {})
    if emails:
        subject = emails.get('subject', [''])[0] if isinstance(emails.get('subject'), list) else emails.get('subject', '')
        preview = emails.get('preview_text', '')
        body = emails.get('body', '')
        cta_text = emails.get('cta_text', 'Get Free Lesson')
        cta_url = emails.get('cta_url', 'https://writernation.com/course')
        
        lines.append(f"\n--- EMAIL ---")
        lines.append(f"Subject: {subject}")
        lines.append(f"Preview: {preview}")
        lines.append(f"CTA: {cta_text} → {cta_url}")
        lines.append(f"Body (HTML):")
        lines.append(body[:500] + "..." if len(body) > 500 else body)
    
    # Story
    lines.append("")
    lines.append("📱 STORIES")
    lines.append("-" * 40)
    if visuals.get('story'):
        lines.append(f"📸 Story template: content/daily/{date_str}/images/story.png")
        lines.append("Hook: Stop writing books nobody reads. Here's the 30-day system.")
        lines.append("CTA: Link in bio for free course")
    
    # Reel covers
    lines.append("")
    lines.append("🎬 REEL COVERS")
    lines.append("-" * 40)
    if visuals.get('reel_cover'):
        lines.append(f"Cover: content/daily/{date_str}/images/reel_cover.png")
    
    # Carousel slides
    if visuals.get('carousel'):
        lines.append("")
        lines.append("📊 CAROUSEL SLIDES")
        lines.append("-" * 40)
        for i, img in enumerate(visuals['carousel'], 1):
            lines.append(f"  Slide {i}: {img}")
    
    # Tweet thread
    if tweets_list:
        lines.append("")
        lines.append("🐦 TWEET THREAD")
        lines.append("-" * 40)
        for tweet in tweets_list:
            lines.append(tweet)
        lines.append("")
        lines.append(tweets_data.get('final_cta', cta) if isinstance(tweets_data, dict) else cta)
        lines.append(' '.join(tweets_data.get('hashtags', [])) if isinstance(tweets_data, dict) else hashtags)
    
    # Portfolio images
    lines.append("")
    lines.append("📁 ALL IMAGES FOR TODAY")
    lines.append("-" * 40)
    img_types = ['quote_square', 'reel_cover', 'post_portrait', 'carousel', 'story']
    for img_type in img_types:
        if visuals.get(img_type):
            if isinstance(visuals[img_type], list):
                for i, img in enumerate(visuals[img_type], 1):
                    lines.append(f"  {img_type} {i}: content/daily/{date_str}/images/{img}")
            else:
                lines.append(f"  {img_type}: content/daily/{date_str}/images/{visuals[img_type]}")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append("✅ COPY EACH SECTION → PASTE INTO INSTAGRAM")
    lines.append("=" * 60)
    
    output = '\n'.join(str(item) for item in lines)
    
    # Save
    base = Path(__file__).parent.parent
    output_path = base / 'content' / 'daily' / date_str / 'post_ready.txt'
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"[{datetime.now(IST)}] Post-ready file created → {output_path}")
    return output

def generate_all_formats(date_str=None):
    """Generate all post formats for a day"""
    if date_str is None:
        date_str = today_str()
    
    generate_post_ready_file(date_str)
    
    # Also create individual files for easy copying
    content = load_today_content(date_str)
    base = Path(__file__).parent.parent
    day_dir = base / 'content' / 'daily' / date_str
    os.makedirs(day_dir, exist_ok=True)
    
    # Individual reel files
    reels = content.get('reels', [])
    for i, reel in enumerate(reels[:3]):
        reel_file = day_dir / f'reel_{i+1}_formatted.txt'
        with open(reel_file, 'w', encoding='utf-8') as f:
            f.write(format_reel_post(reel, {}))
    
    # Individual post files
    # Quote
    quote_file = day_dir / 'post_quote.txt'
    with open(quote_file, 'w', encoding='utf-8') as f:
        f.write(f'Caption:\n{format_post({}, {}, "quote")}')
    
    # Carousel
    carousel_file = day_dir / 'post_carousel.txt'
    with open(carousel_file, 'w', encoding='utf-8') as f:
        f.write(f'Caption:\n{format_post({}, {}, "carousel")}')
    
    # Story
    story_file = day_dir / 'story_text.txt'
    with open(story_file, 'w', encoding='utf-8') as f:
        f.write(format_story({}, {}))
    
    print(f"[{datetime.now(IST)}] All post formats generated for {date_str}")

def main():
    generate_all_formats()

if __name__ == '__main__':
    main()