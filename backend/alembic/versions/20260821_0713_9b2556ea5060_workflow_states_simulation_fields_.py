"""workflow states, simulation fields, diagnosis alternatives

Revision ID: 9b2556ea5060
Revises: 1a073f496248
Create Date: 2026-08-21 07:13:35.794964+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9b2556ea5060"
down_revision: str | None = "1a073f496248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Enum surgery.
#
# Alembic autogenerate compares *columns*, not enum labels, so the value
# changes below are hand-written. PostgreSQL cannot rewrite an enum's labels in
# place, so each swap renames the old type, creates the new one, recasts the
# column through an explicit mapping, and drops the old type.
# ---------------------------------------------------------------------------

WORKFLOW_STATUS_VALUES = (
    "watch",
    "escalated",
    "diagnosed",
    "human_review",
    "approval_required",
    "approved",
    "rejected",
    "work_order_live",
    "resolved",
)

# Old workflow label -> its closest equivalent in the new state machine.
WORKFLOW_STATUS_FORWARD = {
    "detected": "watch",
    "diagnosing": "escalated",
    "diagnosed": "diagnosed",
    "proposed": "approval_required",
    "awaiting_approval": "approval_required",
    "approved": "approved",
    "rejected": "rejected",
    "scheduled": "approved",
    "in_progress": "work_order_live",
    "resolved": "resolved",
    "cancelled": "watch",
}

WORKFLOW_STATUS_OLD_VALUES = tuple(WORKFLOW_STATUS_FORWARD)

WORKFLOW_STATUS_BACKWARD = {
    "watch": "detected",
    "escalated": "diagnosing",
    "diagnosed": "diagnosed",
    "human_review": "diagnosed",
    "approval_required": "awaiting_approval",
    "approved": "approved",
    "rejected": "rejected",
    "work_order_live": "in_progress",
    "resolved": "resolved",
}

SEVERITY_VALUES = (
    "iso_20816_3_band_a",
    "iso_20816_3_band_b",
    "iso_20816_3_band_c",
    "iso_20816_3_band_d",
)

SEVERITY_OLD_VALUES = ("info", "warning", "major", "critical")

SEVERITY_FORWARD = {
    "info": "iso_20816_3_band_a",
    "warning": "iso_20816_3_band_b",
    "major": "iso_20816_3_band_c",
    "critical": "iso_20816_3_band_d",
}

SEVERITY_BACKWARD = {new: old for old, new in SEVERITY_FORWARD.items()}


def _swap_enum(
    *,
    type_name: str,
    new_values: tuple[str, ...],
    table: str,
    column: str,
    mapping: dict[str, str],
) -> None:
    """Replace an enum type's labels, recasting `table.column` through `mapping`."""
    labels = ", ".join(f"'{value}'" for value in new_values)
    cases = "\n        ".join(f"WHEN '{old}' THEN '{new}'" for old, new in mapping.items())
    op.execute(f"ALTER TYPE {type_name} RENAME TO {type_name}_old")
    op.execute(f"CREATE TYPE {type_name} AS ENUM ({labels})")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} USING ("
        f"CASE {column}::text\n        {cases}\n        END"
        f")::{type_name}"
    )
    op.execute(f"DROP TYPE {type_name}_old")


