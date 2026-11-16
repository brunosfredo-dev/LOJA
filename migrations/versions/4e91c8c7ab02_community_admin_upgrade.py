"""Profile names, threaded replies, user reports and administration audit.

Revision ID: 4e91c8c7ab02
Revises: 23e9bb948e0c
"""
from alembic import op
import sqlalchemy as sa

revision = '4e91c8c7ab02'
down_revision = '23e9bb948e0c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('display_name', sa.String(60), nullable=False, server_default=''))
    with op.batch_alter_table('comments') as batch:
        batch.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_foreign_key('fk_comments_parent_id', 'comments', ['parent_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_comments_parent_id', ['parent_id'])
    with op.batch_alter_table('reports') as batch:
        batch.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_reports_user_id', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_reports_user_id', ['user_id'])
    op.create_table('admin_audit',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('admin_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL'),nullable=True),
        sa.Column('action',sa.String(60),nullable=False),
        sa.Column('target_type',sa.String(30),nullable=False),
        sa.Column('target_id',sa.Integer(),nullable=False),
        sa.Column('details',sa.String(500),nullable=False,server_default=''),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index('ix_admin_audit_admin_id','admin_audit',['admin_id'])
    op.create_index('ix_admin_audit_created_at','admin_audit',['created_at'])


def downgrade():
    op.drop_index('ix_admin_audit_created_at',table_name='admin_audit')
    op.drop_index('ix_admin_audit_admin_id',table_name='admin_audit')
    op.drop_table('admin_audit')
    with op.batch_alter_table('reports') as batch:
        batch.drop_index('ix_reports_user_id')
        batch.drop_constraint('fk_reports_user_id',type_='foreignkey')
        batch.drop_column('user_id')
    with op.batch_alter_table('comments') as batch:
        batch.drop_index('ix_comments_parent_id')
        batch.drop_constraint('fk_comments_parent_id',type_='foreignkey')
        batch.drop_column('parent_id')
        batch.drop_column('is_hidden')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('display_name')
