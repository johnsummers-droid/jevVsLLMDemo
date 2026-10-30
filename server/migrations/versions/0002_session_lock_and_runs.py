"""session lock and runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locked', sa.Boolean(), server_default=sa.false(), nullable=False))

    op.create_table('runs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('team_id', sa.String(length=32), nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('graph', sa.JSON(), nullable=False),
    sa.Column('graph_version', sa.Integer(), nullable=False),
    sa.Column('metrics', sa.JSON(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_runs_session_id_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_runs_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs'))
    )
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_runs_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_runs_team_id'), ['team_id'], unique=False)

    # Sessions already in pencils down (every graph locked) stay locked for teams joining later.
    op.execute(
        "UPDATE sessions SET locked = true WHERE EXISTS (SELECT 1 FROM teams WHERE teams.session_id = sessions.id)"
        " AND NOT EXISTS (SELECT 1 FROM teams JOIN graphs ON graphs.team_id = teams.id"
        " WHERE teams.session_id = sessions.id AND graphs.locked = false)"
    )


def downgrade() -> None:
    with op.batch_alter_table('runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_runs_team_id'))
        batch_op.drop_index(batch_op.f('ix_runs_session_id'))

    op.drop_table('runs')
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_column('locked')