def upgrade() -> None:
    # Rebuild the workflow and severity enums before anything references them.
    _swap_enum(
        type_name="workflow_status",
        new_values=WORKFLOW_STATUS_VALUES,
        table="incidents",
        column="workflow_status",
        mapping=WORKFLOW_STATUS_FORWARD,
    )
    _swap_enum(
        type_name="severity",
        new_values=SEVERITY_VALUES,
        table="incidents",
        column="severity",
        mapping=SEVERITY_FORWARD,
    )
    # Purely additive labels — no recast needed.
    op.execute("ALTER TYPE proposal_status ADD VALUE IF NOT EXISTS 'proposed' AFTER 'draft'")
    op.execute(
        "ALTER TYPE part_check_status ADD VALUE IF NOT EXISTS 'checked_not_reserved' "
        "BEFORE 'reserved'"
    )

    # `recommended_action` becomes a native enum. Any free text written before
    # this migration cannot be cast, so it falls back to the safest action.
    recommended_action = sa.Enum(
        "monitor",
        "schedule_inspection",
        "schedule_alignment",
        "schedule_replacement",
        "immediate_stop",
        name="recommended_action",
    )
    recommended_action.create(op.get_bind(), checkfirst=True)
    op.execute(
        "UPDATE diagnoses SET recommended_action = 'monitor' "
        "WHERE recommended_action NOT IN "
        "('monitor', 'schedule_inspection', 'schedule_alignment', "
        "'schedule_replacement', 'immediate_stop')"
    )

    # Create the remaining new enum types up front so add_column cannot race them.
    for enum_type in (
        sa.Enum("sentinel", "diagnosis", "planner", "parts", name="agent_kind"),
        sa.Enum("low", "medium", "high", name="confidence_band"),
        sa.Enum("normal", "low_confidence", "offline", name="scenario_type"),
    ):
        enum_type.create(op.get_bind(), checkfirst=True)

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "sentinel_anomalies",
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("signal_name", sa.String(length=128), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("sigma_deviation", sa.Float(), nullable=True),
        sa.Column("thermal_delta_c", sa.Float(), nullable=True),
        sa.Column("window_count", sa.Integer(), nullable=False),
        sa.Column("persisted", sa.Boolean(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_sentinel_anomalies_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sentinel_anomalies")),
    )
    op.create_index(
        "ix_sentinel_anomalies_detected_at", "sentinel_anomalies", ["detected_at"], unique=False
    )
    op.create_index(
        "ix_sentinel_anomalies_incident_id", "sentinel_anomalies", ["incident_id"], unique=False
    )
    op.create_table(
        "diagnosis_alternatives",
        sa.Column("diagnosis_id", sa.UUID(), nullable=False),
        sa.Column("failure_mode_code", sa.String(length=64), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_diagnosis_alternatives_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["diagnosis_id"],
            ["diagnoses.id"],
            name=op.f("fk_diagnosis_alternatives_diagnosis_id_diagnoses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_alternatives")),
    )
    op.create_index(
        "ix_diagnosis_alternatives_diagnosis_id",
        "diagnosis_alternatives",
        ["diagnosis_id"],
        unique=False,
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "agent_kind",
            sa.Enum("sentinel", "diagnosis", "planner", "parts", name="agent_kind"),
            nullable=True,
        ),
    )
    op.create_index("ix_agent_runs_agent_kind", "agent_runs", ["agent_kind"], unique=False)
    op.add_column("approval_decisions", sa.Column("token_id", sa.UUID(), nullable=True))
    op.alter_column("approval_decisions", "approval_token_hash", new_column_name="token_hash")
    op.add_column(
        "approval_decisions", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_approval_decisions_token_id", "approval_decisions", ["token_id"], unique=False
    )
    op.add_column(
        "diagnoses",
        sa.Column(
            "confidence_band",
            sa.Enum("low", "medium", "high", name="confidence_band"),
            server_default="medium",
            nullable=False,
        ),
    )
    op.add_column("diagnoses", sa.Column("recommended_action_note", sa.Text(), nullable=True))
    op.add_column(
        "diagnoses", sa.Column("similar_work_order_reference", sa.String(length=128), nullable=True)
    )
    op.alter_column(
        "diagnoses",
        "recommended_action",
        existing_type=sa.TEXT(),
        server_default="monitor",
        type_=sa.Enum(
            "monitor",
            "schedule_inspection",
            "schedule_alignment",
            "schedule_replacement",
            "immediate_stop",
            name="recommended_action",
        ),
        existing_nullable=False,
        postgresql_using="recommended_action::recommended_action",
    )
    op.create_index("ix_diagnoses_confidence_band", "diagnoses", ["confidence_band"], unique=False)
    op.add_column(
        "incidents",
        sa.Column(
            "scenario_type",
            sa.Enum("normal", "low_confidence", "offline", name="scenario_type"),
            server_default="normal",
            nullable=False,
        ),
    )
    op.add_column(
        "incidents",
        sa.Column("cloud_available", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column("incidents", sa.Column("human_review_reason", sa.Text(), nullable=True))
    op.create_index("ix_incidents_scenario_type", "incidents", ["scenario_type"], unique=False)
    op.add_column(
        "maintenance_proposals",
        sa.Column("proposed_end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "maintenance_proposals",
        sa.Column("planned_changeover", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "part_checks", sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "technician_outcomes", sa.Column("technician_id", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "technician_outcomes", sa.Column("technician_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "work_orders", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("work_orders", "completed_at")
    op.drop_column("technician_outcomes", "technician_name")
    op.drop_column("technician_outcomes", "technician_id")
    op.drop_column("part_checks", "reserved_at")
    op.drop_column("maintenance_proposals", "planned_changeover")
    op.drop_column("maintenance_proposals", "proposed_end_at")
    op.drop_index("ix_incidents_scenario_type", table_name="incidents")
    op.drop_column("incidents", "human_review_reason")
    op.drop_column("incidents", "cloud_available")
    op.drop_column("incidents", "scenario_type")
    op.drop_index("ix_diagnoses_confidence_band", table_name="diagnoses")
    op.alter_column(
        "diagnoses",
        "recommended_action",
        existing_type=sa.Enum(
            "monitor",
            "schedule_inspection",
            "schedule_alignment",
            "schedule_replacement",
            "immediate_stop",
            name="recommended_action",
        ),
        server_default=None,
        type_=sa.TEXT(),
        existing_nullable=False,
        postgresql_using="recommended_action::text",
    )
    op.drop_column("diagnoses", "similar_work_order_reference")
    op.drop_column("diagnoses", "recommended_action_note")
    op.drop_column("diagnoses", "confidence_band")
    op.drop_index("ix_approval_decisions_token_id", table_name="approval_decisions")
    op.drop_column("approval_decisions", "used_at")
    op.alter_column("approval_decisions", "token_hash", new_column_name="approval_token_hash")
    op.drop_column("approval_decisions", "token_id")
    op.drop_index("ix_agent_runs_agent_kind", table_name="agent_runs")
    op.drop_column("agent_runs", "agent_kind")
    op.drop_index("ix_diagnosis_alternatives_diagnosis_id", table_name="diagnosis_alternatives")
    op.drop_table("diagnosis_alternatives")
    op.drop_index("ix_sentinel_anomalies_incident_id", table_name="sentinel_anomalies")
    op.drop_index("ix_sentinel_anomalies_detected_at", table_name="sentinel_anomalies")
    op.drop_table("sentinel_anomalies")
    # ### end Alembic commands ###

    # Drop the enum types the added columns owned, then restore the two types
    # whose labels this migration rewrote.
    for type_name in ("recommended_action", "scenario_type", "confidence_band", "agent_kind"):
        op.execute(f"DROP TYPE IF EXISTS {type_name}")

    _swap_enum(
        type_name="workflow_status",
        new_values=WORKFLOW_STATUS_OLD_VALUES,
        table="incidents",
        column="workflow_status",
        mapping=WORKFLOW_STATUS_BACKWARD,
    )
    _swap_enum(
        type_name="severity",
        new_values=SEVERITY_OLD_VALUES,
        table="incidents",
        column="severity",
        mapping=SEVERITY_BACKWARD,
    )
    # `proposal_status` and `part_check_status` keep their extra labels:
    # PostgreSQL cannot remove an enum label, and leaving them is harmless.
