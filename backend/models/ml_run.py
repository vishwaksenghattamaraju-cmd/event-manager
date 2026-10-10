"""Model run tracking for ML training, metrics evaluation, and synthetic data auditing."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from backend.models.base import Base


class ModelRun(Base):
    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False, default="RandomForestRegressor")
    version = Column(String(20), nullable=False)

    # Evaluation metrics
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    r2_score = Column(Float, nullable=True)

    baseline_mae = Column(Float, nullable=True)
    is_better_than_baseline = Column(Boolean, nullable=True)

    # Training metadata
    training_samples_count = Column(Integer, nullable=False)
    synthetic_samples_count = Column(Integer, nullable=False, default=0)
    data_date_range_start = Column(DateTime, nullable=True)
    data_date_range_end = Column(DateTime, nullable=True)
    model_file_path = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model_name": self.model_name,
            "version": self.version,
            "mae": self.mae,
            "rmse": self.rmse,
            "r2_score": self.r2_score,
            "baseline_mae": self.baseline_mae,
            "is_better_than_baseline": self.is_better_than_baseline,
            "training_samples_count": self.training_samples_count,
            "synthetic_samples_count": self.synthetic_samples_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
