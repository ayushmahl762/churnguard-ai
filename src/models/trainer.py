"""
trainer.py
----------
End-to-end ML pipeline:
  - Preprocessing (scale + encode)
  - Class imbalance handling (SMOTE)
  - Model comparison (LR, RF, XGBoost)
  - Threshold optimisation (maximise F2 to favour recall)
  - SHAP explainability
  - Saves model + predictions to disk + SQLite
"""

import pandas as pd
import numpy as np
import sqlite3
import joblib
import logging
import warnings
from pathlib import Path

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    roc_auc_score, classification_report, confusion_matrix,
    precision_recall_curve, f1_score, fbeta_score
)
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
log = logging.getLogger(__name__)

PROC_DIR  = Path("data/processed")
PRED_DIR  = Path("data/predictions")
MODEL_DIR = Path("src/models")
DB_PATH   = Path("database/churnguard.db")

# Imported from engineering.py
from src.features.engineering import (
    build_features, NUMERIC_FEATURES, CATEGORICAL_FEATURES, TARGET
)


# ─────────────────────────────────────────────────────────────
#  LOAD FEATURE MATRIX
# ─────────────────────────────────────────────────────────────
def load_feature_matrix() -> pd.DataFrame:
    customers = pd.read_csv(PROC_DIR / "customers_clean.csv")
    orders    = pd.read_csv(PROC_DIR / "orders_clean.csv")
    df = build_features(customers, orders)
    return df


# ─────────────────────────────────────────────────────────────
#  BUILD SKLEARN PIPELINE
# ─────────────────────────────────────────────────────────────
def build_pipeline(model) -> Pipeline:
    # Use only features that exist in the dataframe
    from sklearn.pipeline import Pipeline as SkPipeline
    num_pipe = SkPipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale",  StandardScaler()),
    ])
    cat_pipe = SkPipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("encode", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    preprocessor = ColumnTransformer([
        ("num", num_pipe, NUMERIC_FEATURES),
        ("cat", cat_pipe, CATEGORICAL_FEATURES),
    ], remainder="drop")

    return Pipeline([
        ("prep", preprocessor),
        ("clf",  model),
    ])


# ─────────────────────────────────────────────────────────────
#  TRAIN & COMPARE MODELS
# ─────────────────────────────────────────────────────────────
def train_all(df: pd.DataFrame) -> dict:
    """Compare 3 models, return best pipeline + evaluation dict."""
    # Filter to available columns
    avail_num = [c for c in NUMERIC_FEATURES if c in df.columns]
    avail_cat = [c for c in CATEGORICAL_FEATURES if c in df.columns]

    X = df[avail_num + avail_cat].copy()
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # Class imbalance: 8.9% churn — use scale_pos_weight for tree models
    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    spw = round(neg / pos, 1)
    log.info(f"Class ratio neg:pos = {neg}:{pos} | scale_pos_weight = {spw}")

    # SMOTE only if imbalanced-learn available
    try:
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import Pipeline as ImbPipeline
        smote = SMOTE(random_state=42, k_neighbors=5)
        use_smote = True
    except ImportError:
        use_smote = False
        log.warning("imbalanced-learn not installed — skipping SMOTE")

    candidates = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, class_weight="balanced", C=0.5, random_state=42
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200, class_weight="balanced",
            max_depth=6, random_state=42, n_jobs=-1
        ),
        "XGBoost": XGBClassifier(
            scale_pos_weight=spw, n_estimators=300, max_depth=5,
            learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            eval_metric="auc", random_state=42, verbosity=0
        ),
    }

    results = {}
    for name, model in candidates.items():
        pipe = build_pipeline(model)
        pipe.fit(X_train, y_train)
        probs = pipe.predict_proba(X_test)[:, 1]
        auc   = roc_auc_score(y_test, probs)
        cv_auc = cross_val_score(pipe, X_train, y_train, cv=5,
                                  scoring="roc_auc").mean()
        results[name] = {
            "pipe": pipe, "probs": probs,
            "auc": round(auc, 4), "cv_auc": round(cv_auc, 4)
        }
        log.info(f"  {name:25s} Test AUC={auc:.4f} | CV AUC={cv_auc:.4f}")

    # Best by test AUC
    best_name = max(results, key=lambda k: results[k]["auc"])
    log.info(f"Best model: {best_name}")

    return results, best_name, X_train, X_test, y_train, y_test, avail_num, avail_cat


# ─────────────────────────────────────────────────────────────
#  THRESHOLD OPTIMISATION
# ─────────────────────────────────────────────────────────────
def optimise_threshold(y_true, probs, beta=2.0) -> float:
    """
    Maximise F-beta (beta=2 weights recall 2× more than precision).
    Business rationale: missing a churner costs more than a false alarm.
    """
    prec, rec, thresholds = precision_recall_curve(y_true, probs)
    f_beta = ((1 + beta**2) * prec * rec) / (beta**2 * prec + rec + 1e-9)
    best_idx = np.argmax(f_beta[:-1])
    opt = float(thresholds[best_idx])
    log.info(f"Optimal threshold (F{beta}): {opt:.3f} | "
             f"Precision={prec[best_idx]:.3f} | Recall={rec[best_idx]:.3f}")
    return opt


