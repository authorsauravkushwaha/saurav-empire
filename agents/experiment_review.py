import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import save_json, today_str
from utils.ai_router import ai_reason
def load_experiments() -> dict:
    try:
        with open(Path(__file__).parent.parent.parent / 'reports/experiments.json', 'r') as f:
            return json.load(f)
    except:
        return {'active': [], 'completed': [], 'insights': []}
def save_experiments(data: dict):
    save_json('reports/experiments.json', data)
def analyze_experiment(exp: dict) -> dict:
    prompt = f'''
Analyze this A/B test experiment:
Name: {exp.get('name', '')}
Hypothesis: {exp.get('hypothesis', '')}
Variant A: {exp.get('variant_a', {})}
Variant B: {exp.get('variant_b', {})}
Results A: {exp.get('results_a', {})}
Results B: {exp.get('results_b', {})}
Duration days: {exp.get('duration_days', 0)}
Return JSON:
- winner: 'A' | 'B' | 'inconclusive'
- confidence_pct: 0-100
- key_insight: one sentence
- recommendation: 'scale_A' | 'scale_B' | 'iterate' | 'kill'
- next_test: suggested follow-up experiment
'''
    response = ai_reason(prompt, 'You are a growth experiment analyst. Return valid JSON only.')
    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except:
        return {'winner': 'inconclusive', 'confidence_pct': 0, 'key_insight': 'Parse failed', 'recommendation': 'iterate', 'next_test': ''}
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    print(f'[{datetime.now(IST)}] Experiment Review starting...')
    data = load_experiments()
    for exp in data.get('active', []):
        if exp.get('status') == 'completed' and 'analysis' not in exp:
            exp['analysis'] = analyze_experiment(exp)
            data['completed'].append(exp)
    data['active'] = [e for e in data.get('active', []) if e.get('status') != 'completed']
    insights = []
    for exp in data.get('completed', [])[-5:]:
        a = exp.get('analysis', {})
        insights.append(f"{exp['name']}: {a.get('key_insight', '')} → {a.get('recommendation', '')}")
    data['insights'] = insights[-10:]
    save_experiments(data)
    print(f'[{datetime.now(IST)}] Experiment Review complete → reports/experiments.json')
if __name__ == '__main__':
    main()
