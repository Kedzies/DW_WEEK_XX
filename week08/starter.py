from pathlib import Path
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

DATA = Path(__file__).parent / "data"
OUTPUT = Path(__file__).parent / "output"
OUTPUT.mkdir(exist_ok=True)

PROVINCE_MAP = {
	'กรุงเทพมหานคร':'Bangkok','กทม.':'Bangkok','Bangkok':'Bangkok','BANGKOK':'Bangkok',
	'ชลบุรี':'Chonburi','Chonburi':'Chonburi','ชลบุรี ':'Chonburi',
	'ระยอง':'Rayong','Rayong':'Rayong',
	'ขอนแก่น':'Khon Kaen','ขอนเเก่น':'Khon Kaen',
	'ภูเก็ต':'Phuket','Phuket':'Phuket',
	'เชียงใหม่':'Chiang Mai','Chiang Mai':'Chiang Mai'
}

def parse_discount(x):
	if pd.isna(x):
		return 0.0
	if isinstance(x, str) and x.strip().endswith('%'):
		try:
			return float(x.strip().replace('%',''))/100.0
		except:
			return 0.0
	try:
		return float(x)
	except:
		return 0.0

def run_pipeline():
	# Read orders
	orders_jan = pd.read_csv(DATA / 'orders_2026_01.csv')
	orders_feb = pd.read_csv(DATA / 'orders_2026_02.csv')

	# Align schema
	orders_feb = orders_feb.rename(columns={'ordered_at':'order_date','qty':'quantity','discount_pct':'discount'})
	orders_jan['discount'] = orders_jan['discount'].apply(parse_discount)
	orders_feb['discount'] = orders_feb['discount'].apply(parse_discount)

	for df in (orders_jan, orders_feb):
		df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
		df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce')

	orders_jan['order_date'] = pd.to_datetime(orders_jan['order_date'], errors='coerce')
	orders_feb['order_date'] = pd.to_datetime(orders_feb['order_date'], dayfirst=True, errors='coerce')

	orders = pd.concat([orders_jan, orders_feb], ignore_index=True, sort=False)
	orders = orders.rename(columns={'order_date':'order_datetime'})
	orders = orders[[ 'order_id','order_datetime','customer_id','product_id','quantity','unit_price','discount','channel']]

	# Data quality tracking
	dq = []
	def record(k,v):
		dq.append({'metric':k,'value':int(v) if isinstance(v,(bool,int)) else v})

	record('orders_rows_raw', len(orders))
	record('orders_missing_unit_price', orders['unit_price'].isna().sum())
	record('orders_missing_quantity', orders['quantity'].isna().sum())
	record('orders_negative_quantity', (orders['quantity']<0).sum())
	record('orders_duplicate_order_id', orders.duplicated(subset=['order_id']).sum())

	before = len(orders)
	orders = orders.dropna(subset=['order_id','unit_price','quantity'])
	record('orders_dropped_missing_price_or_qty', before - len(orders))
	orders['is_return'] = orders['quantity'] < 0

	# Customers
	customers = pd.read_csv(DATA / 'customers_crm.csv')
	customers['email'] = customers['email'].astype(str).str.strip().str.lower()
	customers.loc[customers['email'].isin(['nan','none','None']), 'email'] = None
	customers['province_raw'] = customers['province'].astype(str).str.strip()
	customers['province'] = customers['province_raw'].map(PROVINCE_MAP).fillna(customers['province_raw'])

	# Products
	products = pd.read_excel(DATA / 'product_master.xlsx')
	if 'product_id' not in products.columns:
		for c in products.columns:
			if c.lower().replace(' ','')=='productid':
				products = products.rename(columns={c:'product_id'})
	if 'name' in products.columns and 'product_name' not in products.columns:
		products = products.rename(columns={'name':'product_name'})
	if 'category_name' in products.columns and 'category' not in products.columns:
		products = products.rename(columns={'category_name':'category'})

	# Payments
	with open(DATA / 'payments.json','r',encoding='utf-8') as f:
		payments_raw = json.load(f)
	payments = pd.json_normalize(payments_raw)
	if 'payment.method' in payments.columns:
		payments = payments.rename(columns={'payment.method':'payment_method','payment.status':'payment_status'})

	record('customers_rows_raw', len(customers))
	record('products_rows_raw', len(products))
	record('payments_rows_raw', len(payments))

	# Merge
	merged = orders.merge(customers, on='customer_id', how='left', indicator='cust_merge')
	record('orders_unmatched_customers', (merged['cust_merge']=='left_only').sum())
	merged = merged.merge(products, on='product_id', how='left', indicator='prod_merge')
	record('orders_unmatched_products', (merged['prod_merge']=='left_only').sum())
	# payments columns might be named differently after normalization
	pay_cols = [c for c in payments.columns if c in ['order_id','payment_id','payment_method','payment_status','paid_at']]
	merged = merged.merge(payments[pay_cols], on='order_id', how='left', indicator='pay_merge')
	record('orders_unmatched_payments', (merged['pay_merge']=='left_only').sum())

	merged['net_sales'] = merged['quantity'] * merged['unit_price'] * (1 - merged['discount'])

	# Dim and fact
	dim_customer = customers.drop_duplicates(subset=['customer_id'])[['customer_id','full_name','email','province','signup_date']].copy()
	prod_cols = [c for c in ['product_id','product_name','category'] if c in products.columns]
	if prod_cols:
		dim_product = products[[c for c in ['product_id','product_name','category'] if c in products.columns]].drop_duplicates(subset=['product_id']).copy()
	else:
		dim_product = merged[['product_id']].drop_duplicates().copy()

	fact_sales = merged[['order_id','order_datetime','customer_id','product_id','quantity','unit_price','discount','net_sales','payment_status','channel']].copy()

	record('orders_rows_cleaned', len(orders))
	record('fact_sales_rows', len(fact_sales))
	record('fact_sales_negative_net_sales', (fact_sales['net_sales']<0).sum())
	record('duplicate_customer_ids', dim_customer.duplicated(subset=['customer_id']).sum())
	record('duplicate_product_ids', dim_product.duplicated(subset=['product_id']).sum())

	# Save outputs
	dim_customer.to_csv(OUTPUT / 'dim_customer.csv', index=False)
	dim_product.to_csv(OUTPUT / 'dim_product.csv', index=False)
	fact_sales.to_csv(OUTPUT / 'fact_sales.csv', index=False)
	pd.DataFrame(dq).to_csv(OUTPUT / 'data_quality_report.csv', index=False)

	summary_by_province = merged.groupby('province').agg(total_net_sales=pd.NamedAgg(column='net_sales', aggfunc='sum'), orders_count=pd.NamedAgg(column='order_id', aggfunc='nunique')).reset_index().sort_values('total_net_sales', ascending=False)
	summary_by_province.to_csv(OUTPUT / 'summary_by_province.csv', index=False)

	if 'category' in merged.columns:
		summary_by_category = merged.groupby('category').agg(total_net_sales=pd.NamedAgg(column='net_sales', aggfunc='sum'), orders_count=pd.NamedAgg(column='order_id', aggfunc='nunique')).reset_index().sort_values('total_net_sales', ascending=False)
	else:
		merged['category'] = 'UNKNOWN'
		summary_by_category = merged.groupby('category').agg(total_net_sales=pd.NamedAgg(column='net_sales', aggfunc='sum'), orders_count=pd.NamedAgg(column='order_id', aggfunc='nunique')).reset_index()
	summary_by_category.to_csv(OUTPUT / 'summary_by_category.csv', index=False)

	# Analysis summary (answers to 6 questions)
	total_net_sales = fact_sales['net_sales'].sum()
	total_orders = fact_sales['order_id'].nunique()
	prov_summary = fact_sales.merge(dim_customer[['customer_id','province']], on='customer_id', how='left').groupby('province').agg(total_net_sales=pd.NamedAgg('net_sales','sum')).reset_index().sort_values('total_net_sales', ascending=False)
	prod_summary = fact_sales.merge(dim_product[['product_id','product_name']] if 'product_name' in dim_product.columns else dim_product[['product_id']], on='product_id', how='left')
	if 'product_name' in prod_summary.columns:
		prod_by_sales = prod_summary.groupby(['product_id','product_name']).agg(total_net_sales=pd.NamedAgg('net_sales','sum')).reset_index().sort_values('total_net_sales',ascending=False)
	else:
		prod_by_sales = prod_summary.groupby(['product_id']).agg(total_net_sales=pd.NamedAgg('net_sales','sum')).reset_index().sort_values('total_net_sales',ascending=False)
	order_values = fact_sales.groupby('order_id').agg(order_value=pd.NamedAgg('net_sales','sum')).reset_index()
	average_order_value = order_values['order_value'].mean()
	returns = fact_sales[fact_sales['quantity']<0]
	returns_count = len(returns)
	returns_value = returns['net_sales'].sum()
	pay_status = fact_sales['payment_status'].value_counts(dropna=False)

	summary_lines = []
	summary_lines.append(f"Total net sales: {total_net_sales:,.2f}")
	summary_lines.append(f"Total unique orders: {total_orders}")
	summary_lines.append('\nTop 3 provinces by net sales:')
	for _,r in prov_summary.head(3).iterrows():
		summary_lines.append(f" - {r['province']}: {r['total_net_sales']:,.2f}")
	summary_lines.append('\nTop 5 products by net sales:')
	for _,r in prod_by_sales.head(5).iterrows():
		name = r.get('product_name', None)
		if pd.isna(name) or name is None:
			name = r['product_id']
		summary_lines.append(f" - {name} ({r['product_id']}): {r['total_net_sales']:,.2f}")
	summary_lines.append(f"\nAverage order value (AOV): {average_order_value:,.2f}")
	summary_lines.append(f"Returns: count={returns_count}, total_value={returns_value:,.2f}")
	summary_lines.append('\nPayment status distribution:')
	for idx,val in pay_status.items():
		summary_lines.append(f" - {idx}: {val}")

	(OUTPUT / 'analysis_summary.txt').write_text('\n'.join(summary_lines), encoding='utf-8')
	pd.DataFrame({'line':summary_lines}).to_csv(OUTPUT / 'analysis_summary.csv', index=False)

	# PDF report
	pdf_path = OUTPUT / 'analysis_report.pdf'
	with PdfPages(pdf_path) as pdf:
		fig, ax = plt.subplots(figsize=(8.27, 11.69))
		ax.axis('off')
		ax.text(0.01, 0.99, 'TechTrove Data Integration - Analysis Report', fontsize=14, weight='bold', va='top')
		ax.text(0.01, 0.94, '\n'.join(summary_lines), fontsize=9, va='top')
		pdf.savefig(fig, bbox_inches='tight')
		plt.close(fig)

	print('Pipeline finished. Outputs saved in', OUTPUT.resolve())

if __name__ == '__main__':
	run_pipeline()

