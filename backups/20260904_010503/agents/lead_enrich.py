import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import save_json, load_heroes, today_str
from utils.ai_router import ai_reason
from utils.validators import validate_dm_send
def find_engaged_users() -> list:
    return []
def enrich_lead(lead: dict, heroes: list) -> dict:
    prompt = f'''
Analyze this lead for personalized outreach:
Platform: {lead.get('platform', 'unknown')}
Username: {lead.get('username', 'unknown')}
Comment: {lead.get('comment_text', '')[:300]}
Engagement score: {lead.get('engagement_score', 0)}
Our books (pick best match):
{json.dumps([{'title': h['title'], 'angles': h['content_angles']} for h in heroes[:10]], indent=2)}
Return JSON:
- best_book_match: title
- personalization_angle: specific hook for THIS person
- dm_draft: personalized DM (<300 chars, no spam, value-first)
- priority: high/medium/low
- tags: [list of relevant tags]
'''
    response = ai_reason(prompt, 'You are a sales qualification expert. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        enrichment = json.loads(response[start:end])
        return {**lead, **enrichment}
    except:
        return {**lead, 'best_book_match': '', 'personalization_angle': '', 'dm_draft': '', 'priority': 'low', 'tags': []}
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    print(f'[{datetime.now(IST)}] Lead Enrichment starting...')
    heroes = load_heroes()
    raw_leads = find_engaged_users()
    manual_leads = []
    imports_dir = Path(__file__).parent.parent.parent / 'data/imports'
    for csv_file in imports_dir.glob('leads*.csv'):
        try:
            import pandas as pd
            df = pd.read_csv(csv_file)
            manual_leads.extend(df.to_dict('records'))
        except:
            pass
    all_leads = raw_leads + manual_leads
    enriched = [enrich_lead(lead, heroes) for lead in all_leads]
    policy_dm_limit = 30
    qualified = [l for l in enriched if l.get('priority') in ('high', 'medium') and l.get('dm_draft')]
    qualified = qualified[:policy_dm_limit]
    save_json('data/leads.json', {
        'date': today_str(),
        'total_found': len(all_leads),
        'qualified': len(qualified),
        'leads': qualified
    })
    print(f'[{datetime.now(IST)}] Lead Enrichment complete → data/leads.json ({len(qualified)} qualified)')
if __name__ == '__main__':
    main()
