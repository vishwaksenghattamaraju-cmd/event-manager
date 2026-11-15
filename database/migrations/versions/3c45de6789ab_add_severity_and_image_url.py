"""add_severity_and_image_url

Revision ID: 3c45de6789ab
Revises: 2b34bb251fd2
Create Date: 2026-11-15 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c45de6789ab'
down_revision: Union[str, Sequence[str], None] = '2b34bb251fd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include severity in alerts and image_url in events."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Add severity to alerts if not present
    alerts_columns = [c['name'] for c in inspector.get_columns('alerts')]
    if 'severity' not in alerts_columns:
        op.add_column('alerts', sa.Column('severity', sa.String(length=20), nullable=False, server_default='WARNING'))

    # Add image_url to events if not present
    events_columns = [c['name'] for c in inspector.get_columns('events')]
    if 'image_url' not in events_columns:
        op.add_column('events', sa.Column('image_url', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    events_columns = [c['name'] for c in inspector.get_columns('events')]
    if 'image_url' in events_columns:
        op.drop_column('events', 'image_url')

    alerts_columns = [c['name'] for c in inspector.get_columns('alerts')]
    if 'severity' in alerts_columns:
        op.drop_column('alerts', 'severity')