# ─────────────────────────────────────────────────────────────
#  SHAP EXPLAINABILITY
# ─────────────────────────────────────────────────────────────
def compute_shap(pipe, X_test, feature_names) -> pd.DataFrame:
    try:
        import shap
        prep   = pipe.named_steps["prep"]
        model  = pipe.named_steps["clf"]
        X_prep = prep.transform(X_test)

        if hasattr(model, "coef_"):
            # Linear model (e.g. LogisticRegression)
            explainer = shap.LinearExplainer(model, X_prep)
            shap_vals = explainer.shap_values(X_prep)
        else:
            # Tree model (e.g. RandomForest, XGBoost)
            explainer = shap.TreeExplainer(model)
            shap_vals = explainer.shap_values(X_prep)

        # Handle list of arrays (e.g. RandomForest classification returns list of [class0, class1])
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]

        # Handle 3D array (e.g. multi-class or binary with shape samples, features, classes)
        if hasattr(shap_vals, "shape") and len(shap_vals.shape) == 3:
            shap_vals = shap_vals[:, :, 1] if shap_vals.shape[2] > 1 else shap_vals[:, :, 0]

        mean_shap = np.abs(shap_vals).mean(axis=0)
        shap_df   = pd.DataFrame({
            "feature":    feature_names[:len(mean_shap)],
            "mean_abs_shap": mean_shap
        }).sort_values("mean_abs_shap", ascending=False)

        log.info("SHAP computed")
        return shap_df
    except Exception as e:
        log.warning(f"SHAP skipped: {e}")
        return pd.DataFrame({"feature": feature_names, "mean_abs_shap": [0]*len(feature_names)})


# ─────────────────────────────────────────────────────────────
#  BATCH PREDICTIONS
# ─────────────────────────────────────────────────────────────
def predict_all(pipe, df: pd.DataFrame, avail_num, avail_cat,
                threshold: float) -> pd.DataFrame:
    X = df[avail_num + avail_cat].copy()
    probs  = pipe.predict_proba(X)[:, 1]
    labels = (probs >= threshold).astype(int)

    risk_tier = pd.cut(
        probs,
        bins=[0, 0.30, 0.55, 1.0],
        labels=["LOW", "MEDIUM", "HIGH"]
    )

    return pd.DataFrame({
        "customer_id":       df["customer_id"].values,
        "churn_probability": np.round(probs, 4),
        "predicted_churn":   labels,
        "risk_tier":         risk_tier,
        "model_version":     "xgb_v1",
    })


# ─────────────────────────────────────────────────────────────
#  PERSIST
# ─────────────────────────────────────────────────────────────
def save_everything(pipe, predictions: pd.DataFrame,
                    shap_df: pd.DataFrame, threshold: float,
                    model_name: str) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    PRED_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump({"pipe": pipe, "threshold": threshold, "model": model_name},
                MODEL_DIR / "churn_model.pkl")

    predictions.to_csv(PRED_DIR / "churn_predictions.csv", index=False)
    shap_df.to_csv(PRED_DIR / "shap_importance.csv", index=False)

    conn = sqlite3.connect(DB_PATH)
    predictions.to_sql("churn_predictions", conn, if_exists="replace", index=False)
    shap_df.to_sql("shap_importance",       conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

    log.info("✅ Model, predictions, SHAP saved.")


# ─────────────────────────────────────────────────────────────
#  FULL PIPELINE ENTRY POINT
# ─────────────────────────────────────────────────────────────
def run():
    df = load_feature_matrix()
    results, best_name, X_train, X_test, y_train, y_test, avail_num, avail_cat = train_all(df)

    best  = results[best_name]
    pipe  = best["pipe"]
    probs = best["probs"]

    threshold = optimise_threshold(y_test, probs, beta=2.0)

    feature_names = avail_num + avail_cat
    shap_df = compute_shap(pipe, X_test, feature_names)

    predictions = predict_all(pipe, df, avail_num, avail_cat, threshold)
    save_everything(pipe, predictions, shap_df, threshold, best_name)

    # Summary print
    y_pred_opt = (probs >= threshold).astype(int)
    print(f"\n{'='*50}")
    print(f"Model: {best_name} | AUC: {best['auc']}")
    print(f"Threshold: {threshold:.3f}")
    print(classification_report(y_test, y_pred_opt, target_names=["Retained", "Churned"]))
    print(f"HIGH risk:   {(predictions['risk_tier']=='HIGH').sum():,}")
    print(f"MEDIUM risk: {(predictions['risk_tier']=='MEDIUM').sum():,}")
    print(f"LOW risk:    {(predictions['risk_tier']=='LOW').sum():,}")

    return results, predictions, shap_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    run()
