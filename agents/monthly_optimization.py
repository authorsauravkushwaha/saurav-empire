import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_policy, load_books, load_heroes
from utils.ai_router import ai_reason
def generate_monthly_optimization() -> dict:
    policy = load_policy()
    date = today_str()
    books = load_books()
    heroes = load_heroes()
    latest_finance = load_json('reports/daily-finance.json')
    monthly_revenue = latest_finance.get('mtd_revenue_inr', 0)
    prompt = f"""MONTHLY OPTIMIZATION ANALYSIS — {date}
    REVENUE (MTD): ₹{monthly_revenue:,.0f}
    BOOKS CATALOG: {len(books)} titles
    HERO BOOKS: {len(heroes)} prioritized
    CURRENT POLICY:
    - Ad spend: ₹{policy['ad_spend']['daily_limit_inr']}/day
    - Contract auto-approve: ₹{policy['contracts']['auto_approve_limit_inr']}
    - Email limit: {policy['communications']['email']['daily_limit']}/day
    - DM limit: {policy['communications']['dm']['daily_limit']}/day
    - Price change autonomy: ≤{policy['publishing']['max_price_change_pct_per_week']}%/week
    UPGRADE TRIGGERS:
    - VPS: monthly_profit > ₹30k for 2 months
    - Paid email: list > 2000 AND revenue > ₹10k/mo
    - Ad test: monthly_profit > ₹50k for 3 months
    Return JSON with:
    - price_tests: array of {{asin, current_price, test_price, rationale}}
    - kdp_select_decisions: array of {{asin, action: enroll/unenroll/hold, rationale}}
    - affiliate_recruitment: array of {{target_profile, outreach_angle, commission_pct}}
    - policy_changes: array of {{parameter, current, proposed, rationale}}
    - upgrade_actions: array of {{trigger, status, action_needed}}
    - content_strategy_shifts: array of {{from, to, rationale}}
    """
    response = ai_reason(prompt, 'You are a strategic optimization analyst. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'price_tests': [], 'kdp_select_decisions': [], 'affiliate_recruitment': [], 'policy_changes': [], 'upgrade_actions': [], 'content_strategy_shifts': []}
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    nl = chr(10)  # newline char - can't use backslash in f-string expression
    print(f'[{datetime.now(IST)}] Monthly Optimization starting...')
    optimization = generate_monthly_optimization()
    latest_finance = load_json('reports/daily-finance.json')
    report = {
        'month': today_str()[:7],
        'generated': today_str(),
        'optimization': optimization
    }
    save_json(f'reports/monthly-optimization-{today_str()}.json', report)
    md = f"""# 📈 Monthly Optimization — {report['month']}
## 💰 Revenue Context
MTD Revenue: ₹{latest_finance.get('mtd_revenue_inr', 0):,.0f}
## 🎯 Price Tests
{nl.join(f"- {p['asin']}: ₹{p['current_price']} → ₹{p['test_price']} ({p['rationale']})" for p in optimization.get('price_tests', [])) or 'None recommended'}
## 📚 KDP Select Decisions
{nl.join(f"- {d['asin']}: {d['action']} ({d['rationale']})" for d in optimization.get('kdp_select_decisions', [])) or 'None'}
## 🤝 Affiliate Recruitment
{nl.join(f"- {a['target_profile']}: {a['outreach_angle']} ({a['commission_pct']}%)" for a in optimization.get('affiliate_recruitment', [])) or 'None'}
## ⚙️ Policy Changes (require your approval)
{nl.join(f"- {c['parameter']}: {c['current']} → {c['proposed']} ({c['rationale']})" for c in optimization.get('policy_changes', [])) or 'None'}
## ⬆️ Upgrade Actions
{nl.join(f"- {u['trigger']}: {u['status']} → {u['action_needed']}" for u in optimization.get('upgrade_actions', [])) or 'None'}
## 📝 Content Strategy Shifts
{nl.join(f"- {s['from']} → {s['to']} ({s['rationale']})" for s in optimization.get('content_strategy_shifts', [])) or 'None'}
---
**Reply "APPROVED" on any policy change to authorize.**
*Generated automatically by Saurav AI Empire · {today_str()}*
"""
    (Path(__file__).parent.parent / 'reports' / f'monthly-optimization-{today_str()}.md').write_text(md, encoding='utf-8')
    print(f'[{datetime.now(IST)}] Monthly Optimization complete → reports/monthly-optimization-{today_str()}.json + .md')
if __name__ == '__main__':
    main()
