"""provider calls

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('provider_calls',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('response', sa.JSON(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('tokens_in', sa.Integer(), nullable=False),
    sa.Column('tokens_out', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_provider_calls'))
    )
    with op.batch_alter_table('provider_calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_provider_calls_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('provider_calls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_provider_calls_created_at'))

    op.drop_table('provider_calls')
