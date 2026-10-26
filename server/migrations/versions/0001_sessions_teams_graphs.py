"""sessions teams graphs

Revision ID: 0001
Revises:
Create Date: 2026-10-26 17:55:49.698153
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('sessions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('code', sa.String(length=6), nullable=False),
    sa.Column('facilitator_token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('code', name=op.f('uq_sessions_code'))
    )
    op.create_table('teams',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.Column('name_key', sa.String(length=30), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_teams_session_id_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teams')),
    sa.UniqueConstraint('session_id', 'name_key', name='uq_teams_session_id_name_key'),
    sa.UniqueConstraint('token_hash', name=op.f('uq_teams_token_hash'))
    )
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_teams_session_id'), ['session_id'], unique=False)

    op.create_table('graphs',
    sa.Column('team_id', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('locked', sa.Boolean(), nullable=False),
    sa.Column('graph', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_graphs_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('team_id', name=op.f('pk_graphs'))
    )


def downgrade() -> None:
    op.drop_table('graphs')
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_teams_session_id'))

    op.drop_table('teams')
    op.drop_table('sessions')
