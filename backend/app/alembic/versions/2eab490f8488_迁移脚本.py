"""迁移脚本

Revision ID: 2eab490f8488
Revises: 1164d4a7539d
Create Date: 2026-09-15 10:23:23.083752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2eab490f8488'
down_revision: Union[str, None] = '1164d4a7539d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """仅新增边缘事件表 video_edge_events 及其索引（最小增量）。"""
    op.create_table('video_edge_events',
    sa.Column('event_id', sa.String(length=64), nullable=False, comment='Agent 事件 UUID'),
    sa.Column('edge_code', sa.String(length=64), nullable=True, comment='边缘设备码'),
    sa.Column('camera_id', sa.Integer(), nullable=True, comment='相机'),
    sa.Column('task_id', sa.Integer(), nullable=True, comment='布控任务'),
    sa.Column('algorithm_type', sa.String(length=64), nullable=True, comment='场景码'),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=True, comment='事件时间'),
    sa.Column('objects', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='v2 对象数组'),
    sa.Column('detections', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='兼容检测数组'),
    sa.Column('latency_ms', sa.Float(), nullable=True, comment='推理耗时(ms)'),
    sa.Column('snapshot_ref', sa.String(length=512), nullable=True, comment='快照引用'),
    sa.Column('matched', sa.Boolean(), nullable=False, comment='是否命中规则'),
    sa.Column('matched_rule_id', sa.Integer(), nullable=True, comment='命中规则'),
    sa.Column('matched_leaves', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='命中叶子解释'),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
    sa.Column('uuid', sa.String(length=64), nullable=False, comment='UUID全局唯一标识'),
    sa.Column('status', sa.String(length=10), nullable=False, comment='状态(0:正常 1:禁用)'),
    sa.Column('description', sa.Text(), nullable=True, comment='备注/描述'),
    sa.Column('created_time', sa.DateTime(), nullable=False, comment='创建时间'),
    sa.Column('updated_time', sa.DateTime(), nullable=False, comment='更新时间'),
    sa.Column('is_deleted', sa.Boolean(), nullable=False, comment='是否已删除(0:未删除 1:已删除)'),
    sa.Column('deleted_time', sa.DateTime(), nullable=True, comment='删除时间'),
    sa.PrimaryKeyConstraint('id'),
    comment='边缘事件表'
    )
    op.create_index('ix_edge_event_algo_id', 'video_edge_events', ['algorithm_type', 'id'], unique=False)
    op.create_index('ix_edge_event_camera_id_id', 'video_edge_events', ['camera_id', 'id'], unique=False)
    op.create_index('ix_edge_event_matched_id', 'video_edge_events', ['matched', 'id'], unique=False)
    op.create_index(op.f('ix_video_edge_events_created_time'), 'video_edge_events', ['created_time'], unique=False)
    op.create_index(op.f('ix_video_edge_events_deleted_time'), 'video_edge_events', ['deleted_time'], unique=False)
    op.create_index(op.f('ix_video_edge_events_event_id'), 'video_edge_events', ['event_id'], unique=True)
    op.create_index(op.f('ix_video_edge_events_id'), 'video_edge_events', ['id'], unique=False)
    op.create_index(op.f('ix_video_edge_events_is_deleted'), 'video_edge_events', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_video_edge_events_status'), 'video_edge_events', ['status'], unique=False)
    op.create_index(op.f('ix_video_edge_events_updated_time'), 'video_edge_events', ['updated_time'], unique=False)
    op.create_index(op.f('ix_video_edge_events_uuid'), 'video_edge_events', ['uuid'], unique=True)


def downgrade() -> None:
    """回滚：删除边缘事件表及其索引。"""
    op.drop_index(op.f('ix_video_edge_events_uuid'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_updated_time'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_status'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_is_deleted'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_id'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_event_id'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_deleted_time'), table_name='video_edge_events')
    op.drop_index(op.f('ix_video_edge_events_created_time'), table_name='video_edge_events')
    op.drop_index('ix_edge_event_matched_id', table_name='video_edge_events')
    op.drop_index('ix_edge_event_camera_id_id', table_name='video_edge_events')
    op.drop_index('ix_edge_event_algo_id', table_name='video_edge_events')
    op.drop_table('video_edge_events')
