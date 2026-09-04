"""Библиотека анализа телеметрии RaceChrono: чтение, физика, графики, PDF-отчет."""
from .analysis import run_analysis
from .config import AnalysisConfig, AnalysisResult, parse_laps_spec

__all__ = ["run_analysis", "AnalysisConfig", "AnalysisResult", "parse_laps_spec"]
