"""Config loader. SINGLE SOURCE OF TRUTH = config.yaml.
Zero hardcode em qualquer outro ficheiro.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class AppCfg(BaseModel):
    name: str
    tagline: str
    version: str
    host: str
    port: int
    refresh_seconds: int = Field(gt=0)
    dashboard_refresh_seconds: int = Field(gt=0)


class PathsCfg(BaseModel):
    db: str; inbox: str; processed: str; frontend: str


class AFIChannels(BaseModel):
    throughput: float; quality: float; machine: float
    timeline: float; operator: float; setup: float


class AFICfg(BaseModel):
    alpha: float = Field(gt=0)
    d_channels: AFIChannels
    seed: int

    @field_validator("d_channels")
    @classmethod
    def weights_sum_one(cls, v):
        s = sum(v.model_dump().values())
        if abs(s - 1.0) > 1e-6:
            raise ValueError(f"D-channel weights têm de somar 1.0, somam {s}")
        return v


class RectCfg(BaseModel):
    id: str; x: float; y: float; w: float; h: float


class CorridorCfg(RectCfg):
    label: str


class FiducialCfg(BaseModel):
    id: str; x: float; y: float


class FactoryCfg(BaseModel):
    viewbox_width: float = Field(gt=0)
    viewbox_height: float = Field(gt=0)
    corridors: list[CorridorCfg]
    crosswalks: list[RectCfg]
    fiducials: list[FiducialCfg]


class StationCfg(BaseModel):
    id: str
    name: str
    sector: Literal["pre", "correr", "abrir", "expedicao"]
    target_m2_per_hour: float = Field(ge=0)
    x: float; y: float; w: float = Field(gt=0); h: float = Field(gt=0)
    kind: Literal["machine", "assembly", "finishing", "buffer", "storage", "dispatch"]


class ThresholdsCfg(BaseModel):
    green_min: float = Field(ge=0, le=1)
    amber_min: float = Field(ge=0, le=1)
    sustained_minutes: int = Field(gt=0)
    order_urgency_days: int = Field(gt=0)

    @field_validator("amber_min")
    @classmethod
    def _amber_lt_green(cls, v, info):
        if "green_min" in info.data and v >= info.data["green_min"]:
            raise ValueError("amber_min tem de ser < green_min")
        return v


class AlertsCfg(BaseModel):
    routing: dict[str, str]
    severity_to_escalate: int = Field(ge=1, le=4)


class RoleCfg(BaseModel):
    id: str; name: str; level: int; color: str


class MemberCfg(BaseModel):
    id: str; name: str; role: str
    station_assigned: str | None = None
    initials: str


class TeamsCfg(BaseModel):
    roles: list[RoleCfg]
    members: list[MemberCfg]


class CSVSchemaCfg(BaseModel):
    preference: dict[str, str]
    primavera: dict[str, str]


class TrendCfg(BaseModel):
    term: str
    series: list[float]


class StrategicPriorityCfg(BaseModel):
    id: str; title: str
    confidence: float = Field(ge=0, le=1)
    horizon_months: int = Field(gt=0)


class ScaleCfg(BaseModel):
    trends_pt: list[TrendCfg]
    strategic_priorities: list[StrategicPriorityCfg]


class SustainabilityTargets(BaseModel):
    carbon_reduction_pct: float
    reuse_increase_pct: float


class SustainabilityCfg(BaseModel):
    carbon_per_m2_produced: float
    carbon_per_m2_rework: float
    energy_kwh_per_m2: float
    material_reuse_pct: float
    targets: SustainabilityTargets


class AICfg(BaseModel):
    gemini_model: str
    gemini_input_usd_per_m: float = Field(gt=0)
    gemini_output_usd_per_m: float = Field(gt=0)
    daily_cap_calls: int = Field(gt=0)


class SupplierCfg(BaseModel):
    id: str; name: str
    category: Literal["perfis", "vidro", "ferragens", "consumiveis"]
    sustainability_score: int = Field(ge=0, le=100)
    certifications: list[str]
    delivery_days: int = Field(gt=0)
    location: str; contact: str


class CatalogItemCfg(BaseModel):
    id: str; name: str; supplier_id: str
    category: Literal["perfis", "vidro", "ferragens", "consumiveis"]
    unit: str
    price_eur: float = Field(gt=0)
    co2_per_unit: float = Field(ge=0)
    recycled_pct: float = Field(ge=0, le=100)
    sustainability_score: int = Field(ge=0, le=100)
    stock_level: int = Field(ge=0)


class ProcurementCfg(BaseModel):
    suppliers: list[SupplierCfg]
    catalog: list[CatalogItemCfg]


class BrandCfg(BaseModel):
    primary: str; secondary: str; tertiary: str
    green_light_bg: str; green_whisper: str; white: str; ink_soft: str
    amber: str; red: str
    corridor: str; buffer_green: str; buffer_orange: str; buffer_yellow: str
    dispatch_blue: str; hairline: str
    font_display: str; font_body: str; font_mono: str


class WsLiveCfg(BaseModel):
    interior_base_temp_c: float
    interior_humidity_base_pct: float
    interior_co2_base_ppm: float
    interior_noise_base_db: float
    prod_rate_base_m2_min: float


class Config(BaseModel):
    app: AppCfg
    paths: PathsCfg
    afi: AFICfg
    factory: FactoryCfg
    stations: list[StationCfg]
    thresholds: ThresholdsCfg
    alerts: AlertsCfg
    teams: TeamsCfg
    csv_schema: CSVSchemaCfg
    scale: ScaleCfg
    sustainability: SustainabilityCfg
    ai: AICfg
    procurement: ProcurementCfg
    brand: BrandCfg
    ws_live: WsLiveCfg


def load_config(path: str | Path = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(**raw)


_CFG: Config | None = None


def cfg() -> Config:
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG
