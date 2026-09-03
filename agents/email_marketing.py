import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))
BREVO_DAILY_LIMIT = 300  # Brevo free tier
SAFETY_LIMIT = 100  # Our safety margin

def create_welcome_sequence() -> list:
    return [
        {
            'day': 0,
            'subject': 'Welcome to Writer Nation 🎯',
            'template': 'welcome_day0',
            'trigger': 'signup',
            'content_type': 'welcome'
        },
        {
            'day': 1,
            'subject': 'The 30-day book system (50 books prove it works)',
            'template': 'welcome_day1',
            'content_type': 'value'
        },
        {
            'day': 3,
            'subject': 'Most writers fail at this one step',
            'template': 'welcome_day3',
            'content_type': 'education'
        },
        {
            'day': 5,
            'subject': 'Free: My book outline template',
            'template': 'welcome_day5',
            'content_type': 'lead_magnet'
        },
        {
            'day': 7,
            'subject': 'Ready to publish your first book?',
            'template': 'welcome_day7',
            'content_type': 'pitch'
        }
    ]

def create_nurture_sequences() -> list:
    return [
        {
            'name': 'course_funnel',
            'trigger': 'lead_magnet_download',
            'emails': [
                {'day': 0, 'subject': 'Your template is ready 📋', 'template': 'funnel_day0'},
                {'day': 2, 'subject': 'From template to published book', 'template': 'funnel_day2'},
                {'day': 4, 'subject': 'The pricing mistake that costs authors ₹50k+', 'template': 'funnel_day4'},
                {'day': 7, 'subject': 'Special offer: Write & Publish in 30 Days', 'template': 'funnel_day7_pitch'}
            ]
        },
        {
            'name': 'buyer_sequence',
            'trigger': 'purchase',
            'emails': [
                {'day': 0, 'subject': 'Welcome to the course! 🎓', 'template': 'buyer_day0'},
                {'day': 3, 'subject': 'Your Day 1-7 action plan', 'template': 'buyer_day3'},
                {'day': 14, 'subject': 'Halfway there - progress check', 'template': 'buyer_day14'},
                {'day': 30, 'subject': 'You published! What\'s next?', 'template': 'buyer_day30'}
            ]
        }
    ]

def generate_campaign_content(campaign_type: str, context: dict) -> dict:
    sequences = create_welcome_sequence() + [e for s in create_nurture_sequences() for e in s['emails']]
    campaign = next((s for s in sequences if s.get('content_type') == campaign_type or s.get('trigger') == campaign_type), None)
    if not campaign and sequences:
        campaign = sequences[0]
    
    prompt = f'''WRITE EMAIL CONTENT FOR: {campaign_type}
CONTEXT: {json.dumps(context)[:500]}
AUDIENCE: Aspiring authors, self-publishers, writers
BRAND VOICE: Saurav - practical, encouraging, no-fluff, 50+ books authority
COURSE: "Write & Publish in 30 Days" ₹2,999

Return JSON with:
- subject: compelling subject line (<50 chars)
- preview_text: preview text (<100 chars)
- html_content: full HTML email with proper formatting
- text_content: plain text version
- cta: {{text, url}}
- personalization_tags: array of merge tags used'''
    try:
        response = ai_reason(prompt, 'You are an email copywriter for authors. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'subject': f'Update from Writer Nation',
            'preview_text': 'New content for your author journey',
            'html_content': '<p>Content generation failed. Please review manually.</p>',
            'text_content': 'Content generation failed. Please review manually.',
            'cta': {'text': 'Read More', 'url': 'https://writernation.com'},
            'personalization_tags': ['{{first_name}}', '{{last_book}}'],
            'error': str(e)
        }

def prepare_campaigns(leads: dict, policy: dict) -> dict:
    total_leads = leads.get('total', 0)
    qualified = leads.get('qualified', 0)
    
    # Segment leads
    segments = {
        'new_subscribers': min(leads.get('new_today', 0), SAFETY_LIMIT),
        'active_leads': min(qualified, SAFETY_LIMIT),
        'buyers': leads.get('buyers', 0),
        'inactive': leads.get('inactive', 0)
    }
    
    # Campaigns to send today (within limits)
    daily_limit = min(SAFETY_LIMIT, total_leads)
    
    campaigns = []
    
    # Welcome new subscribers
    if segments['new_subscribers'] > 0:
        campaigns.append({
            'name': 'welcome_sequence',
            'segment': 'new_subscribers',
            'count': segments['new_subscribers'],
            'type': 'automated',
            'status': 'ready'
        })
    
    # Weekly newsletter to active leads (if Monday)
    if datetime.now(IST).weekday() == 0 and segments['active_leads'] > 0:
        campaigns.append({
            'name': 'weekly_newsletter',
            'segment': 'active_leads',
            'count': min(segments['active_leads'], daily_limit - sum(c['count'] for c in campaigns)),
            'type': 'broadcast',
            'status': 'ready'
        })
    
    # Course funnel for lead magnet downloaders
    if leads.get('lead_magnet_downloads_today', 0) > 0:
        campaigns.append({
            'name': 'course_funnel',
            'segment': 'lead_magnet_downloaders',
            'count': min(leads.get('lead_magnet_downloads_today', 0), daily_limit - sum(c['count'] for c in campaigns)),
            'type': 'automated',
            'status': 'ready'
        })
    
    return {
        'segments': segments,
        'daily_limit': daily_limit,
        'campaigns_ready': campaigns,
        'total_to_send': sum(c['count'] for c in campaigns)
    }

def main():
    print(f'[{datetime.now(IST)}] Email Marketing starting...')
    leads = load_json('data/leads.json')
    policy = load_policy()
    
    campaign_plan = prepare_campaigns(leads, policy)
    
    # Generate content for each campaign
    for campaign in campaign_plan['campaigns_ready']:
        content = generate_campaign_content(campaign['name'], {
            'segment': campaign['segment'],
            'count': campaign['count'],
            'type': campaign['type']
        })
        campaign['content'] = content
    
    output = {
        'date': today_str(),
        'plan': campaign_plan,
        'sequences': create_welcome_sequence() + create_nurture_sequences(),
        'compliance': {
            'daily_limit': SAFETY_LIMIT,
            'brevo_limit': BREVO_DAILY_LIMIT,
            'double_optin': policy['communications']['email']['double_optin_required'],
            'unsubscribe_required': policy['communications']['email']['unsubscribe_link_required']
        }
    }
    
    save_json('data/email_campaigns.json', output)
    print(f'[{datetime.now(IST)}] Email Marketing complete → data/email_campaigns.json ({output["plan"]["total_to_send"]} emails queued)')

if __name__ == '__main__':
    main()