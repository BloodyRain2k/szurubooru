'''
Adding pg_trgm extension and index to post.source

Revision ID: 0b0966219d9b
Created at: 2024-06-29 20:46:37.070640
'''

import sqlalchemy as sa
from alembic import op

revision = '0b0966219d9b'
down_revision = '236a5500cd0c'
branch_labels = None
depends_on = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE INDEX idx_post_source_gin ON post USING gin (source gin_trgm_ops)')

def downgrade():
    op.execute('DROP INDEX idx_post_source_gin')
    op.execute('DROP EXTENSION pg_trgm')
