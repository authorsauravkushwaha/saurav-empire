import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))
COURSE_PRICE_INR = 2999
DEFAULT_COMMISSION_PCT = 30

def calculate_affiliate_payouts(affiliates: dict, sales: dict) -> list:
    payouts = []
    for affiliate_id, data in affiliates.items():
        ref_sales = sales.get(affiliate_id, {})
        total_sales = ref_sales.get('count', 0)
        revenue = ref_sales.get('revenue_inr', 0)
        commission = round(revenue * DEFAULT_COMMISSION_PCT / 100)
        if commission > 0:
            payouts.append({
                'affiliate_id': affiliate_id,
                'name': data.get('name', ''),
                'email': data.get('email', ''),
                'sales_count': total_sales,
                'revenue_generated': revenue,
                'commission_pct': DEFAULT_COMMISSION_PCT,
                'payout_inr': commission,
                'status': 'pending'
            })
    return payouts

def generate_recruitment_outreach(target_profile: str) -> dict:
    prompt = f'''WRITE AFFILIATE RECRUITMENT OUTREACH FOR: {target_profile}
PRODUCT: "Write & Publish in 30 Days" course ₹2,999
COMMISSION: 30% (₹899/sale)
BRAND: Saurav Kushwaha - 50+ published books, Writer Nation
VALUE PROP: High-ticket course, recurring potential, marketing materials provided

Return JSON with:
- subject: outreach subject line
- body: personalized outreach email
- cta: {{text, url}}
- follow_up_sequence: array of {{day, subject, body}}'''
    try:
        response = ai_reason(prompt, 'You are an affiliate recruitment specialist. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'subject': f'Partnership opportunity: 30% commission on ₹2,999 course',
            'body': f'Hi [Name],\n\nI\'m Saurav, author of 50+ books. Looking for partners to promote my "Write & Publish in 30 Days" course.\n\nCommission: 30% (₹899/sale)\nCourse: ₹2,999\nSupport: Marketing materials, tracking, monthly payouts\n\nInterested? Reply to this email.',
            'cta': {'text': 'Join Affiliate Program', 'url': 'https://writernation.com/affiliates'},
            'follow_up_sequence': [],
            'error': str(e)
        }

def identify_recruitment_targets() -> list:
    # Target profiles for recruitment
    return [
        {'profile': 'writing_coaches', 'angle': 'Monetize your coaching with our course', 'commission_pct': 30},
        {'profile': 'author_influencers', 'angle': 'Earn while helping your audience publish', 'commission_pct': 30},
        {'profile': 'writing_communities', 'angle': 'Fund your community with recurring commissions', 'commission_pct': 25},
        {'profile': 'productivity_creators', 'angle': 'Add high-ticket offer to your funnel', 'commission_pct': 30},
        {'profile': 'book_reviewers', 'angle': 'Earn from readers who want to write', 'commission_pct': 25}
    ]

def track_affiliate_performance(affiliates: dict) -> dict:
    performance = {}
    for aid, data in affiliates.items():
        sales = data.get('lifetime_sales', 0)
        revenue = data.get('lifetime_revenue', 0)
        tier = 'bronze'
        if sales > 100:
            tier = 'platinum'
        elif sales > 50:
            tier = 'gold'
        elif sales > 10:
            tier = 'silver'
        performance[aid] = {
            'tier': tier,
            'sales': sales,
            'revenue': revenue,
            'conversion_rate': data.get('conversion_rate', 0),
            'last_active': data.get('last_active', 'never')
        }
    return performance

def main():
    print(f'[{datetime.now(IST)}] Affiliate Management starting...')
    affiliates = load_json('data/affiliates.json')
    sales = load_json('data/affiliate_sales.json')
    policy = load_policy()
    
    # Calculate pending payouts
    payouts = calculate_affiliate_payouts(affiliates, sales)
    
    # Generate recruitment outreach for new targets
    targets = identify_recruitment_targets()
    outreach = {}
    for target in targets:
        outreach[target['profile']] = generate_recruitment_outreach(target['profile'])
    
    # Track performance tiers
    performance = track_affiliate_performance(affiliates)
    
    # Recruitment targets needing outreach
    recruitment_queue = []
    for target in targets:
        recruitment_queue.append({
            'profile': target['profile'],
            'outreach': outreach.get(target['profile'], {}),
            'priority': 'high' if target['commission_pct'] >= 30 else 'medium',
            'status': 'pending'
        })
    
    output = {
        'date': today_str(),
        'payouts_pending': payouts,
        'total_payout_inr': sum(p['payout_inr'] for p in payouts),
        'affiliate_count': len(affiliates),
        'active_affiliates': len([a for a in affiliates.values() if a.get('status') == 'active']),
        'performance_tiers': performance,
        'recruitment_queue': recruitment_queue,
        'commission_structure': {
            'default_pct': DEFAULT_COMMISSION_PCT,
            'course_price_inr': COURSE_PRICE_INR,
            'per_sale_earning': round(COURSE_PRICE_INR * DEFAULT_COMMISSION_PCT / 100)
        }
    }
    
    save_json('data/affiliate_management.json', output)
    print(f'[{datetime.now(IST)}] Affiliate Management complete → data/affiliate_management.json ({len(payouts)} payouts, {len(recruitment_queue)} recruitment targets)')

if __name__ == '__main__':
    main()