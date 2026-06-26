import sqlite3
import pandas as pd
import os
from dotenv import load_dotenv
from google import genai
from pathlib import Path

# Load environment variables
env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

# Initialize Gemini Client
api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

def generate_executive_summary():
    # 1. Connect to Database
    db_path = Path(__file__).resolve().parents[2] / 'database/churnguard.db'
    conn = sqlite3.connect(db_path)
    
    try:
        # 2. Extract Data
        high_risk_df = pd.read_sql("""
            SELECT customer_id, churn_probability, risk_tier 
            FROM churn_predictions 
            WHERE churn_probability > 0.8 
            LIMIT 100
        """, conn)
        
        shap_df = pd.read_sql("SELECT * FROM shap_importance LIMIT 5", conn)
    finally:
        conn.close()

    # 3. Construct Prompt
    prompt = f"""
    You are a Senior Customer Success Manager. Analyze this data:
    - High-Risk Customer Sample: {high_risk_df.to_string()}
    - Top Churn Drivers: {shap_df.to_string()}
    
    Generate a professional "Executive Churn Insights Report".
    Identify 3 at-risk segments, translate SHAP features into business behaviors, 
    and provide 3 concrete retention strategies.
    """

    # 4. API Call to Gemini
    # Using 'gemini-2.5-flash' which is efficient for high-volume tasks
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )

    # 5. Save Output
    output_path = Path(__file__).resolve().parents[2] / "dashboard/exports/llm_executive_summary.md"
    os.makedirs(output_path.parent, exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(response.text)
    
    print(f"Success: Summary generated at {output_path}")

if __name__ == "__main__":
    generate_executive_summary()