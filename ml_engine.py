import logging
import pandas as pd
import numpy as np
import joblib
import os
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from typing import Dict, Any, Optional

# Constants
MODEL_DIR = "ml_models"
RUG_MODEL_PATH = os.path.join(MODEL_DIR, "rug_classifier.pkl")
MOON_MODEL_PATH = os.path.join(MODEL_DIR, "moonshot_regressor.pkl")

class Oracle:
    """The Machine Learning Engine for Alpha Prediction (Stage 12)."""
    def __init__(self, db):
        self.db = db
        self.rug_model = None
        self.moon_model = None
        
        # Create models directory
        if not os.path.exists(MODEL_DIR):
            os.makedirs(MODEL_DIR)
            
        # Try loading existing models
        self.load_models()

    def load_models(self):
        """Load trained models from disk."""
        try:
            if os.path.exists(RUG_MODEL_PATH):
                self.rug_model = joblib.load(RUG_MODEL_PATH)
                logging.info("🔮 Oracle: Rug Classifier loaded.")
                
            if os.path.exists(MOON_MODEL_PATH):
                self.moon_model = joblib.load(MOON_MODEL_PATH)
                logging.info("🔮 Oracle: Moonshot Regressor loaded.")
        except Exception as e:
            logging.error(f"Failed to load ML models: {e}")

    def train_models(self, trades_df: pd.DataFrame):
        """Train predictive models on historical trade data."""
        logging.info("🧠 Oracle: Starting model training...")
        
        if trades_df.empty:
            logging.warning("No data to train on.")
            return

        # Preprocessing Features
        # Assuming df has columns: liquidity_locked, top_10_holder_pct, account_age_days, social_score, is_rug, max_roi
        required_cols = ['liquidity_locked', 'top_10_holder_pct', 'creator_account_age_days', 'social_score', 'initial_buy_velocity']
        
        X = trades_df[required_cols]
        y_rug = trades_df['is_rug']
        y_roi = trades_df['max_roi_x']
        
        # Training Rug Classifier
        classifier = Pipeline([
            ('imputer', SimpleImputer(strategy='mean')),
            ('scaler', StandardScaler()),
            ('rf', RandomForestClassifier(n_estimators=100, random_state=42))
        ])
        classifier.fit(X, y_rug)
        joblib.dump(classifier, RUG_MODEL_PATH)
        self.rug_model = classifier
        logging.info("✅ Rug Classifier trained and saved.")

        # Training Moonshot Regressor
        regressor = Pipeline([
            ('imputer', SimpleImputer(strategy='mean')),
            ('scaler', StandardScaler()),
            ('gb', GradientBoostingRegressor(n_estimators=100, random_state=42))
        ])
        regressor.fit(X, y_roi)
        joblib.dump(regressor, MOON_MODEL_PATH)
        self.moon_model = regressor
        logging.info("✅ Moonshot Regressor trained and saved.")

    async def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Real-time inference pipeline."""
        input_data = pd.DataFrame([features])
        
        result = {
            "rug_probability": 0.0,
            "predicted_roi": 1.0,
            "oracle_verdict": "NEUTRAL"
        }
        
        # Default behavior if models aren't trained yet
        if not self.rug_model or not self.moon_model:
            return result

        try:
            rug_prob = self.rug_model.predict_proba(input_data)[0][1]
            pred_roi = self.moon_model.predict(input_data)[0]
            
            result["rug_probability"] = float(rug_prob)
            result["predicted_roi"] = float(pred_roi)
            
            if rug_prob > 0.8:
                result["oracle_verdict"] = "HARD_REJECT"
            elif pred_roi > 5.0 and rug_prob < 0.2:
                result["oracle_verdict"] = "MOONSHOT"
            elif rug_prob < 0.4:
                result["oracle_verdict"] = "SAFE"
                
        except Exception as e:
            logging.error(f"Inference error: {e}")
            
        return result
