"""Account link: speakers.user_id.

Adds an optional column tying a speaker profile to a Supabase Auth account, so
a signed-in contributor's recordings can be listed back to them. Existing
speaker rows (recorded before accounts existed, or recorded signed out) simply
have user_id = NULL.


Revision ID: 0003_account_link
Revises: 0002_review_pass
Create Date: 2026-09-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_account_link"
down_revision = "0002_review_pass"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("speakers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_speakers_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("speakers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_speakers_user_id"))
        batch_op.drop_column("user_id")
