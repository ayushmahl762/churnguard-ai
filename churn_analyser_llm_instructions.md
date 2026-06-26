# ChurnGuard AI — Codebase Context & LLM Instructions
## Portfolio Project: AI-Augmented Customer Churn Analysis Dashboard

This document provides a complete guide to the **ChurnGuard AI** codebase, structured specifically to align with the goal of creating a high-impact portfolio project. It details the existing architecture, the state of the GitHub deliverables, and provides copy-pasteable instructions for an LLM to build the remaining features.

---

## 1. Project Goal & Impact

**Business Objective:** Drive measurable retention impact by identifying high-risk customer segments, quantifying the revenue at risk, and using AI to auto-summarize findings for non-technical stakeholders.

**Key Resume Highlights:**
* Built an end-to-end customer churn prediction and monitoring system.
* Implemented feature engineering (RFM, Loyalty, Risk flags) and trained classification models (XGBoost, Random Forest, Logistic Regression).
* Optimized classification thresholds to maximize the $F_2$-score (favoring recall to capture 84%+ of potential churners).
* Integrated an **AI-powered Natural Language Insight Generator** that auto-summarizes top churn risk segments in plain English for VP/executive stakeholders.
* Relayed predictions to a SQLite database for SQL query analysis and reporting.

---

## 2. Project Directory Structure & Current State

Here is the current state of the workspace directory:

```text
churn analyser/
├── .venv/                      # Python virtual environment
├── dashboard/                  # Dashboard and visualization assets
│   └── exports/                # Static PNG charts of analytical insights (e.g., churn by tier, revenue trends)
├── data/                       # Data storage directory
│   ├── raw/                    # Original messy CSV datasets
│   │   ├── customers.csv       # 8,000 rows (demographics, membership, churn label)
│   │   ├── orders.csv          # 25,000 rows (transactions, ratings, returns)
│   │   ├── monthly_revenue.csv # 75 months (macro revenue trends)
│   │   └── product_summary.csv # Catalog metrics
│   ├── processed/              # Cleaned datasets output by preprocessor
│   └── predictions/            # ML model inference outputs
│       ├── churn_predictions.csv  # Customer IDs, churn probabilities, and risk tiers
│       └── shap_importance.csv    # Computed SHAP feature importance rankings
├── database/                   # SQLite Database storage
│   ├── churnguard.db           # Consolidated relational database
│   └── churn_analytics.sql     # SQL analytics query library (Done)
├── notebooks/                  # Jupyter notebooks for interactive analysis
│   ├── 02_eda.ipynb            # Exploratory Data Analysis
│   └── 04_ml_pipeline.ipynb    # Prototyping model training & feature importance
├── src/                        # Core Python application package
│   ├── data/
│   │   └── preprocessor.py     # Data cleaning & SQLite DB construction pipeline (Done)
│   ├── features/
│   │   └── engineering.py      # RFM, Loyalty, and Risk feature generation (Done)
│   └── models/
│       ├── trainer.py          # ML pipeline (XGBoost/RF training & threshold optimization) (Done)
│       └── churn_model.pkl     # Serialized best trained model & optimal threshold (Done)
├── requirments.txt             # Python dependencies (includes anthropic, python-dotenv, shap)
└── verify_db.py                # SQL database table verification script
```

---

## 3. GitHub Deliverables Status

