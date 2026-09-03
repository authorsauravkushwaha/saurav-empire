import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str
from utils.ai_router import ai_reason

IST = timezone(timedelta(hours=5, minutes=30))

def calculate_kpis(finance: dict, leads: dict, content: dict, experiments: dict, publishing: dict) -> dict:
    revenue = finance.get('mtd_revenue_inr', 0)
    expenses = finance.get('mtd_expenses_inr', 0)
    profit = revenue - expenses
    
    total_leads = leads.get('total', 0)
    qualified = leads.get('qualified', 0)
    conversion_rate = round(qualified / total_leads * 100, 2) if total_leads > 0 else 0
    
    content_pieces = content.get('total_pieces', 0)
    reels = content.get('reels', 0)
    tweets = content.get('tweets', 0)
    blogs = content.get('blogs', 0)
    
    active_experiments = len(experiments.get('active', []))
    completed_experiments = len(experiments.get('completed', []))
    winning_experiments = len([e for e in experiments.get('completed', []) if e.get('winner', False)])
    
    books_optimized = publishing.get('summary', {}).get('books_optimized', 0)
    price_tests = publishing.get('summary', {}).get('price_tests', 0)
    
    return {
        'financial': {
            'mtd_revenue_inr': revenue,
            'mtd_expenses_inr': expenses,
            'mtd_profit_inr': profit,
            'profit_margin_pct': round(profit / revenue * 100, 2) if revenue > 0 else 0
        },
        'leads': {
            'total': total_leads,
            'qualified': qualified,
            'conversion_rate_pct': conversion_rate,
            'cost_per_lead_inr': round(expenses / qualified, 2) if qualified > 0 else 0
        },
        'content': {
            'total_pieces': content_pieces,
            'reels': reels,
            'tweets': tweets,
            'blogs': blogs,
            'velocity_per_day': round(content_pieces / 7, 2)
        },
        'experiments': {
            'active': active_experiments,
            'completed': completed_experiments,
            'winning': winning_experiments,
            'win_rate_pct': round(winning_experiments / completed_experiments * 100, 2) if completed_experiments > 0 else 0
        },
        'publishing': {
            'books_optimized': books_optimized,
            'price_tests_running': price_tests,
            'catalog_size': 50,
            'hero_books': 10
        }
    }

def generate_ai_insights(kpis: dict) -> dict:
    prompt = f'''ANALYTICS INSIGHTS FOR SAURAV AI EMPIRE — {today_str()}
KPIs:
{json.dumps(kpis, indent=2)}

Return JSON with:
- health_score: 1-100
- top_3_wins: array of {{metric, value, why_it_matters}}
- top_3_concerns: array of {{metric, value, action_needed}}
- strategic_recommendations: array of {{priority, action, expected_impact, effort}}
- trend_analysis: {{revenue_trend, lead_trend, content_trend, experiment_trend}}
- resource_allocation: {{focus_area, current_pct, recommended_pct}}'''
    try:
        response = ai_reason(prompt, 'You are a business analyst. Return valid JSON only.')
        start = response.find('{')
        end = response.rfind('}') + 1
        return json.loads(response[start:end])
    except Exception as e:
        return {
            'health_score': 50,
            'top_3_wins': [],
            'top_3_concerns': [],
            'strategic_recommendations': [],
            'trend_analysis': {},
            'resource_allocation': {},
            'error': str(e)
        }

def generate_chart_data(finance: dict, leads: dict, experiments: dict, content: dict) -> dict:
    """Generate data for dashboard charts"""
    return {
        'revenue_trend': finance.get('daily_revenue', {}),
        'lead_funnel': {
            'visitors': leads.get('visitors', 0),
            'subscribers': leads.get('total', 0),
            'qualified': leads.get('qualified', 0),
            'buyers': leads.get('buyers', 0)
        },
        'experiment_results': {
            'completed': len(experiments.get('completed', [])),
            'winners': len([e for e in experiments.get('completed', []) if e.get('winner', False)]),
            'by_type': {}
        },
        'content_performance': {
            'reels_views': content.get('reels_views', {}),
            'tweet_engagement': content.get('tweet_engagement', {}),
            'blog_traffic': content.get('blog_traffic', {})
        }
    }

def main():
    print(f'[{datetime.now(IST)}] Analytics Dashboard starting...')
    finance = load_json('reports/daily-finance.json')
    leads = load_json('data/leads.json')
    content = load_json('data/content_performance.json')
    experiments = load_json('reports/experiments.json')
    publishing = load_json('data/publishing_changes.json')
    
    kpis = calculate_kpis(finance, leads, content, experiments, publishing)
    insights = generate_ai_insights(kpis)
    charts = generate_chart_data(finance, leads, experiments, content)
    
    # Historical comparison (last 7 days)
    history_file = Path(__file__).parent.parent / 'reports' / 'kpi_history.json'
    history = []
    if history_file.exists():
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    history.append({'date': today_str(), 'kpis': kpis})
    history = history[-30:]  # Keep 30 days
    
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    
    output = {
        'date': today_str(),
        'kpis': kpis,
        'insights': insights,
        'charts': charts,
        'history': history[-7:]  # Last 7 days for trend
    }
    
    save_json('reports/analytics.json', output)
    print(f'[{datetime.now(IST)}] Analytics Dashboard complete → reports/analytics.json (health: {insights.get("health_score", 50)})')

if __name__ == '__main__':
    main()