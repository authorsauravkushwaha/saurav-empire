import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))

RISK_KEYWORDS = {
    'high_risk': [
        'unlimited liability', 'indemnify', 'hold harmless', 'perpetual',
        'exclusive rights', 'world rights', 'all formats', 'derivative works',
        'irrevocable', 'waive', 'assign', 'sublicense', 'terminate for convenience',
        'liquidated damages', 'penalty', 'confidential', 'non-compete', 'non-solicit'
    ],
    'medium_risk': [
        'auto-renew', 'price increase', 'minimum commitment', 'volume discount',
        'marketing cooperation', 'data sharing', 'audit rights', 'most favored nation',
        'force majeure', 'governing law', 'jurisdiction', 'arbitration'
    ],
    'financial': [
        'royalty', 'advance', 'revenue share', 'commission', 'fee', 'payment terms',
        'net 30', 'net 60', 'invoice', 'late payment', 'interest', 'currency'
    ]
}

def analyze_contract(contract: dict) -> dict:
    text = contract.get('text', '').lower()
    title = contract.get('title', '')
    value = contract.get('value_inr', 0)
    party = contract.get('counterparty', '')
    
    risk_score = 0
    found_risks = {'high': [], 'medium': [], 'financial': []}
    
    for risk_level, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                found_risks[risk_level].append(kw)
                if risk_level == 'high_risk':
                    risk_score += 10
                elif risk_level == 'medium_risk':
                    risk_score += 5
                else:
                    risk_score += 2
    
    risk_level = 'low'
    if risk_score >= 30:
        risk_level = 'critical'
    elif risk_score >= 15:
        risk_level = 'high'
    elif risk_score >= 5:
        risk_level = 'medium'
    
    # AI analysis for complex contracts
    if risk_score > 10:
        prompt = f'''CONTRACT RISK ANALYSIS: {title}
PARTY: {party}
VALUE: ₹{value}
RISK KEYWORDS FOUND: {found_risks}
RISK SCORE: {risk_score}/100

Return JSON with:
- summary: 2-sentence risk summary
- critical_clauses: array of {{clause, risk, recommendation}}
- negotiation_points: array of {{point, suggested_language, priority}}
- approval_required: true/false
- estimated_review_hours: number'''
        try:
            response = ai_reason(prompt, 'You are a contract attorney. Return valid JSON only.')
            start = response.find('{')
            end = response.rfind('}') + 1
            ai_result = json.loads(response[start:end])
        except:
            ai_result = {'summary': f'Contract has {len(found_risks["high_risk"])} high-risk clauses', 'critical_clauses': [], 'negotiation_points': [], 'approval_required': True, 'estimated_review_hours': 2}
    else:
        ai_result = {'summary': 'Low risk contract', 'critical_clauses': [], 'negotiation_points': [], 'approval_required': False, 'estimated_review_hours': 0.5}
    
    return {
        'contract_id': contract.get('id', ''),
        'title': title,
        'counterparty': party,
        'value_inr': value,
        'risk_score': risk_score,
        'risk_level': risk_level,
        'found_risks': found_risks,
        'ai_analysis': ai_result,
        'auto_approve': risk_level == 'low' and value <= load_policy()['contracts']['auto_approve_limit_inr']
    }

def flag_contracts_for_review(contracts: dict) -> list:
    """Identify contracts needing human review"""
    flagged = []
    for contract in contracts.get('pending', []):
        analysis = analyze_contract(contract)
        if not analysis['auto_approve']:
            flagged.append(analysis)
    return flagged

def check_policy_compliance(contract: dict, policy: dict) -> dict:
    """Check contract against autonomy policy"""
    violations = []
    value = contract.get('value_inr', 0)
    auto_limit = policy['contracts']['auto_approve_limit_inr']
    
    if value > auto_limit:
        violations.append(f'Value ₹{value} exceeds auto-approve limit ₹{auto_limit}')
    
    excluded = policy['contracts']['excluded_categories']
    cat = contract.get('category', '')
    if cat in excluded:
        violations.append(f'Category "{cat}" is excluded from auto-approval')
    
    return {
        'compliant': len(violations) == 0,
        'violations': violations
    }

def main():
    print(f'[{datetime.now(IST)}] Contract Review starting...')
    contracts = load_json('data/contracts.json')
    policy = load_policy()
    
    # Analyze all pending contracts
    results = []
    for contract in contracts.get('pending', []):
        analysis = analyze_contract(contract)
        compliance = check_policy_compliance(contract, policy)
        analysis['policy_compliance'] = compliance
        results.append(analysis)
    
    # Flag for review
    flagged = [r for r in results if not r['auto_approve']]
    
    # Summary
    summary = {
        'total_pending': len(contracts.get('pending', [])),
        'auto_approved': len([r for r in results if r['auto_approve']]),
        'flagged_for_review': len(flagged),
        'by_risk_level': {
            'critical': len([r for r in results if r['risk_level'] == 'critical']),
            'high': len([r for r in results if r['risk_level'] == 'high']),
            'medium': len([r for r in results if r['risk_level'] == 'medium']),
            'low': len([r for r in results if r['risk_level'] == 'low'])
        },
        'total_value_inr': sum(r['value_inr'] for r in results)
    }
    
    output = {
        'date': today_str(),
        'contracts': results,
        'flagged': flagged,
        'summary': summary
    }
    
    save_json('data/contract_review.json', output)
    print(f'[{datetime.now(IST)}] Contract Review complete → data/contract_review.json ({summary["flagged_for_review"]} flagged)')

if __name__ == '__main__':
    main()