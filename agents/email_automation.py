#!/usr/bin/env python3
"""
Email Automation Agent - Brevo free tier integration
Prepares email campaigns, sequences, and broadcasts
Zero API dependencies for core logic - Brevo API only for sending
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_books, load_heroes

IST = timezone(timedelta(hours=5, minutes=30))

# Email sequences
SEQUENCES = {
    'welcome': {
        'name': 'Welcome Sequence',
        'trigger': 'signup',
        'emails': [
            {
                'day': 0,
                'subject': 'Welcome to Writer Nation 🎯',
                'template': 'welcome_day0',
                'content_type': 'welcome',
                'delay_hours': 0
            },
            {
                'day': 1,
                'subject': 'The 30-day book system (50 books prove it works)',
                'template': 'welcome_day1',
                'content_type': 'value',
                'delay_hours': 24
            },
            {
                'day': 3,
                'subject': 'Most writers fail at this one step',
                'template': 'welcome_day3',
                'content_type': 'education',
                'delay_hours': 72
            },
            {
                'day': 5,
                'subject': 'Free: My book outline template',
                'template': 'welcome_day5',
                'content_type': 'lead_magnet',
                'delay_hours': 120
            },
            {
                'day': 7,
                'subject': 'Ready to publish your first book?',
                'template': 'welcome_day7',
                'content_type': 'pitch',
                'delay_hours': 168
            }
        ]
    },
    'course_funnel': {
        'name': 'Course Funnel',
        'trigger': 'lead_magnet_download',
        'emails': [
            {
                'day': 0,
                'subject': 'Your template is ready 📋',
                'template': 'funnel_day0',
                'delay_hours': 0
            },
            {
                'day': 2,
                'subject': 'From template to published book',
                'template': 'funnel_day2',
                'delay_hours': 48
            },
            {
                'day': 4,
                'subject': 'The pricing mistake that costs authors ₹50k+',
                'template': 'funnel_day4',
                'delay_hours': 96
            },
            {
                'day': 7,
                'subject': 'Special offer: Write & Publish in 30 Days',
                'template': 'funnel_day7_pitch',
                'delay_hours': 168
            }
        ]
    },
    'buyer_sequence': {
        'name': 'Buyer Onboarding',
        'trigger': 'purchase',
        'emails': [
            {
                'day': 0,
                'subject': 'Welcome to the course! 🎓',
                'template': 'buyer_day0',
                'delay_hours': 0
            },
            {
                'day': 3,
                'subject': 'Your Day 1-7 action plan',
                'template': 'buyer_day3',
                'delay_hours': 72
            },
            {
                'day': 14,
                'subject': 'Halfway there - progress check',
                'template': 'buyer_day14',
                'delay_hours': 336
            },
            {
                'day': 30,
                'subject': 'You published! What\'s next?',
                'template': 'buyer_day30',
                'delay_hours': 720
            }
        ]
    },
    'reengagement': {
        'name': 'Re-engagement',
        'trigger': 'inactive_30_days',
        'emails': [
            {
                'day': 0,
                'subject': 'Still writing? 🤔',
                'template': 'reengage_day0',
                'delay_hours': 0
            },
            {
                'day': 3,
                'subject': 'The one thing that changed everything',
                'template': 'reengage_day3',
                'delay_hours': 72
            },
            {
                'day': 7,
                'subject': 'Come back - we saved your spot',
                'template': 'reengage_day7',
                'delay_hours': 168
            }
        ]
    }
}

# Email templates
TEMPLATES = {
    'welcome_day0': {
        'subject': 'Welcome to Writer Nation 🎯',
        'html': '''
        <h2>Welcome to Writer Nation, {{first_name}}! 🎯</h2>
        <p>I'm Saurav - author of 50+ books, creator of "Write & Publish in 30 Days" course.</p>
        <p>You're here because you want to write and publish a book. <strong>Good news: there's a system for that.</strong></p>
        <p>Over the next week, I'll share:</p>
        <ul>
            <li>The exact 30-day system that helped me publish 50+ books</li>
            <li>Why most authors fail (and how to avoid it)</li>
            <li>Free templates you can use immediately</li>
        </ul>
        <p><a href="{{course_link}}" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Get Free Lesson →</a></p>
        <p>Write on,<br>Saurav</p>
        ''',
        'text': '''
        Welcome to Writer Nation, {{first_name}}! 🎯

        I'm Saurav - author of 50+ books, creator of "Write & Publish in 30 Days" course.

        You're here because you want to write and publish a book. Good news: there's a system for that.

        Over the next week, I'll share:
        - The exact 30-day system that helped me publish 50+ books
        - Why most authors fail (and how to avoid it)
        - Free templates you can use immediately

        Get Free Lesson: {{course_link}}

        Write on,
        Saurav
        '''
    },
    'welcome_day1': {
        'subject': 'The 30-day book system (50 books prove it works)',
        'html': '''
        <h2>The 30-Day System That Published 50+ Books</h2>
        <p>Most writers spend years on one book. I published 50 in the same time.</p>
        <p>The difference? <strong>A repeatable system.</strong></p>
        <p><strong>Phase 1 (Days 1-7):</strong> Market research & keyword validation</p>
        <p><strong>Phase 2 (Days 8-14):</strong> Detailed outline & structure</p>
        <p><strong>Phase 3 (Days 15-21):</strong> Fast drafting (2000 words/day)</p>
        <p><strong>Phase 4 (Days 22-26):</strong> Edit & polish</p>
        <p><strong>Phase 5 (Days 27-30):</strong> Publish & launch</p>
        <p><a href="{{course_link}}" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">See the Full System →</a></p>
        <p>Write on,<br>Saurav</p>
        ''',
        'text': '''
        The 30-Day System That Published 50+ Books

        Most writers spend years on one book. I published 50 in the same time.
        The difference? A repeatable system.

        Phase 1 (Days 1-7): Market research & keyword validation
        Phase 2 (Days 8-14): Detailed outline & structure
        Phase 3 (Days 15-21): Fast drafting (2000 words/day)
        Phase 4 (Days 22-26): Edit & polish
        Phase 5 (Days 27-30): Publish & launch

        See the Full System: {{course_link}}

        Write on,
        Saurav
        '''
    },
    'welcome_day3': {
        'subject': 'Most writers fail at this one step',
        'html': '''
        <h2>The #1 Mistake: Writing What YOU Want, Not What READERS Want</h2>
        <p>I see it constantly. Authors pour months into a book nobody searches for.</p>
        <p><strong>The fix:</strong> Research trending topics in your genre FIRST. Then write to that demand.</p>
        <p>My 50-book catalog proves this works. Every book started with market research.</p>
        <p><strong>Free tool:</strong> My keyword research template shows exactly how.</p>
        <p><a href="{{template_link}}" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Download Free Template →</a></p>
        <p>Write on,<br>Saurav</p>
        ''',
        'text': '''
        The #1 Mistake: Writing What YOU Want, Not What READERS Want

        I see it constantly. Authors pour months into a book nobody searches for.

        The fix: Research trending topics in your genre FIRST. Then write to that demand.

        My 50-book catalog proves this works. Every book started with market research.

        Free tool: My keyword research template shows exactly how.

        Download Free Template: {{template_link}}

        Write on,
        Saurav
        '''
    },
    'welcome_day5': {
        'subject': 'Free: My book outline template',
        'html': '''
        <h2>Free: The Exact Outline Template I Use for Every Book</h2>
        <p>This template has guided 50+ books from idea to published.</p>
        <p>It includes:</p>
        <ul>
            <li>Chapter-by-chapter structure</li>
            <li>Word count targets per chapter</li>
            <li>Hook & cliffhanger prompts</li>
            <li>Reader journey map</li>
        </ul>
        <p><a href="{{template_link}}" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Download Free Template →</a></p>
        <p>Write on,<br>Saurav</p>
        ''',
        'text': '''
        Free: The Exact Outline Template I Use for Every Book

        This template has guided 50+ books from idea to published.

        It includes:
        - Chapter-by-chapter structure
        - Word count targets per chapter
        - Hook & cliffhanger prompts
        - Reader journey map

        Download Free Template: {{template_link}}

        Write on,
        Saurav
        '''
    },
    'welcome_day7': {
        'subject': 'Ready to publish your first book?',
        'html': '''
        <h2>You've Learned the System. Now Execute It.</h2>
        <p>Over the past week, you've seen:</p>
        <ul>
            <li>The 30-day system that published 50+ books</li>
            <li>The #1 mistake that kills book sales</li>
            <li>Free templates for research & outlining</li>
        </ul>
        <p>Now you have two choices:</p>
        <ol>
            <li>Try to figure it out alone (takes years)</li>
            <li>Follow the exact system with guidance (30 days)</li>
        </ol>
        <p><a href="{{course_link}}" style="background:#FFD700;color:#000;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;">Join "Write & Publish in 30 Days" →</a></p>
        <p><em>₹2,999 | Lifetime access | 1000+ authors enrolled</em></p>
        <p>Write on,<br>Saurav</p>
        ''',
        'text': '''
        Ready to publish your first book?

        You've learned the system. Now execute it.

        You've seen:
        - The 30-day system that published 50+ books
        - The #1 mistake that kills book sales
        - Free templates for research & outlining

        Now choose:
        1. Figure it out alone (takes years)
        2. Follow the exact system with guidance (30 days)

        Join "Write & Publish in 30 Days": {{course_link}}

        ₹2,999 | Lifetime access | 1000+ authors enrolled

        Write on,
        Saurav
        '''
    },
    'funnel_day0': {
        'subject': 'Your template is ready 📋',
        'html': '<p>Your template is ready! Download it here: {{template_link}}</p>',
        'text': 'Your template is ready! Download: {{template_link}}'
    },
    'funnel_day2': {
        'subject': 'From template to published book',
        'html': '<p>You have the template. Now what? The full system shows you exactly how to turn that outline into a published book.</        <p><a href="{{course_link}}">See the system →</a></p>',
        'text': 'From template to published book. The full system shows you how. {{course_link}}'
    },
    'funnel_day4': {
        'subject': 'The pricing mistake that costs authors ₹50k+',
        'html': '<p>Most authors price too low. Here is the data on optimal pricing for your genre.</p><p><a href="{{course_link}}">Learn optimal pricing →</a></p>',
        'text': 'The pricing mistake that costs authors ₹50k+. {{course_link}}'
    },
    'funnel_day7_pitch': {
        'subject': 'Special offer: Write & Publish in 30 Days',
        'html': '<p>You\'ve seen the system. Now join 1000+ authors.</p><p><a href="{{course_link}}">Join for ₹2,999 →</a></p>',
        'text': 'Special offer: Write & Publish in 30 Days for ₹2,999. {{course_link}}'
    },
    'buyer_day0': {
        'subject': 'Welcome to the course! 🎓',
        'html': '<p>Welcome! Your login details are here: {{course_link}}.<br>Start with Module 1: Market Research.</p>',
        'text': 'Welcome to the course! Login: {{course_link}}. Start with Module 1.'
    },
    'buyer_day3': {
        'subject': 'Your Day 1-7 action plan',
        'html': '<p>Here is your exact Day 1-7 plan for market research.</p><p><a href="{{course_link}}">View Module 1 →</a></p>',
        'text': 'Your Day 1-7 action plan. {{course_link}}'
    },
    'buyer_day14': {
        'subject': 'Halfway there - progress check',
        'html': '<p>You are halfway through! How is the draft coming along?</p><p>Reply to this email - I read every one.</p>',
        'text': 'Halfway there! How is the draft coming? Reply to this email.'
    },
    'buyer_day30': {
        'subject': 'You published! What\'s next?',
        'html': '<p>Congratulations! 🎉 Your book is live.</p><p>Now: marketing, reviews, and your next book.</p><p><a href="{{course_link}}">Advanced marketing module →</a></p>',
        'text': 'You published! What\'s next? Advanced marketing: {{course_link}}'
    },
    'reengage_day0': {
        'subject': 'Still writing? 🤔',
        'html': '<p>Haven\'t seen you in a while. Still working on your book?</p><p><a href="{{course_link}}">Pick up where you left off →</a></p>',
        'text': 'Still writing? Pick up where you left off: {{course_link}}'
    },
    'reengage_day3': {
        'subject': 'The one thing that changed everything',
        'html': '<p>It wasn\'t talent. It was a system.</p><p><a href="{{course_link}}">See the system →</a></p>',
        'text': 'The one thing that changed everything: a system. {{course_link}}'
    },
    'reengage_day7': {
        'subject': 'Come back - we saved your spot',
        'html': '<p>Your spot in the course is still open.</p><p><a href="{{course_link}}">Claim your spot →</a></p>',
        'text': 'Come back - we saved your spot. {{course_link}}'
    },
}

def generate_email_campaigns(date_str=None):
    """Generate email campaigns for the day"""
    if date_str is None:
        date_str = today_str()
    
    leads = load_json('data/leads.json')
    total_leads = leads.get('total', 0)
    
    campaigns = {}
    
    # Daily broadcast (if Monday)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    if date_obj.weekday() == 0:  # Monday
        campaigns['weekly_newsletter'] = {
            'name': 'Weekly Newsletter',
            'subject': f'Writer Nation Weekly - {date_str}',
            'segment': 'all_subscribers',
            'template': 'weekly_newsletter',
            'scheduled': '09:00',
            'cta': 'course',
            'send_via': 'brevo_dashboard'
        }
    
    # Sequence emails (handled by Brevo automation)
    for seq_key, seq in SEQUENCES.items():
        campaigns[f'sequence_{seq_key}'] = {
            'name': seq['name'],
            'trigger': seq['trigger'],
            'emails': len(seq['emails']),
            'status': 'active_in_brevo',
            'configured_in': 'brevo_automation'
        }
    
    # Save
    save_json(f'data/email_campaigns_{date_str}.json', {
        'date': date_str,
        'total_leads': total_leads,
        'campaigns': campaigns
    })
    
    return campaigns

def generate_email_content(template_key, data=None):
    """Generate email content for a template"""
    if data is None:
        data = {}
    
    defaults = {
        'first_name': 'Writer',
        'course_link': 'https://writernation.com/course',
        'template_link': 'https://writernation.com/free-template',
    }
    data = {**defaults, **data}
    
    template = TEMPLATES.get(template_key, {})
    if not template:
        return None
    
    # Simple template replacement
    html = template.get('html', '')
    text = template.get('text', '')
    
    for key, value in data.items():
        html = html.replace(f'{{{{{key}}}}}', value)
        text = text.replace(f'{{{{{key}}}}}', value)
    
    return {
        'subject': template.get('subject', ''),
        'html': html,
        'text': text
    }

def prepare_brevo_import(date_str=None):
    """Prepare CSV for Brevo contact import"""
    if date_str is None:
        date_str = today_str()
    
    leads = load_json('data/leads.json')
    contacts = leads.get('contacts', [])
    
    # Format for Brevo CSV import
    csv_rows = ['email,first_name,last_name,source,signup_date']
    for contact in contacts:
        csv_rows.append(f"{contact.get('email','')},{contact.get('first_name','')},{contact.get('last_name','')},{contact.get('source','')},{contact.get('signup_date', date_str)}")
    
    csv_content = '\n'.join(csv_rows)
    
    save_json(f'data/brevo_import_{date_str}.json', {
        'date': date_str,
        'csv_content': csv_content,
        'total_contacts': len(contacts)
    })
    
    return csv_content

def main():
    date = today_str()
    campaigns = generate_email_campaigns(date)
    print(f"[{datetime.now(IST)}] Email campaigns prepared for {date}")
    print(f"Campaigns: {list(campaigns.keys())}")
    
    # Prepare Brevo import
    prepare_brevo_import(date)
    print("Brevo import prepared")

if __name__ == '__main__':
    main()