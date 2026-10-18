import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, f1_score, classification_report
import xgboost as xgb

# ---------------------------------------------------------------------------
# 1. Synthetic Dataset Generation
# ---------------------------------------------------------------------------
def generate_synthetic_data(num_samples=1500, random_state=42):
    np.random.seed(random_state)

    monthly_revenue = np.random.uniform(2000, 150000, size=num_samples)
    transaction_frequency = np.random.randint(10, 800, size=num_samples)
    default_rate = np.random.beta(a=0.5, b=5, size=num_samples)  # Skewed low
    inventory_turnover = np.random.uniform(0.5, 12.0, size=num_samples)
    avg_basket_size = monthly_revenue / np.maximum(transaction_frequency, 1)
    repayment_history_score = np.random.randint(300, 850, size=num_samples)

    logit = (
        0.00008 * monthly_revenue +
        0.003 * transaction_frequency -
        8.0 * default_rate +
        0.25 * inventory_turnover +
        0.008 * repayment_history_score -
        4.0
    )
    probabilities = 1 / (1 + np.exp(-logit))
    creditworthy_labels = (probabilities > 0.5).astype(int)

    return pd.DataFrame({
        'monthly_revenue': monthly_revenue,
        'transaction_frequency': transaction_frequency,
        'default_rate': default_rate,
        'inventory_turnover': inventory_turnover,
        'avg_basket_size': avg_basket_size,
        'repayment_history_score': repayment_history_score,
        'is_creditworthy': creditworthy_labels
    })

# ---------------------------------------------------------------------------
# 2. Pipeline Training & Evaluation
# ---------------------------------------------------------------------------
def train_and_evaluate_models():
    print("Generating training dataset...")
    df = generate_synthetic_data(num_samples=1500)

    X = df[[
        'monthly_revenue',
        'transaction_frequency',
        'default_rate',
        'inventory_turnover',
        'avg_basket_size',
        'repayment_history_score'
    ]]
    y = df['is_creditworthy']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    candidates = {
        'LogisticRegression': Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', LogisticRegression(random_state=42))
        ]),
        'RandomForest': Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
        ]),
        'XGBoost': Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42))
        ])
    }

    best_score = -1.0
    best_model_name = None
    best_pipeline = None

    print("\n--- Training Candidate Models ---")
    for name, pipeline in candidates.items():
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        y_proba = pipeline.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, y_proba)
        f1 = f1_score(y_test, y_pred)

        print(f"\nModel: {name}")
        print(f"  ROC-AUC Score: {auc:.4f}")
        print(f"  F1 Score:      {f1:.4f}")

        if auc > best_score:
            best_score = auc
            best_model_name = name
            best_pipeline = pipeline

    print("\n==========================================")
    print(f"Selected Best Model: {best_model_name} (ROC-AUC: {best_score:.4f})")
    print("==========================================")

    y_pred_best = best_pipeline.predict(X_test)
    print("\nDetailed Performance Report:")
    print(classification_report(y_test, y_pred_best))

    output_dir = os.path.join(os.path.dirname(__file__), 'credit_scoring', 'ml_models')
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, 'credit_scorer.joblib')

    joblib.dump(best_pipeline, model_path)
    print(f"\nSuccessfully saved serialized model artifact to:\n  {model_path}")

if __name__ == '__main__':
    train_and_evaluate_models()

