"""The candidate model zoo, mirroring what an AutoML `compare_models` would sweep.

Each entry is a lazily-constructed sklearn-compatible estimator plus a family label
used for grouping in the leaderboard.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from xgboost import XGBClassifier, XGBRegressor


@dataclass
class Candidate:
    name: str
    family: str  # linear|tree|boosting|neighbors|bayes
    factory: Callable[[], Any]


def classification_zoo() -> list[Candidate]:
    return [
        Candidate("Logistic Regression", "linear", lambda: LogisticRegression(max_iter=1000)),
        Candidate("Random Forest", "tree", lambda: RandomForestClassifier(n_estimators=200, n_jobs=-1)),
        Candidate("Extra Trees", "tree", lambda: ExtraTreesClassifier(n_estimators=200, n_jobs=-1)),
        Candidate("Gradient Boosting", "boosting", lambda: GradientBoostingClassifier()),
        Candidate(
            "XGBoost",
            "boosting",
            lambda: XGBClassifier(
                n_estimators=300, learning_rate=0.1, max_depth=6, n_jobs=-1,
                eval_metric="logloss", tree_method="hist",
            ),
        ),
        Candidate(
            "LightGBM",
            "boosting",
            lambda: LGBMClassifier(n_estimators=300, learning_rate=0.1, n_jobs=-1, verbose=-1),
        ),
        Candidate("K-Nearest Neighbors", "neighbors", lambda: KNeighborsClassifier()),
        Candidate("Gaussian Naive Bayes", "bayes", lambda: GaussianNB()),
    ]


def regression_zoo() -> list[Candidate]:
    return [
        Candidate("Linear Regression", "linear", lambda: LinearRegression()),
        Candidate("Ridge", "linear", lambda: Ridge()),
        Candidate("Random Forest", "tree", lambda: RandomForestRegressor(n_estimators=200, n_jobs=-1)),
        Candidate("Extra Trees", "tree", lambda: ExtraTreesRegressor(n_estimators=200, n_jobs=-1)),
        Candidate("Gradient Boosting", "boosting", lambda: GradientBoostingRegressor()),
        Candidate(
            "XGBoost",
            "boosting",
            lambda: XGBRegressor(
                n_estimators=300, learning_rate=0.1, max_depth=6, n_jobs=-1, tree_method="hist"
            ),
        ),
        Candidate(
            "LightGBM",
            "boosting",
            lambda: LGBMRegressor(n_estimators=300, learning_rate=0.1, n_jobs=-1, verbose=-1),
        ),
        Candidate("K-Nearest Neighbors", "neighbors", lambda: KNeighborsRegressor()),
    ]


def zoo_for(task_type: str) -> list[Candidate]:
    if task_type == "classification":
        return classification_zoo()
    if task_type == "regression":
        return regression_zoo()
    raise ValueError(f"No model zoo for task type '{task_type}'")
