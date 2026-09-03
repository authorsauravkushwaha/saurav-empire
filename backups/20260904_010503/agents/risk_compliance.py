import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))

def check_ad_spend_compliance(finance: dict, policy: dict) -> list:
    violations = []
    mtd_spend = finance.get('mtd_ad_spend_inr', 0)
    daily_limit = policy['ad_spend']['daily_limit_inr']
    monthly_limit = policy['ad_spend']['monthly_limit_inr']
    if daily_limit > 0 and mtd_spend > daily_limit * 30:
        violations.append(f"Ad spend ₹{mtd_spend} exceeds monthly limit ₹{monthly_limit}")
    return violations

def check_contract_compliance(contracts: dict, policy: dict) -> list:
    violations = []
    auto_limit = policy['contracts']['auto_approve_limit_inr']
    for contract in contracts.get('pending', []):
        if contract.get('value_inr', 0) > auto_limit:
            violations.append(f"Contract {contract.get('id')} ₹{contract.get('value_inr')} exceeds auto-approve limit ₹{auto_limit}")
    return violations

def check_communication_compliance(leads: dict, policy: dict) -> list:
    violations = []
    email_limit = policy['communications']['email']['daily_limit']
    dm_limit = policy['communications']['dm']['daily_limit']
    emails_sent = leads.get('emails_sent_today', 0)
    dms_sent = leads.get('dms_sent_today', 0)
    if emails_sent > email_limit:
        violations.append(f"Emails sent {emails_sent} exceeds daily limit {email_limit}")
    if dms_sent > dm_limit:
        violations.append(f"DMs sent {dms_sent} exceeds daily limit {dm_limit}")
    return violations

def check_publishing_compliance(publishing: dict, policy: dict) -> list:
    violations = []
    max_pct = policy['publishing']['max_price_change_pct_per_week']
    for change in publishing.get('price_changes', []):
        if abs(change.get('pct_change', 0)) > max_pct:
            violations.append(f"Price change {change.get('pct_change')}% exceeds {max_pct}% limit for {change.get('asin')}")
    return violations

def check_financial_anomalies(finance: dict) -> list:
    anomalies = []
    revenue = finance.get('mtd_revenue_inr', 0)
    expenses = finance.get('mtd_expenses_inr', 0)
    if revenue > 0 and expenses > revenue * 0.5:
        anomalies.append(f"Expenses ₹{expenses} > 50% of revenue ₹{revenue}")
    for platform, amt in finance.get('by_platform', {}).items():
        if amt < 0:
            anomalies.append(f"Negative revenue on {platform}: ₹{amt}")
    return anomalies

def analyze_with_ai(data: dict) -> dict:
    policy = load_policy()
    prompt = f'''RISK & COMPLIANCE ANALYSIS — {today_str()}
CURRENT POLICY:
- Ad spend limit: ₹{policy['ad_spend']['daily_limit_inr']}/day
- Contract auto-approve: ₹{policy['contracts']['auto_approve_limit_inr']}
- Email limit: {policy['communications']['email']['daily_limit']}/day
- DM limit: {policy['communications']['dm']['daily_limit']}/day
- Price change limit: {policy['publishing']['max_price_change_pct_per_week']}%/week

VIOLATIONS FOUND:
Ad Spend: {data.get('ad_spend_violations', [])}
Contracts: {data.get('contract_violations', [])}
Communications: {data.get('communication_violations', [])}
Publishing: {data.get('publishing_violations', [])}
Financial Anomalies: {data.get('financial_anomalies', [])}

Return JSON with:
- risk_level: "low|medium|high|critical"
- priority_actions: array of {{action, rationale, deadline}}
- approvals_needed: array of {{item, reason, approver}}
- policy_adjustments: array of {{parameter, current, suggested, rationale}}
- monitoring_alerts: array of {{metric, threshold, current_value}}'''
    try:
        response = ai_reason(prompt, 'You are a risk & compliance officer. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {'risk_level': 'low', 'priority_actions': [], 'approvals_needed': [], 'policy_adjustments': [], 'monitoring_alerts': [], 'error': str(e)}

def main():
    print(f'[{datetime.now(IST)}] Risk & Compliance starting...')
    finance = load_json('reports/daily-finance.json')
    leads = load_json('data/leads.json')
    contracts = load_json('data/contracts.json')
    publishing = load_json('data/publishing_changes.json')
    policy = load_policy()

    violations = {
        'ad_spend_violations': check_ad_spend_compliance(finance, policy),
        'contract_violations': check_contract_compliance(contracts, policy),
        'communication_violations': check_communication_compliance(leads, policy),
        'publishing_violations': check_publishing_compliance(publishing, policy),
        'financial_anomalies': check_financial_anomalies(finance)
    }

    total_violations = sum(len(v) for v in violations.values())
    ai_analysis = analyze_with_ai(violations)

    report = {
        'date': today_str(),
        'total_violations': total_violations,
        'violations': violations,
        'ai_analysis': ai_analysis,
        'policy_version': policy.get('version', '2.0')
    }

    save_json('reports/risk-compliance.json', report)
    print(f'[{datetime.now(IST)}] Risk & Compliance complete → reports/risk-compliance.json ({total_violations} violations)')

if __name__ == '__main__':
    main()