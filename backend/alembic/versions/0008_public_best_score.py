"""Public profiles show each skill's best verified score (audit fix, D56).

Bidding (the newcomer rule, Algorithm 1) uses a developer's best score per skill
(`repositories/bids.best_evidence_by_developer`), but `public_developer_profile` showed the
latest one, so a client could see a failing score on someone the filter passed. The function now
picks the best score per skill (the latest of equal scores); nothing else changes.

Revision ID: 0008_public_best_score
Revises: 0007_bidding_terms
Create Date: 2026-10-24 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_public_best_score"
down_revision: str | None = "0007_bidding_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEST = """
CREATE OR REPLACE FUNCTION public_developer_profile(p_user uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT CASE WHEN NOT profile_visible(p_user) THEN NULL ELSE jsonb_build_object(
    'id', u.id,
    'display_name', u.display_name,
    'member_since', u.created_at,
    'headline', coalesce(dp.headline, ''),
    'bio', coalesce(dp.bio, ''),
    'hours_per_week', coalesce(dp.hours_per_week, 20),
    'github_username', dp.github_username,
    'visibility', coalesce(dp.visibility, 'PUBLIC'),
    'skills', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', s.id, 'name', s.name, 'domain', s.domain,
                                          'self_level', ds.self_level) ORDER BY s.name)
      FROM developer_skills ds JOIN skills s ON s.id = ds.skill_id WHERE ds.user_id = u.id), '[]'),
    'verified_scores', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', e.skill_id, 'name', s.name, 'score', e.score::text,
                                          'at', e.at) ORDER BY s.name)
      FROM (SELECT DISTINCT ON (skill_id) skill_id, score, at FROM skill_evidence
            WHERE user_id = u.id ORDER BY skill_id, score DESC, at DESC) e
      JOIN skills s ON s.id = e.skill_id), '[]'),
    'portfolio', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'id', p.id, 'title', p.title, 'description', p.description, 'url', p.url,
        'skill_ids', p.skill_ids,
        'image_ids', coalesce((SELECT jsonb_agg(pi.file_id ORDER BY pi.position)
                               FROM portfolio_images pi WHERE pi.portfolio_item_id = p.id), '[]'))
        ORDER BY p.position)
      FROM portfolio_items p WHERE p.user_id = u.id), '[]'),
    'certificates', coalesce((
      SELECT jsonb_agg(jsonb_build_object('title', c.title, 'issuer', c.issuer) ORDER BY c.title)
      FROM certificates c WHERE c.user_id = u.id AND c.status = 'VERIFIED'), '[]')
  ) END
  FROM users u LEFT JOIN developer_profiles dp ON dp.user_id = u.id
  WHERE u.id = p_user
$$;
"""

LATEST = """
CREATE OR REPLACE FUNCTION public_developer_profile(p_user uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT CASE WHEN NOT profile_visible(p_user) THEN NULL ELSE jsonb_build_object(
    'id', u.id,
    'display_name', u.display_name,
    'member_since', u.created_at,
    'headline', coalesce(dp.headline, ''),
    'bio', coalesce(dp.bio, ''),
    'hours_per_week', coalesce(dp.hours_per_week, 20),
    'github_username', dp.github_username,
    'visibility', coalesce(dp.visibility, 'PUBLIC'),
    'skills', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', s.id, 'name', s.name, 'domain', s.domain,
                                          'self_level', ds.self_level) ORDER BY s.name)
      FROM developer_skills ds JOIN skills s ON s.id = ds.skill_id WHERE ds.user_id = u.id), '[]'),
    'verified_scores', coalesce((
      SELECT jsonb_agg(jsonb_build_object('skill_id', e.skill_id, 'name', s.name, 'score', e.score::text,
                                          'at', e.at) ORDER BY s.name)
      FROM (SELECT DISTINCT ON (skill_id) skill_id, score, at FROM skill_evidence
            WHERE user_id = u.id ORDER BY skill_id, at DESC) e
      JOIN skills s ON s.id = e.skill_id), '[]'),
    'portfolio', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'id', p.id, 'title', p.title, 'description', p.description, 'url', p.url,
        'skill_ids', p.skill_ids,
        'image_ids', coalesce((SELECT jsonb_agg(pi.file_id ORDER BY pi.position)
                               FROM portfolio_images pi WHERE pi.portfolio_item_id = p.id), '[]'))
        ORDER BY p.position)
      FROM portfolio_items p WHERE p.user_id = u.id), '[]'),
    'certificates', coalesce((
      SELECT jsonb_agg(jsonb_build_object('title', c.title, 'issuer', c.issuer) ORDER BY c.title)
      FROM certificates c WHERE c.user_id = u.id AND c.status = 'VERIFIED'), '[]')
  ) END
  FROM users u LEFT JOIN developer_profiles dp ON dp.user_id = u.id
  WHERE u.id = p_user
$$;
"""


def upgrade() -> None:
    op.execute(BEST)


def downgrade() -> None:
    op.execute(LATEST)
