import sqlite3
import pandas as pd
import os

def export_to_csv():
    conn = sqlite3.connect('database/churnguard.db')
    output_dir = 'dashboard/exports/csv'
    os.makedirs(output_dir, exist_ok=True)
    
    # List of views/tables to export for Power BI / Tableau
    exports = [
        # Raw/Processed Tables
        'customers',
        'orders',
        'monthly_revenue',
        'product_summary',
        # ML Outputs
        'churn_predictions',
        'shap_importance',
        # Business Views
        'v_executive_kpis',
        'v_churn_by_tier',
        'v_churn_by_channel',
        'v_revenue_trend'
    ]
    
    for item in exports:
        df = pd.read_sql(f"SELECT * FROM {item}", conn)
        df.to_csv(f"{output_dir}/{item}.csv", index=False)
        print(f"Exported {item} to CSV.")
    
    conn.close()

if __name__ == "__main__":
    export_to_csv()