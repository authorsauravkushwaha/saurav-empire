import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_policy
def generate_weekly_report() -> dict:
    policy = load_policy()
    date = today_str()
    trends = load_json('data/trends.json')
    finance = load_json('reports/daily-finance.json')
    leads = load_json('data/leads.json')
    experiments = load_json('reports/experiments.json')
    content_summary = {}
    content_dir = Path(__file__).parent.parent.parent / 'content/daily'
    if content_dir.exists():
        for day_dir in sorted(content_dir.iterdir())[-7:]:
            if day_dir.is_dir():
                reels = load_json(f'content/daily/{day_dir.name}/reels.json') if (day_dir / 'reels.json').exists() else []
                content_summary[day_dir.name] = {'reels': len(reels)}
    report = {
        'week_ending': date,
        'civilization_health': 'operational',
        'metrics': {
            'revenue_inr': finance.get('mtd_revenue_inr', 0),
            'leads_generated': leads.get('qualified', 0),
            'content_pieces': sum(c.get('reels', 0) for c in content_summary.values()),
            'experiments_completed': len(experiments.get('completed', [])),
            'active_experiments': len(experiments.get('active', []))
        },
        'top_insights': experiments.get('insights', [])[-5:],
        'content_performance': content_summary,
        'trending_keywords': trends.get('analysis', {}).get('top_keywords', [])[:10],
        'finance_by_platform': finance.get('by_platform', {}),
        'top_products': finance.get('top_products', [])[:5],
        'policy_compliance': {
            'ad_spend_inr': 0,
            'contracts_approved': 0,
            'emails_sent': 'N/A (manual)',
            'dms_sent': 'N/A (manual)',
            'publishing_changes': 'N/A (manual)'
        },
        'next_week_focus': [
            'Batch record next week Reels/Shorts',
            'Launch tripwire product (₹299)',
            'Recruit 5 affiliates for course',
            'Publish 1 SEO blog post',
            'Review and approve winning experiments'
        ],
        'blockers': [],
        'approvals_needed': []
    }
    return report
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    nl = chr(10)  # newline char - can't use backslash in f-string expression
    print(f'[{datetime.now(IST)}] Weekly Report generating...')
    report = generate_weekly_report()
    policy = load_policy()  # Load policy for markdown generation
    date = today_str()
    save_json(f'reports/weekly/weekly-{date}.json', report)
    md = f"""# 📊 Weekly Report — {report['week_ending']}
## 🏛️ Civilization Health: {report['civilization_health'].upper()}
## 📈 Key Metrics
- **Revenue (MTD)**: ₹{report['metrics']['revenue_inr']:,.0f}
- **Leads Generated**: {report['metrics']['leads_generated']}
- **Content Pieces**: {report['metrics']['content_pieces']}
- **Experiments Completed**: {report['metrics']['experiments_completed']}
- **Active Experiments**: {report['metrics']['active_experiments']}
## 💡 Top Insights
{nl.join(f"- {i}" for i in report['top_insights']) if report['top_insights'] else '- No insights yet'}
## 📝 Content Performance (Last 7 Days)
{nl.join(f"- {day}: {data['reels']} Reels" for day, data in report['content_performance'].items())}
## 🔍 Trending Keywords
{', '.join(report['trending_keywords']) if report['trending_keywords'] else 'No trend data'}
## 💰 Finance by Platform
{nl.join(f"- {plat}: ₹{amt:,.0f}" for plat, amt in report['finance_by_platform'].items())}
## 🏆 Top Products
{nl.join(f"- {prod}: ₹{rev:,.0f}" for prod, rev in report['top_products'])}
## ✅ Policy Compliance
- Ad Spend: ₹{report['policy_compliance']['ad_spend_inr']} (limit: ₹{policy['ad_spend']['daily_limit_inr']}/day)
- Contracts Auto-approved: {report['policy_compliance']['contracts_approved']}
## 🎯 Next Week Focus
{nl.join(f"- [ ] {item}" for item in report['next_week_focus'])}
## 🚫 Blockers
{nl.join(f"- {b}" for b in report['blockers']) if report['blockers'] else 'None'}
## ⏳ Approvals Needed
{nl.join(f"- {a}" for a in report['approvals_needed']) if report['approvals_needed'] else 'None'}
---
*Generated automatically by Saurav AI Empire · {date}*
"""
    (Path(__file__).parent.parent.parent / 'reports/weekly' / f'weekly-{date}.md').write_text(md, encoding='utf-8')
    print(f'[{datetime.now(IST)}] Weekly Report complete → reports/weekly/weekly-{date}.json + .md')
if __name__ == '__main__':
    main()
