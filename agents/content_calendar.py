#!/usr/bin/env python3
"""
Content Calendar Generator - Weekly themes, daily assignments, content planning
Zero API dependencies - local only
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_books, load_heroes

IST = timezone(timedelta(hours=5, minutes=30))

# Weekly themes
WEEKLY_THEMES = [
    "Book Writing Systems",
    "Publishing Strategies", 
    "Marketing for Authors",
    "Building Author Brand",
    "Course Creation",
    "Audience Growth",
    "Revenue Optimization"
]

# Daily content types
DAILY_CONTENT = {
    'Monday': {
        'theme': 'Motivation & Systems',
        'reel': 'System spotlight',
        'post': 'Quote graphic',
        'story': 'Weekly goal setting',
        'focus': 'Start week with actionable system'
    },
    'Tuesday': {
        'theme': 'Education & Craft',
        'reel': 'Writing tip',
        'post': 'Carousel: How-to',
        'story': 'Book recommendation',
        'focus': 'Teach one actionable skill'
    },
    'Wednesday': {
        'theme': 'Business & Publishing',
        'reel': 'Publishing insight',
        'post': 'Stat/Infographic',
        'story': 'Q&A',
        'focus': 'Industry knowledge'
    },
    'Thursday': {
        'theme': 'Writing & Craft',
        'reel': 'Writing technique',
        'post': 'Quote graphic',
        'story': 'Behind the scenes',
        'focus': 'Writing process transparency'
    },
    'Friday': {
        'theme': 'Weekend Planning',
        'reel': 'Weekend writing plan',
        'post': 'Motivation quote',
        'story': 'Weekly wins',
        'focus': 'Set up productive weekend'
    },
    'Saturday': {
        'theme': 'Personal Growth',
        'reel': 'Personal story',
        'post': 'Personal insight',
        'story': 'Weekend reading',
        'focus': 'Authentic connection'
    },
    'Sunday': {
        'theme': 'Planning & Strategy',
        'reel': 'Week ahead preview',
        'post': 'Weekly recap',
        'story': 'Planning session',
        'focus': 'Strategic planning'
    }
}

# Content pillars (rotate through these)
CONTENT_PILLARS = [
    {'name': 'Book Writing System', 'weight': 30, 'keywords': ['30 days', 'system', 'process', 'outline', 'draft']},
    {'name': 'Publishing Journey', 'weight': 20, 'keywords': ['KDP', 'publish', 'launch', 'cover', 'ISBN']},
    {'name': 'Author Marketing', 'weight': 20, 'keywords': ['marketing', 'ads', 'email', 'social', 'launch']},
    {'name': 'Author Brand', 'weight': 15, 'keywords': ['brand', 'authority', 'niche', 'audience', 'voice']},
    {'name': 'Course Creation', 'weight': 15, 'keywords': ['course', 'teach', 'students', 'curriculum', 'revenue']},
]

# Hashtag sets by pillar
HASHTAGS = {
    'Book Writing System': ['#writerlife', '#amwriting', '#writetip', '#booksystem', '#30daybook', '#outline', '#firstdraft', '#authorlife'],
    'Publishing Journey': ['#selfpublishing', '#kdp', '#booklaunch', '#indieauthor', '#publish', '#kdpselect', '#bookcover', '#amazon'],
    'Author Marketing': ['#bookmarketing', '#authormarketing', '#bookpromo', '#bookads', '#emailmarketing', '#booklaunch', '#reader', '#authorbrand'],
    'Author Brand': ['#authorbrand', '#personalbrand', '#authorplatform', '#writerbrand', '#authority', '#niche', '#expert'],
    'Course Creation': ['#coursecreator', '#onlinecourse', '#teachonline', '#passiveincome', '#digitalcourse', '#writecourse', '#authorcourse'],
}

def get_week_number(date_str=None):
    """Get ISO week number"""
    if date_str:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        date_obj = datetime.now(IST)
    return date_obj.isocalendar()[1]

def get_week_dates(week_num, year=None):
    """Get Monday-Sunday dates for a week"""
    if year is None:
        year = datetime.now(IST).year
    # Find Monday of the week
    jan1 = datetime(year, 1, 1)
    # First Monday of year
    first_monday = jan1 + timedelta(days=(7 - jan1.weekday()) % 7)
    week_monday = first_monday + timedelta(weeks=week_num-1)
    return [(week_monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

def generate_weekly_calendar(week_num=None, year=None):
    """Generate weekly content calendar"""
    if week_num is None:
        week_num = get_week_number()
    if year is None:
        year = datetime.now(IST).year
    
    week_dates = get_week_dates(week_num, year)
    theme = WEEKLY_THEMES[(week_num - 1) % len(WEEKLY_THEMES)]
    
    calendar = {
        'week_number': week_num,
        'year': year,
        'theme': theme,
        'dates': week_dates,
        'days': {}
    }
    
    heroes = load_heroes()
    hero_titles = [h.get('title', '') for h in heroes]
    
    for i, date_str in enumerate(week_dates):
        day_name = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')
        daily = DAILY_CONTENT[day_name].copy()
        
        # Assign content pillar based on rotation
        pillar_idx = (week_num + i) % len(CONTENT_PILLARS)
        pillar = CONTENT_PILLARS[pillar_idx]
        
        # Select hashtags
        pillar_tags = HASHTAGS.get(pillar['name'], [])
        daily_tags = random.sample(pillar_tags, min(8, len(pillar_tags)))
        
        # Book to feature (rotate through heroes)
        hero_idx = (week_num * 7 + i) % len(hero_titles) if hero_titles else 0
        featured_book = hero_titles[hero_idx] if hero_titles else "Write & Publish in 30 Days"
        
        calendar['days'][date_str] = {
            'day': day_name,
            'date': date_str,
            'theme': daily['theme'],
            'pillar': pillar['name'],
            'content_types': {
                'reel': daily['reel'],
                'post': daily['post'],
                'story': daily['story']
            },
            'focus': daily['focus'],
            'hashtags': daily_tags,
            'featured_book': featured_book,
            'cta': get_cta(pillar['name']),
            'content_ideas': get_content_ideas(pillar['name'], daily['theme'])
        }
    
    return calendar

def get_cta(pillar):
    """Get call-to-action for pillar"""
    ctas = {
        'Book Writing System': 'Download free 30-day outline template → Link in bio',
        'Publishing Journey': 'Get my KDP checklist free → Link in bio',
        'Author Marketing': 'Join free author marketing workshop → Link in bio',
        'Author Brand': 'Grab my author brand worksheet → Link in bio',
        'Course Creation': 'Free lesson: Write & Publish in 30 Days → Link in bio',
    }
    return ctas.get(pillar, 'Link in bio for free resources')

def get_content_ideas(pillar, theme):
    """Generate specific content ideas"""
    ideas = {
        'Book Writing System': [
            "My exact 30-day writing calendar",
            "How I outline a book in 2 hours",
            "The 5-minute daily writing habit",
            "From idea to outline in 3 steps"
        ],
        'Publishing Journey': [
            "KDP Select: My honest review",
            "Cover design: DIY vs Pro",
            "My launch day checklist",
            "ISBN: Do you really need one?"
        ],
        'Author Marketing': [
            "Amazon ads: My $5/day strategy",
            "Email list: First 1000 subscribers",
            "BookBub feature: How I got it",
            "TikTok for authors: Worth it?"
        ],
        'Author Brand': [
            "My author bio that converts",
            "Choosing your author niche",
            "Consistent visual brand",
            "Voice: Finding yours"
        ],
        'Course Creation': [
            "Course outline template",
            "Pricing your first course",
            "Recording without fancy gear",
            "Student results: Case study"
        ],
    }
    return ideas.get(pillar, [theme])

import random

def generate_content_calendar(weeks_ahead=4):
    """Generate calendar for next N weeks"""
    current_week = get_week_number()
    current_year = datetime.now(IST).year
    
    all_weeks = {}
    for w in range(weeks_ahead):
        week_num = current_week + w
        year = current_year
        if week_num > 52:
            week_num -= 52
            year += 1
        week_key = f"{year}-W{week_num:02d}"
        all_weeks[week_key] = generate_weekly_calendar(week_num, year)
    
    # Save
    save_json('content/calendar/master.json', {
        'generated': today_str(),
        'current_week': f"{current_year}-W{current_week:02d}",
        'weeks': all_weeks
    })
    
    # Also save current week separately for easy access
    current_key = f"{current_year}-W{current_week:02d}"
    save_json(f'content/calendar/{current_key}.json', all_weeks[current_key])
    
    print(f"[{datetime.now(IST)}] Content calendar generated for {weeks_ahead} weeks")
    return all_weeks

def get_daily_plan(date_str=None):
    """Get detailed daily plan for a specific date"""
    if date_str is None:
        date_str = today_str()
    
    week_num = get_week_number(date_str)
    year = datetime.strptime(date_str, '%Y-%m-%d').year
    calendar = generate_weekly_calendar(week_num, year)
    
    return calendar['days'].get(date_str, {})

def main():
    weeks = generate_content_calendar(4)
    print(f"Generated calendar for {len(weeks)} weeks")
    # Print current week summary
    current_week = get_week_number()
    current_year = datetime.now(IST).year
    current = weeks.get(f"{current_year}-W{current_week:02d}", {})
    if current:
        print(f"\nThis Week ({current.get('theme', 'N/A')}):")
        for date_str, day in current.get('days', {}).items():
            print(f"  {day['day']} ({date_str}): {day['pillar']} - {day['content_types']['reel']} | {day['content_types']['post']}")

if __name__ == '__main__':
    main()