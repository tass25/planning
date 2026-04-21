"""ComplexityAgent — L2-D risk scoring for SAS partitions.

Assigns a ``RiskLevel`` (LOW / MODERATE / HIGH / UNCERTAIN) to every
``PartitionIR`` block using a 6-feature LogReg + Platt-calibrated classifier
trained on the gold standard corpus.

A rule-based fallback is always available so the agent works without fitting.

Key design choices
------------------
* **LogReg + Platt scaling** (``CalibratedClassifierCV(method="sigmoid")``)
  gives reliable probabilities with the ~580 training samples available
  (80 % of 721 gold blocks).
* **ECE target < 0.08** — measured on a held-out 20 % split.
* **6 features** (see ``features.py``): line_count, nesting_depth,
  macro_pct, has_call_execute, type_weight, is_ambiguous.

Usage
-----
>>> agent = ComplexityAgent()
>>> partitions = await PartitionBuilderAgent().process(events)
>>> labelled = await agent.process(partitions, gold_dir=GOLD_DIR)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

# Serialised model lives next to this file; auto-trained from gold corpus on first run.
_MODEL_PATH = Path(__file__).parent / "complexity_model.joblib"
_GOLD_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "gold_standard"

from partition.base_agent import BaseAgent
from partition.models.enums import RiskLevel
from partition.models.partition_ir import PartitionIR

from .features import BlockFeatures, extract

# Gold tier string → RiskLevel
_TIER_MAP: dict[str, RiskLevel] = {
    "simple": RiskLevel.LOW,
    "medium": RiskLevel.MODERATE,
    "hard": RiskLevel.HIGH,
}

# Integer label → RiskLevel (for sklearn output)
_INT_LABEL: dict[int, RiskLevel] = {
    0: RiskLevel.LOW,
    1: RiskLevel.MODERATE,
    2: RiskLevel.HIGH,
}
_RISK_INT: dict[RiskLevel, int] = {v: k for k, v in _INT_LABEL.items()}

# Rule-based thresholds
_LINE_NORM = 200  # divisor used when building BlockFeatures.line_count_norm
_NEST_NORM = 5  # divisor used when building BlockFeatures.nesting_depth_norm
_HIGH_LINE = 50
_HIGH_NEST = 3
_HIGH_TYPE = 2.0
_LOW_LINE = 10
_LOW_TYPE = 1.0


class ComplexityAgent(BaseAgent):
    """Score each PartitionIR block with a RiskLevel.

    Attributes
    ----------
    _fitted : bool
        True once ``fit()`` has been called successfully.
    _model : CalibratedClassifierCV | None
        The trained Platt-calibrated LogReg, or None before fitting.
    """

    agent_name = "ComplexityAgent"

    def __init__(self) -> None:
        super().__init__()
        self._fitted = False
        self._model: CalibratedClassifierCV | None = None

        # Try to load a previously trained model from disk first.
        if _MODEL_PATH.exists():
            try:
                self._model = joblib.load(_MODEL_PATH)
                self._fitted = True
                self.logger.info("complexity_model_loaded", path=str(_MODEL_PATH))
            except Exception as exc:
                self.logger.warning("complexity_model_load_failed", error=str(exc))

        # If no saved model, auto-train from gold corpus if it's available.
        if not self._fitted and _GOLD_DIR.exists() and any(_GOLD_DIR.glob("*.gold.json")):
            try:
                self.fit(_GOLD_DIR)
            except Exception as exc:
                self.logger.warning("complexity_model_autotrain_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, gold_dir: Path, *, test_size: float = 0.2, seed: int = 42) -> dict[str, Any]:
        """Train LogReg + Platt calibration on the gold standard corpus.

        Labels come from the gold JSON ``tier`` field (file-level):
        ``simple`` → LOW, ``medium`` → MODERATE, ``hard`` → HIGH.

        Args:
            gold_dir: Directory containing ``*.gold.json`` annotation files.
            test_size: Fraction held out for evaluation (default 0.20).
            seed: Random seed for reproducible splits.

        Returns:
            Dict with ``train_acc``, ``test_acc``, ``ece``, ``n_train``,
            ``n_test`` for inspection and reporting.
        """
        X, y = self._load_gold_features(gold_dir)
        if len(X) == 0:
            raise ValueError(f"No gold blocks loaded from {gold_dir}")

        X_arr = np.array([f.to_list() for f in X])
        y_arr = np.array([_RISK_INT[label] for label in y])

        X_tr, X_te, y_tr, y_te = train_test_split(
            X_arr, y_arr, test_size=test_size, stratify=y_arr, random_state=seed
        )

        base = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced", C=1.0)
        self._model = CalibratedClassifierCV(base, method="sigmoid", cv=5)
        self._model.fit(X_tr, y_tr)
        self._fitted = True

        # Persist so subsequent runs skip re-training.
        try:
            joblib.dump(self._model, _MODEL_PATH)
        except Exception as exc:
            self.logger.warning(
                "complexity_model_save_failed", path=str(_MODEL_PATH), error=str(exc)
            )

        train_acc = float(np.mean(self._model.predict(X_tr) == y_tr))
        test_acc = float(np.mean(self._model.predict(X_te) == y_te))
        proba_te = self._model.predict_proba(X_te)
        ece = _compute_ece(y_te, proba_te)

        self.logger.info(
            "complexity_model_trained",
            n_train=len(X_tr),
            n_test=len(X_te),
            train_acc=round(train_acc, 3),
            test_acc=round(test_acc, 3),
            ece=round(ece, 4),
        )
        return {
            "train_acc": train_acc,
            "test_acc": test_acc,
            "ece": ece,
            "n_train": len(X_tr),
            "n_test": len(X_te),
        }

    async def process(  # type: ignore[override]
        self,
        partitions: list[PartitionIR],
    ) -> list[PartitionIR]:
        """Assign ``risk_level`` (and confidence) to every block in-place.

        Uses the fitted LogReg when available; falls back to rule-based
        heuristics otherwise.

        Args:
            partitions: PartitionIR blocks from PartitionBuilderAgent.

        Returns:
            The same list with ``risk_level`` and
            ``metadata["complexity_confidence"]`` populated.
        """
        results: list[PartitionIR] = []
        for part in partitions:
            feats = extract(part)
            if self._fitted and self._model is not None:
                risk, conf = self._predict_model(feats)
            else:
                risk, conf = self._predict_rules(feats)

            updated_meta = dict(part.metadata)
            updated_meta["complexity_confidence"] = round(conf, 4)
            updated_meta["complexity_features"] = feats.to_list()

            results.append(part.model_copy(update={"risk_level": risk, "metadata": updated_meta}))

        self.logger.info("complexity_scored", n_blocks=len(results), fitted=self._fitted)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _predict_model(self, feats: BlockFeatures) -> tuple[RiskLevel, float]:
        """Predict using the fitted calibrated LogReg."""
        assert self._model is not None
        x = np.array([feats.to_list()])
        label = int(self._model.predict(x)[0])
        conf = float(np.max(self._model.predict_proba(x)[0]))
        return _INT_LABEL[label], conf

    def _predict_rules(self, feats: BlockFeatures) -> tuple[RiskLevel, float]:
        """Rule-based fallback (no training required).

        Rules (in priority order):
        1. CALL EXECUTE present → HIGH (0.90)
        2. type_weight >= 2.0 AND line_count_norm >= HIGH_LINE/200 → HIGH (0.85)
        3. nesting_depth_norm >= HIGH_NEST/5 → HIGH (0.80)
        4. line_count_norm >= HIGH_LINE/200 → HIGH (0.75)
        5. line_count_norm <= LOW_LINE/200 AND type_weight <= LOW_TYPE
           AND nesting_depth_norm == 0 → LOW (0.82)
        6. Otherwise → MODERATE (0.65)
        """
        lc = feats.line_count_norm * _LINE_NORM  # un-normalise
        nd = feats.nesting_depth_norm * _NEST_NORM

        if feats.has_call_execute:
            return RiskLevel.HIGH, 0.90
        if feats.type_weight >= _HIGH_TYPE and lc >= _HIGH_LINE:
            return RiskLevel.HIGH, 0.85
        if nd >= _HIGH_NEST:
            return RiskLevel.HIGH, 0.80
        if lc >= _HIGH_LINE:
            return RiskLevel.HIGH, 0.75
        if lc <= _LOW_LINE and feats.type_weight <= _LOW_TYPE and nd == 0:
            return RiskLevel.LOW, 0.82
        return RiskLevel.MODERATE, 0.65

    @staticmethod
    def _load_gold_features(
        gold_dir: Path,
    ) -> tuple[list[BlockFeatures], list[RiskLevel]]:
        """Load all blocks from gold JSON files and extract features.

        Returns parallel lists (features, labels).
        """
        from partition.models.enums import PartitionType

        X: list[BlockFeatures] = []
        y: list[RiskLevel] = []

        for gf in sorted(gold_dir.glob("*.gold.json")):
            data = json.loads(gf.read_text(encoding="utf-8"))
            tier = data.get("tier", "medium")
            label = _TIER_MAP.get(tier.lower(), RiskLevel.MODERATE)

            for block in data.get("blocks", []):
                pt_str = block.get("partition_type", "DATA_STEP")
                try:
                    pt = PartitionType(pt_str)
                except ValueError:
                    pt = PartitionType.DATA_STEP

                sas_path = gold_dir / Path(gf.stem.replace(".gold", "") + ".sas")
                source = ""
                if sas_path.exists():
                    try:
                        lines = sas_path.read_text(encoding="utf-8", errors="replace").splitlines()
                        s, e = block["line_start"] - 1, block["line_end"]
                        source = "\n".join(lines[s:e])
                    except Exception:
                        pass

                # Build a minimal PartitionIR-like object
                dummy = PartitionIR(
                    file_id=UUID("00000000-0000-0000-0000-000000000000"),
                    partition_type=pt,
                    source_code=source,
                    line_start=block["line_start"],
                    line_end=block["line_end"],
                    metadata={
                        "nesting_depth": block.get("nesting_depth", 0),
                        "is_ambiguous": False,
                    },
                )
                X.append(extract(dummy))
                y.append(label)

        return X, y


# ---------------------------------------------------------------------------
# ECE utility
# ---------------------------------------------------------------------------


def _compute_ece(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE) for a multi-class classifier.

    Uses the one-vs-rest decomposition: for each class k, the model's
    predicted probability for class k is compared with the empirical rate
    of class k in each confidence bin.

    Args:
        y_true:  Integer class labels, shape (N,).
        y_proba: Predicted class probabilities, shape (N, K).
        n_bins:  Number of confidence bins (default 10).

    Returns:
        Scalar ECE ∈ [0, 1].
    """
    n_samples, n_classes = y_proba.shape
    ece = 0.0
    for k in range(n_classes):
        # Binary problem: "is this sample class k?"
        true_k = (y_true == k).astype(float)
        prob_k = y_proba[:, k]

        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
            mask = (prob_k >= lo) & (prob_k < hi)
            if not mask.any():
                continue
            conf_mean = float(prob_k[mask].mean())
            acc_mean = float(true_k[mask].mean())
            ece += (mask.sum() / n_samples) * abs(conf_mean - acc_mean)

    return ece / n_classes


def compute_ece(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10) -> float:
    """Public alias for ``_compute_ece`` (used in tests)."""
    return _compute_ece(y_true, y_proba, n_bins=n_bins)
