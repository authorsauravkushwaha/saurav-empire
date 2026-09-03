import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))
DAILY_DM_LIMIT = 30
PLATFORMS = ['instagram', 'twitter', 'linkedin']

def generate_social_content(content_type: str, context: dict) -> dict:
    prompt = f'''CREATE SOCIAL MEDIA CONTENT FOR: {content_type}
PLATFORM: {context.get('platform', 'all')}
CONTEXT: {json.dumps(context)[:500]}
BRAND: Saurav Kushwaha - 50+ books, "Write & Publish in 30 Days" course ₹2,999
VOICE: Practical, encouraging, authority, no-fluff

Return JSON with:
- instagram: {{caption, hashtags[10], media_type: "reel|carousel|image", hook: "first 3 seconds"}}
- twitter: {{thread: [tweet1, tweet2, ...], hashtags[5]}}
- linkedin: {{post: "professional article style", hashtags[5]}}
- cta: {{text, url}}'''
    try:
        response = ai_reason(prompt, 'You are a social media strategist for authors. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'instagram': {'caption': 'Content generation failed', 'hashtags': ['#writerlife'], 'media_type': 'image', 'hook': ''},
            'twitter': {'thread': ['Content generation failed'], 'hashtags': ['#writerlife']},
            'linkedin': {'post': 'Content generation failed', 'hashtags': ['#writerlife']},
            'cta': {'text': 'Learn More', 'url': 'https://writernation.com'},
            'error': str(e)
        }

def prepare_dm_outreach(leads: dict) -> list:
    dms = []
    qualified = leads.get('qualified', 0)
    if qualified == 0:
        return dms
    
    # Target: engaged followers, commenters, lead magnet downloaders
    targets = [
        {'platform': 'instagram', 'type': 'comment_reply', 'count': min(10, qualified)},
        {'platform': 'twitter', 'type': 'mention_reply', 'count': min(10, qualified)},
        {'platform': 'linkedin', 'type': 'connection_message', 'count': min(10, qualified)}
    ]
    
    for target in targets:
        dms.append({
            'platform': target['platform'],
            'type': target['type'],
            'max_count': target['count'],
            'template': f'{target["type"]}_template',
            'personalized': True,
            'status': 'pending_approval'
        })
    
    return dms

def schedule_content_from_gen(content_gen: dict) -> dict:
    # Extract content from content_gen output
    reels = content_gen.get('reels', [])
    tweets = content_gen.get('tweets', [])
    blogs = content_gen.get('blogs', [])
    
    schedule = {'instagram': [], 'twitter': [], 'linkedin': []}
    
    # Schedule Reels (1 per day max)
    for i, reel in enumerate(reels[:7]):
        schedule['instagram'].append({
            'type': 'reel',
            'content': reel,
            'day_offset': i,
            'time_ist': '18:00',
            'status': 'ready'
        })
    
    # Schedule Twitter threads
    for i, tweet in enumerate(tweets[:3]):
        schedule['twitter'].append({
            'type': 'thread',
            'content': tweet,
            'day_offset': i * 2,
            'time_ist': '10:00',
            'status': 'ready'
        })
    
    # Schedule blog posts as LinkedIn articles
    for i, blog in enumerate(blogs[:2]):
        schedule['linkedin'].append({
            'type': 'article',
            'content': blog,
            'day_offset': i * 3,
            'time_ist': '09:00',
            'status': 'ready'
        })
    
    return schedule

def main():
    print(f'[{datetime.now(IST)}] Social Media starting...')
    leads = load_json('data/leads.json')
    policy = load_policy()
    content_gen = load_json('content/daily/{}/reels.json'.format(today_str())) if Path(f'content/daily/{today_str()}/reels.json').exists() else {}
    
    # Prepare DM outreach (requires approval)
    dm_plan = prepare_dm_outreach(leads)
    
    # Schedule content from content_gen
    content_schedule = schedule_content_from_gen(content_gen)
    
    # Generate fresh social content for gaps
    fresh_content = {}
    for platform in PLATFORMS:
        fresh_content[platform] = generate_social_content('daily_post', {
            'platform': platform,
            'trends': load_json('data/trends.json').get('analysis', {}).get('top_keywords', [])[:5],
            'hero_book': load_json('config/heroes.json').get('heroes', [{}])[0].get('title', '')
        })
    
    output = {
        'date': today_str(),
        'dm_outreach': dm_plan,
        'content_schedule': content_schedule,
        'fresh_content': fresh_content,
        'compliance': {
            'daily_dm_limit': DAILY_DM_LIMIT,
            'platforms': PLATFORMS,
            'human_in_loop': policy['communications']['dm']['human_in_loop'],
            'personalized_only': policy['communications']['dm']['personalized_only']
        },
        'summary': {
            'dms_pending': sum(d['max_count'] for d in dm_plan),
            'posts_scheduled': sum(len(v) for v in content_schedule.values()),
            'fresh_content_generated': len(fresh_content)
        }
    }
    
    save_json('data/social_media.json', output)
    print(f'[{datetime.now(IST)}] Social Media complete → data/social_media.json ({output["summary"]["posts_scheduled"]} posts, {output["summary"]["dms_pending"]} DMs pending)')

if __name__ == '__main__':
    main()