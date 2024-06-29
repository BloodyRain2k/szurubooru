'''
Add 'directory' and 'filename' columns to posts

Revision ID: 236a5500cd0c
Created at: 2024-06-28 17:40:08.371419
'''

import sqlalchemy as sa
from alembic import op

revision = '236a5500cd0c'
down_revision = '99de351fb1d0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "post", sa.Column("directory", sa.Unicode(8), nullable=True)
    )


def downgrade():
    op.drop_column("post", "directory")
