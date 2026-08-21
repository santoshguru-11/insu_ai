"""The three demo storylines, as plain data.

Keeping the numbers here — rather than inline in the seeding code — makes the
demo script reviewable by an engineer who cares whether the vibration figures
are plausible, without reading any persistence logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import (
    AssetStatus,
    ConfidenceBand,
    Criticality,
    EvidenceType,
    PartCheckStatus,
    ProductionImpact,
    ProposalStatus,
    RecommendedAction,
    ScenarioType,
    Severity,
    WorkflowStatus,
)

#: Anchor for every relative timestamp, so a re-seed produces a consistent story.
NOW = datetime.now(UTC)

# The maintenance window in the main demo: Saturday 22 August, 22:00-04:00.
SCENARIO_A_WINDOW_START = datetime(2026, 8, 22, 22, 0, tzinfo=UTC)
SCENARIO_A_WINDOW_HOURS = 6.0


SCENARIO_A: dict[str, Any] = {
    "scenario_type": ScenarioType.NORMAL,
    "asset": {
        "asset_code": "CAL-04-DRIVE",
        "name": "Calender Roll Drive Train",
        "plant_name": "Battery Plant",
        "line_name": "Calender Line 2",
        "criticality": Criticality.HIGH,
        "status": AssetStatus.DEGRADED,
    },
    "incident": {
        "trace_id": "tr_9f21",
        "severity": Severity.ISO_20816_3_BAND_C,
        "workflow_status": WorkflowStatus.APPROVAL_REQUIRED,
        "cloud_available": True,
        "detected_at": NOW - timedelta(hours=6),
    },
    "anomaly": {
        "signal_name": "bpfo_envelope_velocity",
        "observed_value": 4.2,
        "baseline_value": 1.1,
        "unit": "mm/s",
        "sigma_deviation": 6.4,
        "thermal_delta_c": 14.8,
        "window_count": 6,
        "persisted": True,
    },
    "diagnosis": {
        "failure_mode_code": "BRG_OUTER_RACE_WEAR",
        "fmea_reference": "FM-1182",
        "confidence": 0.87,
        "confidence_band": ConfidenceBand.HIGH,
        "recommended_action": RecommendedAction.SCHEDULE_REPLACEMENT,
        "recommended_action_note": (
            "Replace the drive-end bearing during the next planned changeover; "
            "the outer-race signature is unambiguous and still has runway."
        ),
        "similar_work_order_reference": "WO-40218",
        "rul_estimate_days": 18.0,
        "rul_ci_low_days": 12.0,
        "rul_ci_high_days": 26.0,
    },
    "evidence": [
        {
            "signal_name": "bpfo_envelope_velocity",
            "observed_value": 4.2,
            "baseline_value": 1.1,
            "unit": "mm/s",
            "evidence_type": EvidenceType.SPECTRAL_FEATURE,
            "weight": 0.45,
            "source_reference": "envelope-spectrum:2026-08-21T02:14Z",
        },
        {
            "signal_name": "bpfo_sigma_deviation",
            "observed_value": 6.4,
            "baseline_value": 1.0,
            "unit": "sigma",
            "evidence_type": EvidenceType.THRESHOLD_BREACH,
            "weight": 0.25,
            "source_reference": "baseline-model:cal-04-drive-de",
        },
        {
            "signal_name": "bearing_housing_temperature_delta",
            "observed_value": 14.8,
            "baseline_value": 0.0,
            "unit": "degC",
            "evidence_type": EvidenceType.SENSOR_READING,
            "weight": 0.20,
            "source_reference": "thermal-probe:de-housing",
        },
        {
            "signal_name": "anomaly_window_persistence",
            "observed_value": 6.0,
            "baseline_value": 0.0,
            "unit": "windows",
            "evidence_type": EvidenceType.TREND,
            "weight": 0.10,
            "source_reference": "sentinel:persistence-check",
        },
    ],
    "alternatives": [
        {
            "failure_mode_code": "MISALIGNMENT",
            "rejection_reason": (
                "Rejected: no 2x running-speed component is present in the spectrum."
            ),
            "confidence": 0.08,
        },
        {
            "failure_mode_code": "BRG_INNER_RACE_WEAR",
            "rejection_reason": (
                "Rejected: the BPFI signature is absent from the envelope spectrum."
            ),
            "confidence": 0.05,
        },
    ],
    "proposal": {
        "proposed_start_at": SCENARIO_A_WINDOW_START,
        "proposed_end_at": SCENARIO_A_WINDOW_START + timedelta(hours=SCENARIO_A_WINDOW_HOURS),
        "duration_hours": SCENARIO_A_WINDOW_HOURS,
        "rul_margin_days": 9.0,
        "production_impact": ProductionImpact.NONE,
        "crew_available": True,
        "planned_changeover": True,
        "status": ProposalStatus.PROPOSED,
    },
    "part_check": {
        "sku": "BRG-6220-C3",
        "quantity": 1,
        "in_stock": True,
        "location": "STORE-A",
        "lead_time_days": 0,
        "estimated_cost": 840,
        "currency": "INR",
        # Availability confirmed, nothing held: reservation waits for approval.
        "status": PartCheckStatus.CHECKED_NOT_RESERVED,
    },
}


SCENARIO_B: dict[str, Any] = {
    "scenario_type": ScenarioType.LOW_CONFIDENCE,
    "asset": {
        "asset_code": "MIX-02-AGITATOR",
        "name": "Slurry Mixer Agitator Gearbox",
        "plant_name": "Battery Plant",
        "line_name": "Mixing Line 1",
        "criticality": Criticality.CRITICAL,
        "status": AssetStatus.DEGRADED,
    },
    "incident": {
        "trace_id": "tr_5c07",
        "severity": Severity.ISO_20816_3_BAND_B,
        "workflow_status": WorkflowStatus.HUMAN_REVIEW,
        "cloud_available": True,
        "detected_at": NOW - timedelta(hours=3),
        "human_review_reason": (
            "Ambiguous signal pattern: gear-mesh and bearing hypotheses score "
            "within 0.06 of each other on insufficient evidence."
        ),
    },
    "anomaly": {
        "signal_name": "gearbox_broadband_velocity",
        "observed_value": 2.6,
        "baseline_value": 1.7,
        "unit": "mm/s",
        "sigma_deviation": 2.4,
        "thermal_delta_c": 3.1,
        "window_count": 2,
        "persisted": False,
    },
    "diagnosis": {
        "failure_mode_code": "GEAR_MESH_WEAR",
        "fmea_reference": "FM-2041",
        "confidence": 0.52,
        "confidence_band": ConfidenceBand.LOW,
        "recommended_action": RecommendedAction.SCHEDULE_INSPECTION,
        "recommended_action_note": (
            "Confidence is below the auto-approval threshold. A human should "
            "review the spectra before any intervention is proposed."
        ),
        "similar_work_order_reference": None,
        "rul_estimate_days": 41.0,
        "rul_ci_low_days": 9.0,
        "rul_ci_high_days": 120.0,
    },
    "evidence": [
        {
            "signal_name": "gearbox_broadband_velocity",
            "observed_value": 2.6,
            "baseline_value": 1.7,
            "unit": "mm/s",
            "evidence_type": EvidenceType.SENSOR_READING,
            "weight": 0.55,
            "source_reference": "vibration:mix-02-gbx",
        }
    ],
    # Two plausible modes, neither convincing — this is why it needs a human.
    "alternatives": [
        {
            "failure_mode_code": "BRG_CAGE_DEFECT",
            "rejection_reason": (
                "Not ruled out: cage frequency sidebands are present but below "
                "the detection threshold on a 2-window sample."
            ),
            "confidence": 0.46,
        },
        {
            "failure_mode_code": "LUBRICATION_DEGRADATION",
            "rejection_reason": (
                "Not ruled out: oil analysis is 40 days stale, so the hypothesis "
                "can be neither confirmed nor discarded."
            ),
            "confidence": 0.31,
        },
    ],
    # No proposal, no part check, no work order: nothing is planned for an
    # incident a human has not yet adjudicated.
    "proposal": None,
    "part_check": None,
}


SCENARIO_C: dict[str, Any] = {
    "scenario_type": ScenarioType.OFFLINE,
    "asset": {
        "asset_code": "COAT-01-DRYER",
        "name": "Electrode Coater Dryer Fan",
        "plant_name": "Battery Plant",
        "line_name": "Coating Line 3",
        "criticality": Criticality.HIGH,
        "status": AssetStatus.DEGRADED,
    },
    "incident": {
        "trace_id": "tr_1d88",
        "severity": Severity.ISO_20816_3_BAND_C,
        # Diagnosed at the edge; it cannot progress while the WAN link is down.
        "workflow_status": WorkflowStatus.DIAGNOSED,
        "cloud_available": False,
        "detected_at": NOW - timedelta(hours=9),
    },
    "anomaly": {
        "signal_name": "fan_1x_radial_velocity",
        "observed_value": 5.1,
        "baseline_value": 1.9,
        "unit": "mm/s",
        "sigma_deviation": 5.2,
        "thermal_delta_c": 6.4,
        "window_count": 5,
        "persisted": True,
    },
    "diagnosis": {
        "failure_mode_code": "ROTOR_IMBALANCE",
        "fmea_reference": "FM-3310",
        "confidence": 0.81,
        "confidence_band": ConfidenceBand.MEDIUM,
        "recommended_action": RecommendedAction.SCHEDULE_ALIGNMENT,
        "recommended_action_note": (
            "Edge diagnosis complete and retained locally. Planner, parts and "
            "approval steps are unavailable until the WAN link is restored."
        ),
        "similar_work_order_reference": "WO-39871",
        "rul_estimate_days": 24.0,
        "rul_ci_low_days": 15.0,
        "rul_ci_high_days": 38.0,
    },
    "evidence": [
        {
            "signal_name": "fan_1x_radial_velocity",
            "observed_value": 5.1,
            "baseline_value": 1.9,
            "unit": "mm/s",
            "evidence_type": EvidenceType.SPECTRAL_FEATURE,
            "weight": 0.60,
            "source_reference": "edge-spectrum:coat-01-fan",
        },
        {
            "signal_name": "phase_shift_across_bearings",
            "observed_value": 172.0,
            "baseline_value": 8.0,
            "unit": "deg",
            "evidence_type": EvidenceType.SPECTRAL_FEATURE,
            "weight": 0.40,
            "source_reference": "edge-phase:coat-01-fan",
        },
    ],
    "alternatives": [
        {
            "failure_mode_code": "BENT_SHAFT",
            "rejection_reason": "Rejected: axial 1x amplitude stays within baseline.",
            "confidence": 0.07,
        }
    ],
    "proposal": None,
    "part_check": None,
}

ALL_SCENARIOS = (SCENARIO_A, SCENARIO_B, SCENARIO_C)
