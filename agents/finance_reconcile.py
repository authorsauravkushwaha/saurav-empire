import json
import csv
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import save_json, load_course, today_str
def parse_gumroad_csv(filepath: Path) -> list:
    sales = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sales.append({
                    'platform': 'gumroad',
                    'product_id': row.get('product_id', ''),
                    'product_name': row.get('product_name', ''),
                    'amount_usd': float(row.get('sale_price', 0)) / 100,
                    'currency': 'USD',
                    'customer_email': row.get('email', ''),
                    'customer_name': row.get('name', ''),
                    'sale_date': row.get('created_at', ''),
                    'is_affiliate': row.get('affiliate', '') != '',
                    'affiliate_email': row.get('affiliate_email', '')
                })
    except Exception as e:
        print(f'Gumroad CSV parse error: {e}')
    return sales
def parse_kdp_csv(filepath: Path) -> list:
    sales = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sales.append({
                    'platform': 'kdp',
                    'asin': row.get('ASIN', ''),
                    'title': row.get('Title', ''),
                    'royalty_inr': float(row.get('Royalty', 0)),
                    'units': int(row.get('Units', 0)),
                    'marketplace': row.get('Marketplace', 'IN'),
                    'period': row.get('Period', ''),
                    'currency': 'INR'
                })
    except Exception as e:
        print(f'KDP CSV parse error: {e}')
    return sales
def parse_stripe_csv(filepath: Path) -> list:
    sales = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sales.append({
                    'platform': 'stripe',
                    'amount_inr': float(row.get('amount', 0)) / 100,
                    'currency': 'INR',
                    'customer_email': row.get('customer_email', ''),
                    'product': row.get('description', ''),
                    'date': row.get('created', ''),
                    'fee_inr': float(row.get('fee', 0)) / 100
                })
    except Exception as e:
        print(f'Stripe CSV parse error: {e}')
    return sales
def main():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    print(f'[{datetime.now(IST)}] Finance Reconcile starting...')
    imports_dir = Path(__file__).parent.parent.parent / 'data/imports'
    all_sales = []
    for csv_file in imports_dir.glob('*.csv'):
        fname = csv_file.name.lower()
        if 'gumroad' in fname:
            all_sales.extend(parse_gumroad_csv(csv_file))
        elif 'kdp' in fname:
            all_sales.extend(parse_kdp_csv(csv_file))
        elif 'stripe' in fname:
            all_sales.extend(parse_stripe_csv(csv_file))
    total_revenue_inr = sum(s.get('royalty_inr', s.get('amount_inr', s.get('amount_usd', 0) * 83)) for s in all_sales)
    by_platform = {}
    by_product = {}
    for s in all_sales:
        plat = s.get('platform', 'unknown')
        by_platform[plat] = by_platform.get(plat, 0) + s.get('royalty_inr', s.get('amount_inr', s.get('amount_usd', 0) * 83))
        prod = s.get('product_name') or s.get('title') or s.get('product') or s.get('asin', 'unknown')
        by_product[prod] = by_product.get(prod, 0) + s.get('royalty_inr', s.get('amount_inr', s.get('amount_usd', 0) * 83))
    mtd_revenue = total_revenue_inr
    report = {
        'date': today_str(),
        'total_sales_count': len(all_sales),
        'total_revenue_inr': round(total_revenue_inr, 2),
        'mtd_revenue_inr': round(mtd_revenue, 2),
        'by_platform': {k: round(v, 2) for k, v in by_platform.items()},
        'by_product': {k: round(v, 2) for k, v in by_product.items()},
        'top_products': sorted(by_product.items(), key=lambda x: x[1], reverse=True)[:10],
        'raw_sales': all_sales
    }
    save_json('reports/daily-finance.json', report)
    print(f'[{datetime.now(IST)}] Finance Reconcile complete → reports/daily-finance.json (₹{total_revenue_inr:,.0f})')
if __name__ == '__main__':
    main()
