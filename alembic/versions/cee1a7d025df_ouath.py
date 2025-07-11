"""ouath

Revision ID: cee1a7d025df
Revises: 72f0a5f81279
Create Date: 2025-06-25 10:30:33.724211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cee1a7d025df'
down_revision: Union[str, None] = '72f0a5f81279'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_oauth_user', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_oauth_user')

    # ### end Alembic commands ###
