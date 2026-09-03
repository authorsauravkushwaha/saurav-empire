import re
from typing import Dict, Any
POLICY = None
def load_policy():
    global POLICY
    if POLICY is None:
        import yaml
        from pathlib import Path
        with open(Path(__file__).parent.parent.parent / 'config/autonomy_policy.yaml', 'r') as f:
            POLICY = yaml.safe_load(f)
    return POLICY
def validate_ad_spend(amount_inr: float) -> bool:
    policy = load_policy()
    return amount_inr <= policy['ad_spend']['daily_limit_inr']
def validate_contract_auto_approve(amount_inr: float, category: str) -> bool:
    policy = load_policy()
    if amount_inr > policy['contracts']['auto_approve_limit_inr']:
        return False
    if category in policy['contracts']['excluded_categories']:
        return False
    return True
def validate_email_send(count: int, warm_leads_only: bool = True) -> bool:
    policy = load_policy()
    if count > policy['communications']['email']['daily_limit']:
        return False
    if policy['communications']['email']['warm_leads_only'] and not warm_leads_only:
        return False
    return True
def validate_dm_send(count: int, personalized: bool = True) -> bool:
    policy = load_policy()
    if count > policy['communications']['dm']['daily_limit']:
        return False
    if policy['communications']['dm']['personalized_only'] and not personalized:
        return False
    return True
def validate_publishing_action(action: str, price_change_pct: float = 0) -> bool:
    policy = load_policy()
    if action in policy['publishing']['autonomous_actions']:
        if action == 'price_change' and abs(price_change_pct) > policy['publishing']['max_price_change_pct_per_week']:
            return False
        return True
    return False
def requires_approval(action: str, **kwargs) -> bool:
    return not validate_publishing_action(action, **kwargs)
