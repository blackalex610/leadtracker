"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-24 12:48:16.227159
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_table('niche_presets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('label_bg', sa.String(length=120), nullable=True),
    sa.Column('category_query', sa.String(length=200), nullable=False),
    sa.Column('included_type', sa.String(length=100), nullable=True),
    sa.Column('keywords', sa.String(length=300), nullable=True),
    sa.Column('match_types', postgresql.ARRAY(sa.String(length=100)), server_default='{}', nullable=False),
    sa.Column('calling_window_start', sa.String(length=5), nullable=True),
    sa.Column('calling_window_end', sa.String(length=5), nullable=True),
    sa.Column('booking_oriented', sa.Boolean(), nullable=False),
    sa.Column('discovery_dependent', sa.Boolean(), nullable=False),
    sa.Column('strong_opportunities', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    sa.Column('is_builtin', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_niche_presets')),
    sa.UniqueConstraint('key', name=op.f('uq_niche_presets_key'))
    )
    op.create_table('provider_cache',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('operation', sa.String(length=40), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_provider_cache'))
    )
    op.create_index(op.f('ix_provider_cache_expires_at'), 'provider_cache', ['expires_at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_users_token_hash'))
    )
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_app_settings_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('businesses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('name_key', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=200), nullable=True),
    sa.Column('subcategory', sa.String(length=200), nullable=True),
    sa.Column('primary_type', sa.String(length=100), nullable=True),
    sa.Column('types', postgresql.ARRAY(sa.String(length=100)), server_default='{}', nullable=False),
    sa.Column('niche_key', sa.String(length=64), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('address', sa.String(length=500), nullable=True),
    sa.Column('address_key', sa.String(length=500), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('neighborhood', sa.String(length=120), nullable=True),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('latlng_fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('google_maps_url', sa.String(length=500), nullable=True),
    sa.Column('website_url', sa.String(length=1000), nullable=True),
    sa.Column('website_domain', sa.String(length=255), nullable=True),
    sa.Column('website_kind', sa.String(length=20), nullable=True),
    sa.Column('website_status', sa.String(length=20), nullable=False),
    sa.Column('website_health_score', sa.SmallInteger(), nullable=True),
    sa.Column('outdated_score', sa.SmallInteger(), nullable=True),
    sa.Column('last_audit_id', sa.Integer(), nullable=True),
    sa.Column('last_audited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phone_raw', sa.String(length=64), nullable=True),
    sa.Column('normalized_phone', sa.String(length=20), nullable=True),
    sa.Column('national_phone', sa.String(length=32), nullable=True),
    sa.Column('international_phone', sa.String(length=32), nullable=True),
    sa.Column('phone_country_code', sa.SmallInteger(), nullable=True),
    sa.Column('phone_type', sa.String(length=32), nullable=True),
    sa.Column('phone_source', sa.String(length=32), nullable=True),
    sa.Column('phone_verified', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('phone_invalid', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.Column('review_count', sa.Integer(), nullable=True),
    sa.Column('opening_hours', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('utc_offset_minutes', sa.Integer(), nullable=True),
    sa.Column('business_status', sa.String(length=40), nullable=True),
    sa.Column('photo_count', sa.SmallInteger(), nullable=True),
    sa.Column('google_profile_score', sa.SmallInteger(), nullable=True),
    sa.Column('google_signals', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('provider_place_id', sa.String(length=255), nullable=True),
    sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('data_quality', sa.String(length=10), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('opportunity_score', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('priority', sa.String(length=10), server_default='COLD', nullable=False),
    sa.Column('priority_rank', sa.SmallInteger(), server_default='2', nullable=False),
    sa.Column('priority_reason', sa.Text(), nullable=True),
    sa.Column('opportunity_types', postgresql.ARRAY(sa.String(length=40)), server_default='{}', nullable=False),
    sa.Column('score_reasons', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('booking_oriented', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('strong_category', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('open_in_calling_window', sa.Boolean(), nullable=True),
    sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='NEW', nullable=False),
    sa.Column('suppressed', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('assigned_to_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('last_contacted_by_id', sa.Integer(), nullable=True),
    sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_callback_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('call_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], name=op.f('fk_businesses_assigned_to_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_businesses_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['last_contacted_by_id'], ['users.id'], name=op.f('fk_businesses_last_contacted_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_businesses'))
    )
    op.create_index(op.f('ix_businesses_address_key'), 'businesses', ['address_key'], unique=False)
    op.create_index(op.f('ix_businesses_assigned_to_id'), 'businesses', ['assigned_to_id'], unique=False)
    op.create_index(op.f('ix_businesses_category'), 'businesses', ['category'], unique=False)
    op.create_index(op.f('ix_businesses_city'), 'businesses', ['city'], unique=False)
    op.create_index('ix_businesses_list_default', 'businesses', ['priority_rank', 'opportunity_score'], unique=False)
    op.create_index(op.f('ix_businesses_name_key'), 'businesses', ['name_key'], unique=False)
    op.create_index('ix_businesses_name_trgm', 'businesses', ['name'], unique=False, postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.create_index(op.f('ix_businesses_next_callback_at'), 'businesses', ['next_callback_at'], unique=False)
    op.create_index(op.f('ix_businesses_niche_key'), 'businesses', ['niche_key'], unique=False)
    op.create_index(op.f('ix_businesses_normalized_phone'), 'businesses', ['normalized_phone'], unique=False)
    op.create_index(op.f('ix_businesses_opportunity_score'), 'businesses', ['opportunity_score'], unique=False)
    op.create_index('ix_businesses_opportunity_types', 'businesses', ['opportunity_types'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_businesses_provider_place_id'), 'businesses', ['provider_place_id'], unique=False)
    op.create_index(op.f('ix_businesses_status'), 'businesses', ['status'], unique=False)
    op.create_index(op.f('ix_businesses_suppressed'), 'businesses', ['suppressed'], unique=False)
    op.create_index(op.f('ix_businesses_website_domain'), 'businesses', ['website_domain'], unique=False)
    op.create_table('calling_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('lead_ids', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_calling_sessions_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calling_sessions'))
    )
    op.create_table('import_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('columns', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_import_batches_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_batches'))
    )
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('stage', sa.String(length=40), nullable=True),
    sa.Column('progress_total', sa.Integer(), nullable=False),
    sa.Column('progress_processed', sa.Integer(), nullable=False),
    sa.Column('counters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('attempts', sa.SmallInteger(), nullable=False),
    sa.Column('max_attempts', sa.SmallInteger(), nullable=False),
    sa.Column('locked_by', sa.String(length=100), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('retry_of_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_jobs_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['retry_of_id'], ['jobs.id'], name=op.f('fk_jobs_retry_of_id_jobs'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs'))
    )
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_kind'), 'jobs', ['kind'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_table('api_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('operation', sa.String(length=40), nullable=False),
    sa.Column('sku', sa.String(length=60), nullable=True),
    sa.Column('units', sa.Integer(), nullable=False),
    sa.Column('cached', sa.Boolean(), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('status_code', sa.SmallInteger(), nullable=True),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_api_usage_job_id_jobs'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_usage'))
    )
    op.create_index(op.f('ix_api_usage_created_at'), 'api_usage', ['created_at'], unique=False)
    op.create_table('business_contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('raw_phone', sa.String(length=64), nullable=False),
    sa.Column('normalized_phone', sa.String(length=20), nullable=False),
    sa.Column('national_format', sa.String(length=32), nullable=True),
    sa.Column('international_format', sa.String(length=32), nullable=True),
    sa.Column('country_code', sa.SmallInteger(), nullable=True),
    sa.Column('phone_type', sa.String(length=32), nullable=True),
    sa.Column('phone_source', sa.String(length=32), nullable=False),
    sa.Column('phone_verified', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification_method', sa.String(length=40), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('invalid', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_business_contacts_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_business_contacts')),
    sa.UniqueConstraint('business_id', 'normalized_phone', name='uq_business_contacts_business_phone')
    )
    op.create_index(op.f('ix_business_contacts_business_id'), 'business_contacts', ['business_id'], unique=False)
    op.create_index(op.f('ix_business_contacts_normalized_phone'), 'business_contacts', ['normalized_phone'], unique=False)
    op.create_table('business_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('match_reason', sa.String(length=40), nullable=True),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_business_sources_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_business_sources')),
    sa.UniqueConstraint('provider', 'external_id', name='uq_business_sources_provider_external')
    )
    op.create_index(op.f('ix_business_sources_business_id'), 'business_sources', ['business_id'], unique=False)
    op.create_table('call_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('outcome', sa.String(length=30), nullable=False),
    sa.Column('phone_dialed', sa.String(length=20), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('callback_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_call_attempts_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['calling_sessions.id'], name=op.f('fk_call_attempts_session_id_calling_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_call_attempts_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_call_attempts'))
    )
    op.create_index(op.f('ix_call_attempts_business_id'), 'call_attempts', ['business_id'], unique=False)
    op.create_index(op.f('ix_call_attempts_created_at'), 'call_attempts', ['created_at'], unique=False)
    op.create_table('job_businesses',
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('is_new', sa.Boolean(), nullable=False),
    sa.Column('matched_filters', sa.Boolean(), nullable=False),
    sa.Column('query', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_job_businesses_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_job_businesses_job_id_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id', 'business_id', name=op.f('pk_job_businesses'))
    )
    op.create_table('lead_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_lead_events_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_lead_events_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lead_events'))
    )
    op.create_index(op.f('ix_lead_events_business_id'), 'lead_events', ['business_id'], unique=False)
    op.create_table('notes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_notes_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notes_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notes'))
    )
    op.create_index(op.f('ix_notes_business_id'), 'notes', ['business_id'], unique=False)
    op.create_table('search_queries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('text_query', sa.String(length=500), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pages_fetched', sa.SmallInteger(), nullable=False),
    sa.Column('results_count', sa.Integer(), nullable=False),
    sa.Column('cached', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_search_queries_job_id_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_search_queries'))
    )
    op.create_index(op.f('ix_search_queries_job_id'), 'search_queries', ['job_id'], unique=False)
    op.create_table('suppression_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('normalized_phone', sa.String(length=20), nullable=True),
    sa.Column('business_id', sa.Integer(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deactivated_by_id', sa.Integer(), nullable=True),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_suppression_list_business_id_businesses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_suppression_list_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deactivated_by_id'], ['users.id'], name=op.f('fk_suppression_list_deactivated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suppression_list'))
    )
    op.create_index(op.f('ix_suppression_list_normalized_phone'), 'suppression_list', ['normalized_phone'], unique=False)
    op.create_index('uq_suppression_active_phone', 'suppression_list', ['normalized_phone'], unique=True, postgresql_where=sa.text('active AND normalized_phone IS NOT NULL'))
    op.create_table('website_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('url', sa.String(length=1000), nullable=False),
    sa.Column('final_url', sa.String(length=1000), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('http_status', sa.SmallInteger(), nullable=True),
    sa.Column('https', sa.Boolean(), nullable=True),
    sa.Column('redirect_count', sa.SmallInteger(), nullable=False),
    sa.Column('redirect_chain', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('health_score', sa.SmallInteger(), nullable=True),
    sa.Column('outdated_score', sa.SmallInteger(), nullable=True),
    sa.Column('outdated_band', sa.String(length=40), nullable=True),
    sa.Column('category_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outdated_signals', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('analyzer_version', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_website_audits_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_website_audits_job_id_jobs'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_website_audits'))
    )
    op.create_index(op.f('ix_website_audits_business_id'), 'website_audits', ['business_id'], unique=False)
    op.create_foreign_key(op.f('fk_businesses_last_audit_id_website_audits'), 'businesses', 'website_audits', ['last_audit_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_job_businesses_business_id', 'job_businesses', ['business_id'], unique=False)
    op.create_index('ix_call_attempts_session_id', 'call_attempts', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_constraint(op.f('fk_businesses_last_audit_id_website_audits'), 'businesses', type_='foreignkey')
    op.drop_index('ix_call_attempts_session_id', table_name='call_attempts')
    op.drop_index('ix_job_businesses_business_id', table_name='job_businesses')
    op.drop_index(op.f('ix_website_audits_business_id'), table_name='website_audits')
    op.drop_table('website_audits')
    op.drop_index('uq_suppression_active_phone', table_name='suppression_list', postgresql_where=sa.text('active AND normalized_phone IS NOT NULL'))
    op.drop_index(op.f('ix_suppression_list_normalized_phone'), table_name='suppression_list')
    op.drop_table('suppression_list')
    op.drop_index(op.f('ix_search_queries_job_id'), table_name='search_queries')
    op.drop_table('search_queries')
    op.drop_index(op.f('ix_notes_business_id'), table_name='notes')
    op.drop_table('notes')
    op.drop_index(op.f('ix_lead_events_business_id'), table_name='lead_events')
    op.drop_table('lead_events')
    op.drop_table('job_businesses')
    op.drop_index(op.f('ix_call_attempts_created_at'), table_name='call_attempts')
    op.drop_index(op.f('ix_call_attempts_business_id'), table_name='call_attempts')
    op.drop_table('call_attempts')
    op.drop_index(op.f('ix_business_sources_business_id'), table_name='business_sources')
    op.drop_table('business_sources')
    op.drop_index(op.f('ix_business_contacts_normalized_phone'), table_name='business_contacts')
    op.drop_index(op.f('ix_business_contacts_business_id'), table_name='business_contacts')
    op.drop_table('business_contacts')
    op.drop_index(op.f('ix_api_usage_created_at'), table_name='api_usage')
    op.drop_table('api_usage')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_kind'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_created_at'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_table('import_batches')
    op.drop_table('calling_sessions')
    op.drop_index(op.f('ix_businesses_website_domain'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_suppressed'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_status'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_provider_place_id'), table_name='businesses')
    op.drop_index('ix_businesses_opportunity_types', table_name='businesses', postgresql_using='gin')
    op.drop_index(op.f('ix_businesses_opportunity_score'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_normalized_phone'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_niche_key'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_next_callback_at'), table_name='businesses')
    op.drop_index('ix_businesses_name_trgm', table_name='businesses', postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.drop_index(op.f('ix_businesses_name_key'), table_name='businesses')
    op.drop_index('ix_businesses_list_default', table_name='businesses')
    op.drop_index(op.f('ix_businesses_city'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_category'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_assigned_to_id'), table_name='businesses')
    op.drop_index(op.f('ix_businesses_address_key'), table_name='businesses')
    op.drop_table('businesses')
    op.drop_table('app_settings')
    op.drop_table('users')
    op.drop_index(op.f('ix_provider_cache_expires_at'), table_name='provider_cache')
    op.drop_table('provider_cache')
    op.drop_table('niche_presets')
