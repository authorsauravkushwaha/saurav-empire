import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))

FAQ_CATEGORIES = {
    'publishing': ['How to publish on KDP?', 'Cover requirements?', 'ISBN needed?', 'Royalties explained?', 'KDP Select pros/cons?'],
    'marketing': ['Book launch strategy?', 'Amazon ads setup?', 'Email list building?', 'Social media for authors?', 'Review generation?'],
    'course': ['Course content?', 'Time commitment?', 'Refund policy?', 'Lifetime access?', 'Results guarantee?'],
    'technical': ['Login issues?', 'Payment failed?', 'Download problems?', 'Video playback?', 'Mobile access?'],
    'general': ['Who is Saurav?', 'Writer Nation mission?', 'Free resources?', 'Contact support?', 'Affiliate program?']
}

def generate_faq_response(category: str, question: str) -> dict:
    prompt = f'''WRITE FAQ RESPONSE FOR: {category} - {question}
BRAND: Saurav Kushwaha - 50+ books, Writer Nation, "Write & Publish in 30 Days" ₹2,999
VOICE: Practical, encouraging, authoritative, concise
FORMAT: Direct answer + actionable next step + relevant link

Return JSON with:
- answer: clear, helpful response (2-3 paragraphs)
- next_step: single actionable step for user
- related_links: array of {{text, url}}
- tags: array of related FAQ topics'''
    try:
        response = ai_reason(prompt, 'You are a customer support expert for authors. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'answer': f'For questions about {category.lower()}, please check our knowledge base or contact support.',
            'next_step': 'Visit writernation.com/help',
            'related_links': [{'text': 'Knowledge Base', 'url': 'https://writernation.com/help'}],
            'tags': [category],
            'error': str(e)
        }

def analyze_tickets(tickets: list) -> dict:
    if not tickets:
        return {'top_issues': [], 'sentiment': 'neutral', 'urgent_count': 0, 'sla_breaches': 0}
    
    categories = {}
    urgent = 0
    for ticket in tickets:
        cat = ticket.get('category', 'general')
        categories[cat] = categories.get(cat, 0) + 1
        if ticket.get('priority') == 'urgent':
            urgent += 1
    
    top_issues = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'top_issues': [{'category': k, 'count': v} for k, v in top_issues],
        'sentiment': 'negative' if urgent > 5 else 'neutral',
        'urgent_count': urgent,
        'sla_breaches': sum(1 for t in tickets if t.get('sla_breached', False))
    }

def generate_auto_response(ticket: dict) -> dict:
    category = ticket.get('category', 'general')
    question = ticket.get('subject', '') + ' ' + ticket.get('body', '')
    
    faq = generate_faq_response(category, question)
    
    return {
        'ticket_id': ticket.get('id', ''),
        'auto_response': faq.get('answer', ''),
        'confidence': 0.7,
        'escalate': ticket.get('priority') == 'urgent' or 'refund' in question.lower(),
        'suggested_tags': faq.get('tags', [])
    }

def prepare_knowledge_base_updates(tickets: list) -> list:
    """Identify gaps in FAQ based on ticket patterns"""
    category_counts = {}
    for ticket in tickets:
        cat = ticket.get('category', 'general')
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    updates = []
    for cat, count in category_counts.items():
        if count > 10:  # High volume = needs better FAQ
            for q in FAQ_CATEGORIES.get(cat, []):
                updates.append({
                    'category': cat,
                    'question': q,
                    'reason': f'{count} tickets in {cat} category',
                    'priority': 'high' if count > 20 else 'medium'
                })
    return updates

def main():
    print(f'[{datetime.now(IST)}] Customer Support starting...')
    tickets = load_json('data/support_tickets.json')
    policy = load_policy()
    
    # Analyze ticket patterns
    analysis = analyze_tickets(tickets)
    
    # Generate auto-responses for new tickets
    new_tickets = [t for t in tickets if t.get('status') == 'new']
    auto_responses = [generate_auto_response(t) for t in new_tickets]
    
    # Identify knowledge base gaps
    kb_updates = prepare_knowledge_base_updates(tickets)
    
    # Common issues requiring proactive content
    proactive_content = []
    if analysis['top_issues']:
        for issue in analysis['top_issues'][:3]:
            proactive_content.append({
                'topic': issue['category'],
                'type': 'blog_post' if issue['count'] > 20 else 'faq_entry',
                'reason': f'{issue["count"]} tickets this period',
                'title_idea': f'Complete Guide to {issue["category"].title()} for Authors'
            })
    
    output = {
        'date': today_str(),
        'ticket_summary': {
            'total': len(tickets),
            'new': len(new_tickets),
            'resolved': len([t for t in tickets if t.get('status') == 'resolved']),
            'urgent': analysis['urgent_count'],
            'sla_breaches': analysis['sla_breaches']
        },
        'analysis': analysis,
        'auto_responses': auto_responses,
        'knowledge_base_updates': kb_updates,
        'proactive_content': proactive_content,
        'faq_categories': FAQ_CATEGORIES
    }
    
    save_json('data/customer_support.json', output)
    print(f'[{datetime.now(IST)}] Customer Support complete → data/customer_support.json ({len(auto_responses)} auto-responses, {len(kb_updates)} KB updates)')

if __name__ == '__main__':
    main()