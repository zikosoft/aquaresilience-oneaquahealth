"""situation brief city_id

Revision ID: 333e03fa6e6a
Revises: 11b7fc6c3a61
Create Date: 2026-10-03 19:52:25.534309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '333e03fa6e6a'
down_revision: Union[str, None] = '11b7fc6c3a61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("situation_briefs", sa.Column("city_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_situation_briefs_city_id"), "situation_briefs", ["city_id"])
    op.create_foreign_key(
        "fk_situation_briefs_city_id_cities",
        "situation_briefs",
        "cities",
        ["city_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_situation_briefs_city_id_cities", "situation_briefs", type_="foreignkey")
    op.drop_index(op.f("ix_situation_briefs_city_id"), table_name="situation_briefs")
    op.drop_column("situation_briefs", "city_id")
