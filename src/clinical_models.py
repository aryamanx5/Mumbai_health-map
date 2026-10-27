"""The three cardiovascular classifiers: Logistic Regression, Random Forest and an ANN (MLP).

All three share one preprocessing design and one stratified train/test split. Every transformation
(feature engineering, imputation, scaling, one-hot encoding) lives inside the sklearn Pipeline, so it is fitted on
training folds only and the saved pipeline applies exactly the same steps at prediction time.
"""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from .clinical_data import BINARY, ENGINEERED, NOMINAL, NUMERIC, add_features
from .config import RANDOM_SEED

TEST_SIZE = 0.2
CV_FOLDS = 5
SCORING = "roc_auc"

MODELS = {
    "logistic_regression": dict(
        label="Logistic Regression", short="LR",
        estimator=lambda: LogisticRegression(max_iter=5000, random_state=RANDOM_SEED),
        grid={"model__C": [0.01, 0.1, 1.0, 10.0]},
        why="Linear baseline; coefficients are directly interpretable as log-odds effects."),
    "random_forest": dict(
        label="Random Forest", short="RF",
        estimator=lambda: RandomForestClassifier(random_state=RANDOM_SEED, n_jobs=-1),
        grid={"model__n_estimators": [300], "model__max_depth": [None, 4, 8],
              "model__min_samples_leaf": [1, 3, 5]},
        why="Non-linear ensemble of trees; captures interactions and gives feature importances."),
    "ann": dict(
        label="Artificial Neural Network (MLP)", short="ANN",
        estimator=lambda: MLPClassifier(max_iter=3000, random_state=RANDOM_SEED, learning_rate_init=0.001),
        grid={"model__hidden_layer_sizes": [(16,), (32,), (32, 16)], "model__alpha": [1e-4, 1e-3, 1e-2, 1e-1]},
        why="Small feed-forward network (one or two hidden layers) suited to ~800 training rows."),
}


def preprocessor(drop=()):
    num = [c for c in NUMERIC + ENGINEERED if c not in drop]
    bins = [c for c in BINARY if c not in drop]
    nom = [c for c in NOMINAL if c not in drop]
    return ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), num),
        ("bin", SimpleImputer(strategy="most_frequent"), bins),
        ("nom", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), nom),
    ], verbose_feature_names_out=True)


def make_pipeline(key, drop=()):
    return Pipeline([
        ("features", FunctionTransformer(add_features)),
        ("prep", preprocessor(drop)),
        ("model", MODELS[key]["estimator"]()),
    ])


def feature_names(pipe):
    return [n.split("__", 1)[1] for n in pipe.named_steps["prep"].get_feature_names_out()]


def ann_learning_curves(params, X_train, y_train, epochs=300, seed=RANDOM_SEED):
    """Train/validation log-loss per epoch for the chosen ANN settings.

    Diagnostic only: an inner 80/20 split of the TRAINING data (the test set is never touched); preprocessing is
    fitted on the inner-train part. The deployed ANN is the GridSearchCV refit on the full training set.
    """
    from sklearn.metrics import log_loss
    from sklearn.model_selection import train_test_split

    Xa, Xv, ya, yv = train_test_split(X_train, y_train, test_size=0.2, stratify=y_train, random_state=seed)
    prep = Pipeline([("features", FunctionTransformer(add_features)), ("prep", preprocessor())])
    Za, Zv = prep.fit_transform(Xa), prep.transform(Xv)
    net = MLPClassifier(hidden_layer_sizes=params["model__hidden_layer_sizes"], alpha=params["model__alpha"],
                        learning_rate_init=0.001, random_state=seed)
    classes = np.array([0, 1])
    train_loss, val_loss = [], []
    for _ in range(epochs):
        net.partial_fit(Za, ya, classes=classes)
        train_loss.append(log_loss(ya, net.predict_proba(Za)[:, 1], labels=classes))
        val_loss.append(log_loss(yv, net.predict_proba(Zv)[:, 1], labels=classes))
    return dict(epoch=list(range(1, epochs + 1)), train_loss=train_loss, val_loss=val_loss,
                best_val_epoch=int(np.argmin(val_loss)) + 1, n_inner_train=len(ya), n_validation=len(yv))
