"""create persisted test reports

Revision ID: 9c7d2a1b4e60
Revises: 825a4e213bb7
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c7d2a1b4e60"
down_revision: Union[str, Sequence[str], None] = "825a4e213bb7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_records",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("overall_status", sa.String(length=32), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_report_records_id", "report_records", ["id"])
    op.create_index("ix_report_records_url", "report_records", ["url"])
    op.create_index("ix_report_records_created_at", "report_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_report_records_created_at", table_name="report_records")
    op.drop_index("ix_report_records_url", table_name="report_records")
    op.drop_index("ix_report_records_id", table_name="report_records")
    op.drop_table("report_records")
