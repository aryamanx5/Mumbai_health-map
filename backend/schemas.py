"""Pydantic request/response models. Field ranges mirror the cleaning rules in src/clinical_data.py."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PatientInput(BaseModel):
    """One patient's clinical values. Codes follow the dataset's published data dictionary."""
    age: int = Field(..., ge=18, le=100, description="Age in years")
    gender: Literal[0, 1] = Field(..., description="0 = female, 1 = male")
    chestpain: Literal[0, 1, 2, 3] = Field(..., description="0 typical angina, 1 atypical angina, 2 non-anginal pain, 3 asymptomatic")
    restingBP: float = Field(..., ge=80, le=220, description="Resting blood pressure, mm Hg")
    serumcholestrol: Optional[float] = Field(None, ge=80, le=700, description="Serum cholesterol, mg/dl. Leave empty if unknown: the training median is imputed")
    fastingbloodsugar: Literal[0, 1] = Field(..., description="1 if fasting blood sugar > 120 mg/dl")
    restingrelectro: Literal[0, 1, 2] = Field(..., description="0 normal, 1 ST-T wave abnormality, 2 left ventricular hypertrophy")
    maxheartrate: float = Field(..., ge=60, le=220, description="Maximum heart rate achieved, bpm")
    exerciseangia: Literal[0, 1] = Field(..., description="1 if exercise-induced angina")
    oldpeak: float = Field(..., ge=0, le=7, description="ST depression induced by exercise relative to rest")
    slope: Literal[1, 2, 3] = Field(..., description="Slope of peak exercise ST segment: 1 up, 2 flat, 3 down")
    noofmajorvessels: Literal[0, 1, 2, 3] = Field(..., description="Major vessels coloured by fluoroscopy")

    model_config = {"json_schema_extra": {"example": {
        "age": 54, "gender": 1, "chestpain": 2, "restingBP": 150, "serumcholestrol": 290, "fastingbloodsugar": 0,
        "restingrelectro": 1, "maxheartrate": 140, "exerciseangia": 1, "oldpeak": 2.4, "slope": 2,
        "noofmajorvessels": 1}}}


class ModelPrediction(BaseModel):
    model: str
    label: str
    probability: float = Field(..., description="Predicted probability of heart disease (class 1)")
    predicted_class: int
    predicted_label: str
    test_roc_auc: float
    test_accuracy: float


class PredictionResponse(BaseModel):
    predictions: list[ModelPrediction]
    models_predicting_disease: int
    mean_probability: float
    probability_spread: float = Field(..., description="Max minus min probability across the three models")
    threshold: float
    imputed_fields: list[str]
    disclaimer: str


class Health(BaseModel):
    status: str
    models_loaded: list[str]
    data_ready: bool