| Deliverable | Status | Location | Notes |
| :--- | :--- | :--- | :--- |
| **SQL Queries** | **Complete** | [database/churn_analytics.sql](file:///d:/coding/churn%20analyser/database/churn_analytics.sql) | 12 high-business-value queries targeting SQLite database. |
| **Python Notebooks** | **Complete** | [notebooks/](file:///d:/coding/churn%20analyser/notebooks/) | Covers EDA, features, and model benchmarking. |
| **Cleaned Data Pipeline** | **Complete** | [src/](file:///d:/coding/churn%20analyser/src/) | Modular python pipeline from raw data to predictions. |
| **LLM Summarizer Module** | **Pending** | `src/models/insight_generator.py` | Needs to query the DB, extract top churn groups, and query Anthropic/Gemini. |
| **Power BI Integration** | **Pending** | `dashboard/` | Needs data export configurations and a guide on connecting SQLite to Power BI. |
| **GitHub README.md** | **Pending** | `README.md` | Needs a business-impact-focused write-up. |

---

## 4. Feature Implementation Prompts for Next Steps

To build out the remaining features, copy and paste the prompts below into your LLM coding assistant:

### Prompt 1: Build the LLM Executive Summary Module (`src/models/insight_generator.py`)
```markdown
I need to implement the "AI Twist" for my Customer Churn Analysis project: an LLM-powered natural language insight generator that auto-summarizes the top churn risk segments for non-technical stakeholders.

I want you to write a Python script `src/models/insight_generator.py` that:
1. Connects to the SQLite database `database/churnguard.db`.
2. Queries the database to extract key data about high-risk customers, specifically:
   - Aggregated metrics from high-risk churners (e.g. membership tiers, preferred devices, acquisition channels, return rates, average review ratings).
   - The top 5 features from the `shap_importance` table.
   - Summaries of at-risk revenue by risk tier from the `churn_predictions` joined with `customers`.
3. Constructs a prompt that includes these data tables/metrics and sends them to the Anthropic API (using the `anthropic` package and loading `ANTHROPIC_API_KEY` from `.env`).
4. Asks Claude to write a high-level, business-focused "Executive Churn Insights Report" that:
   - Identifies the top 3 distinct customer segments at risk of churning.
   - Translates technical SHAP features into plain business behaviors (e.g., "Customers with return rates above 20% are 3x more likely to churn...").
   - Quantifies the total dollar value at risk.
   - Provides 3 actionable business recommendations to improve retention.
5. Saves the output to a text or markdown file `dashboard/exports/llm_executive_summary.md` so it can be committed to GitHub or displayed.
```

### Prompt 2: Setup SQLite to Power BI Connection & Data Exports
```markdown
My project data resides in a SQLite database `database/churnguard.db`. I need to build a Power BI dashboard to visualize the data, but Power BI requires a clear path to ingest SQLite tables or views.

Please help me create:
1. A python utility script `dashboard/export_for_bi.py` that connects to the SQLite database, extracts all tables and custom analytical views (like `v_executive_kpis`, `v_churn_by_tier`, `v_revenue_trend`), and writes them out as clean CSV files to `dashboard/exports/csv/` so they can be easily imported into Power BI/Tableau without needing local SQLite drivers.
2. A markdown guide `dashboard/POWERBI_GUIDE.md` detailing:
   - How to connect Power BI to the database using the SQLite ODBC Driver (Step-by-step instructions).
   - How to import the exported CSVs if they prefer a driverless setup.
   - A list of suggested visuals for the Power BI report:
     - KPI Cards: Total revenue at risk, overall churn rate, active customer count.
     - Slicers: Filter by country, membership tier, acquisition channel.
     - Bar chart: Churn rate vs. customer lifetime value (LTV) by membership tier.
     - Line chart: Month-over-Month revenue trend showing ARPU.
```

### Prompt 3: Create a High-Impact GitHub README.md
```markdown
I need a professional, portfolio-grade `README.md` file for my GitHub repository. The project is an "AI-Augmented Customer Churn Analysis Dashboard" built using Python (pandas, scikit-learn, XGBoost, SHAP), SQLite, Power BI, and the Anthropic Claude API.

Please write a detailed `README.md` at the root of the project that includes the following sections:
1. **Title & Headline**: A strong title explaining the business value (e.g., "ChurnGuard AI: AI-Augmented Customer Retention & Prediction Platform").
2. **Business Problem**: A clear narrative explaining why customer churn matters, the cost of acquiring customers vs. retaining them, and the target outcome (identifying at-risk high-value customers).
3. **Key Features**: Highlight the end-to-end data pipeline, feature engineering (RFM scores), model comparison (XGBoost outperforming with 84%+ F2 recall), SQLite database structure, and the LLM-powered insight generator.
4. **Project Architecture**: A textual block diagram showing the flow: Raw CSVs -> Python Preprocessor -> SQL Database -> ML Training & Inferences -> SQLite Views -> Power BI Dashboard & LLM insight generator.
5. **Key Business Metrics (Mocked/Actual)**:
   - High-risk churners identified with 84%+ recall.
   - Projections showing $X revenue saved by proactively targeting the top 100 high-value at-risk customers.
6. **How to Run**: Simple instructions on setting up the `.venv`, installing `requirments.txt`, setting up the `.env` file, running the preprocessing/training scripts, and viewing the database.
```
