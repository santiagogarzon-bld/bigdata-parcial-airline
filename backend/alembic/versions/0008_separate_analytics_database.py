"""Remove the transitional warehouse from the OLTP database."""

from alembic import op

revision = "0008_separate_analytics_database"
down_revision = "0007_analytics_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")


def downgrade() -> None:
    # Replaying 0006/0007 is deliberately required to restore the old design.
    pass
