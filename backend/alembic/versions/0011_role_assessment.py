"""Role assessment for newcomers (ROLE_ASSESSMENT_BUILD_SPEC.md §4, §10).

- `competencies` (per skill, keywords for requirement matching) and the extended
  `question_bank` (competency tag, DRAFT/APPROVED/RETIRED status, source, code snippet,
  explanation, review level and record, exposure count, version). Content of an approved
  question is immutable (trigger); a correction retires it and inserts a new version.
- `assessment_blueprints` (immutable, unique by fingerprint) and `slot_assessments` (the blueprint
  of each slot, fixed by the publish transaction), `user_accommodations` (admin extra time).
- `test_attempts` serves practice tests and role assessments (`kind`); role attempts carry the
  one-way position, the locked answers, the window token hash, the focus record and the result.
- `skill_evidence` gains `ROLE_ASSESSMENT` rows (passed, valid until, voided); `bids` links the
  evidence a newcomer's bid relies on.
- SECURITY DEFINER functions start, serve, answer, finish and score role attempts; questions
  leave the database one at a time and never with their answers. The practice-test functions
  now refuse role attempts, and at most one attempt of either kind is open per developer.
- Seed: the competency catalogue and the question bank v2 (`question_bank_v2.json`, built from
  `scripts/seed_data/question_bank/*.yaml`); the 128 original questions are found by text and
  tagged. Settings v5 adds the `assessment` group and the assessment rate limits.

Revision ID: 0011_role_assessment
Revises: 0010_versions_and_job_runs
Create Date: 2026-10-28 00:00:00.000000+00:00
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_role_assessment"
down_revision: str | None = "0010_versions_and_job_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
BANK = SEED_DIR / "question_bank_v2.json"
SETTINGS_V5 = SEED_DIR / "platform_settings_v5.json"
DML_ROLES = "devsync_app, devsync_worker"
NEW_ENUMS = {
    "question_status": ("DRAFT", "APPROVED", "RETIRED"),
    "question_source": ("HUMAN", "CLAUDE_GENERATED"),
    "review_level": ("NONE", "SELF_VERIFIED", "HUMAN_APPROVED"),
    "attempt_kind": ("PRACTICE", "ROLE"),
    "terminated_reason": ("FOCUS_LIMIT", "EXPIRED", "ADMIN_VOID"),
    "blueprint_status": ("AVAILABLE", "UNAVAILABLE"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*NEW_ENUMS[name], name=name, create_type=False)


# Practice-test functions of 0004, now limited to PRACTICE attempts (a role attempt must never be
# served all at once or answered out of order through them) and with one open attempt of any
# kind per developer (Decision 4). `ORIGINAL_PRACTICE` restores 0004's versions on downgrade.
PRACTICE = r"""
CREATE OR REPLACE FUNCTION start_test_attempt(p_test uuid, p_now timestamptz, p_seed bigint)
RETURNS TABLE (attempt_id uuid, deadline_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_user uuid := app_uid();
  v_test skill_tests%ROWTYPE;
  v_ids uuid[];
  v_last timestamptz;
BEGIN
  IF v_user IS NULL OR app_role() <> 'DEVELOPER' THEN
    RAISE EXCEPTION 'only developers take tests' USING ERRCODE = 'insufficient_privilege';
  END IF;
  -- One start at a time per developer, across practice tests and role assessments.
  PERFORM pg_advisory_xact_lock(hashtextextended(v_user::text || '|attempt-start', 0));
  SELECT * INTO v_test FROM skill_tests WHERE id = p_test AND active;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'test not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF EXISTS (SELECT 1 FROM test_attempts a WHERE a.user_id = v_user
             AND a.submitted_at IS NULL AND a.deadline_at > p_now) THEN
    RAISE EXCEPTION 'attempt already open' USING ERRCODE = 'unique_violation';
  END IF;
  SELECT max(a.started_at) INTO v_last FROM test_attempts a
  WHERE a.user_id = v_user AND a.test_id = p_test AND a.scored;
  IF v_last IS NOT NULL AND v_last > p_now - interval '30 days' THEN
    RAISE EXCEPTION 'retake not allowed before %', v_last + interval '30 days'
      USING ERRCODE = 'check_violation';
  END IF;
  PERFORM setseed(((p_seed % 2000000) - 1000000) / 1000000.0);
  SELECT array_agg(t.id) INTO v_ids FROM (
    SELECT b.id FROM (SELECT id FROM question_bank
                      WHERE skill_id = v_test.skill_id AND active ORDER BY id) b
    ORDER BY random() LIMIT v_test.question_count
  ) t;
  IF v_ids IS NULL OR cardinality(v_ids) < v_test.question_count THEN
    RAISE EXCEPTION 'question bank too small' USING ERRCODE = 'data_exception';
  END IF;
  RETURN QUERY
  INSERT INTO test_attempts (kind, test_id, user_id, question_ids, answers, seed, started_at,
                             deadline_at, scored)
  VALUES ('PRACTICE', p_test, v_user, v_ids, '{}'::jsonb, p_seed, p_now,
          p_now + make_interval(secs => v_test.time_limit_seconds), true)
  RETURNING id, test_attempts.deadline_at;
END;
$$;

CREATE OR REPLACE FUNCTION attempt_questions(p_attempt uuid)
RETURNS TABLE (question_id uuid, ordinal int, text text, options jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT q.id, ord::int - 1, q.text, q.options
  FROM test_attempts a
  CROSS JOIN LATERAL unnest(a.question_ids) WITH ORDINALITY AS u(qid, ord)
  JOIN question_bank q ON q.id = u.qid
  WHERE a.id = p_attempt AND a.user_id = app_uid() AND a.kind = 'PRACTICE'
  ORDER BY ord
$$;

CREATE OR REPLACE FUNCTION record_test_answer(p_attempt uuid, p_question uuid, p_choice int,
                                              p_now timestamptz)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_attempt test_attempts%ROWTYPE;
BEGIN
  SELECT * INTO v_attempt FROM test_attempts
  WHERE id = p_attempt AND user_id = app_uid() AND kind = 'PRACTICE'
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF v_attempt.submitted_at IS NOT NULL OR p_now > v_attempt.deadline_at THEN
    RETURN false;
  END IF;
  IF NOT (p_question = ANY (v_attempt.question_ids)) OR p_choice NOT BETWEEN 0 AND 3 THEN
    RAISE EXCEPTION 'invalid answer' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE test_attempts SET answers = answers || jsonb_build_object(p_question::text, p_choice),
         updated_at = p_now
  WHERE id = p_attempt;
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION score_test_attempt(p_attempt uuid, p_now timestamptz)
RETURNS TABLE (score numeric, correct int, total int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_attempt test_attempts%ROWTYPE;
  v_correct int;
  v_total int;
  v_score numeric(4,3);
  v_skill uuid;
BEGIN
  SELECT * INTO v_attempt FROM test_attempts
  WHERE id = p_attempt AND (user_id = app_uid() OR caller_is_system()) AND kind = 'PRACTICE'
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF v_attempt.submitted_at IS NOT NULL THEN
    RAISE EXCEPTION 'already submitted' USING ERRCODE = 'unique_violation';
  END IF;
  v_total := cardinality(v_attempt.question_ids);
  SELECT count(*) INTO v_correct FROM question_bank q
  WHERE q.id = ANY (v_attempt.question_ids)
    AND (v_attempt.answers ->> q.id::text)::int = q.correct_index;
  v_score := round(v_correct::numeric / greatest(v_total, 1), 3);
  UPDATE test_attempts SET submitted_at = p_now, score = v_score, updated_at = p_now
  WHERE id = p_attempt;
  IF v_attempt.scored THEN
    SELECT t.skill_id INTO v_skill FROM skill_tests t WHERE t.id = v_attempt.test_id;
    INSERT INTO skill_evidence (user_id, skill_id, source, score, attempt_id, at)
    VALUES (v_attempt.user_id, v_skill, 'TEST', v_score, p_attempt, p_now);
  END IF;
  RETURN QUERY SELECT v_score, v_correct, v_total;
END;
$$;
"""

ORIGINAL_PRACTICE = (
    PRACTICE.replace(
        "PERFORM pg_advisory_xact_lock(hashtextextended(v_user::text || '|attempt-start', 0));",
        "PERFORM pg_advisory_xact_lock(hashtextextended(v_user::text || ':' || p_test::text, 0));",
    )
    .replace(
        "WHERE a.user_id = v_user\n             AND a.submitted_at IS NULL",
        "WHERE a.user_id = v_user AND a.test_id = p_test\n             AND a.submitted_at IS NULL",
    )
    .replace(
        "INSERT INTO test_attempts (kind, test_id, user_id, question_ids, answers, seed, started_at,\n"
        "                             deadline_at, scored)\n"
        "  VALUES ('PRACTICE', p_test,",
        "INSERT INTO test_attempts (test_id, user_id, question_ids, answers, seed, started_at,\n"
        "                             deadline_at, scored)\n"
        "  VALUES (p_test,",
    )
    .replace(" AND a.kind = 'PRACTICE'", "")
    .replace(" AND kind = 'PRACTICE'", "")
)

# Internal helpers: not granted to the runtime roles; called only from the definers below (which
# run as the owner). Grace: 5 s after the deadline (§6.3). Gaps: > 60 s without contact is a
# connection gap, > 2 min flags the attempt (§7.4); gaps never end an attempt.
HELPERS = r"""
CREATE FUNCTION role_token_state(p_stored bytea, p_retired bytea[], p_given bytea) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, public AS $$
  SELECT CASE
    WHEN p_given IS NULL THEN 'ATTEMPT_TOKEN_REQUIRED'
    WHEN p_stored IS NOT NULL AND p_given = p_stored THEN 'OK'
    WHEN p_given = ANY (p_retired) THEN 'ATTEMPT_MOVED'
    ELSE 'ATTEMPT_TOKEN_INVALID'
  END
$$;

CREATE FUNCTION role_touch(p_attempt uuid, p_now timestamptz) RETURNS void
LANGUAGE sql SET search_path = pg_catalog, public AS $$
  UPDATE test_attempts SET
    connection_gaps = connection_gaps + CASE
      WHEN last_heartbeat_at IS NOT NULL AND p_now - last_heartbeat_at > interval '60 seconds'
      THEN 1 ELSE 0 END,
    flagged = flagged OR (last_heartbeat_at IS NOT NULL
                          AND p_now - last_heartbeat_at > interval '120 seconds'),
    last_heartbeat_at = greatest(coalesce(last_heartbeat_at, p_now), p_now),
    updated_at = p_now
  WHERE id = p_attempt
$$;

-- Score a role attempt (§5.3, integers only); idempotent: an attempt already scored is left as
-- it is. Writes one ROLE_ASSESSMENT evidence row for every scored attempt.
CREATE FUNCTION role_score_core(p_attempt uuid, p_now timestamptz, p_reason terminated_reason)
RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
  b assessment_blueprints%ROWTYPE;
  v_reason terminated_reason := p_reason;
  v_breakdown jsonb;
  v_overall int;
  v_heavy_ok boolean;
  v_passed boolean;
  v_score numeric(4,3);
BEGIN
  SELECT * INTO a FROM test_attempts WHERE id = p_attempt AND kind = 'ROLE' FOR UPDATE;
  IF NOT FOUND OR a.submitted_at IS NOT NULL THEN
    RETURN;
  END IF;
  PERFORM role_touch(p_attempt, least(p_now, a.deadline_at));
  SELECT * INTO a FROM test_attempts WHERE id = p_attempt;
  SELECT * INTO b FROM assessment_blueprints WHERE id = a.blueprint_id;
  IF v_reason IS NULL AND jsonb_array_length(a.answers_locked) = 0 AND p_now > a.deadline_at THEN
    v_reason := 'EXPIRED';  -- abandoned without a single answer (reporting only)
  END IF;
  WITH comp AS (
    SELECT (c ->> 'competency_id')::uuid AS id, c ->> 'code' AS code, c ->> 'name' AS name,
           (c ->> 'weight_bp')::int AS weight_bp, ord
    FROM jsonb_array_elements(b.competencies) WITH ORDINALITY AS t(c, ord)
  ), qs AS (
    SELECT q.competency_id,
           CASE q.difficulty WHEN 1 THEN 2 WHEN 2 THEN 3 ELSE 4 END AS w,
           EXISTS (SELECT 1 FROM jsonb_array_elements(a.answers_locked) x
                   WHERE (x ->> 'question_id')::uuid = q.id
                     AND x ->> 'choice' IS NOT NULL
                     AND (x ->> 'choice')::int = q.correct_index) AS correct
    FROM question_bank q WHERE q.id = ANY (a.question_ids)
  ), per AS (
    SELECT comp.id, comp.code, comp.name, comp.weight_bp, comp.ord,
           coalesce(sum(qs.w) FILTER (WHERE qs.correct), 0)::int AS earned,
           coalesce(sum(qs.w), 0)::int AS possible
    FROM comp LEFT JOIN qs ON qs.competency_id = comp.id
    GROUP BY comp.id, comp.code, comp.name, comp.weight_bp, comp.ord
  ), scored AS (
    SELECT per.*, CASE WHEN possible > 0 THEN (10000 * earned) / possible ELSE 0 END AS score_bp
    FROM per
  )
  SELECT jsonb_agg(jsonb_build_object(
           'competency_id', id, 'code', code, 'name', name, 'weight_bp', weight_bp,
           'earned_w', earned, 'possible_w', possible, 'score_bp', score_bp) ORDER BY ord),
         (sum(weight_bp::bigint * score_bp) / 10000)::int,
         bool_and(weight_bp < (b.pass_rule ->> 'heavy_weight_bp')::int
                  OR score_bp >= (b.pass_rule ->> 'floor_bp')::int)
  INTO v_breakdown, v_overall, v_heavy_ok
  FROM scored;
  v_passed := coalesce(v_reason NOT IN ('FOCUS_LIMIT', 'ADMIN_VOID'), true)
              AND v_overall >= (b.pass_rule ->> 'overall_bp')::int
              AND coalesce(v_heavy_ok, true);
  v_score := ((v_overall / 10)::numeric / 1000)::numeric(4,3);
  UPDATE test_attempts SET
    submitted_at = p_now, score = v_score, breakdown = v_breakdown, overall_bp = v_overall,
    passed = v_passed, terminated_reason = v_reason,
    flagged = flagged OR v_reason = 'FOCUS_LIMIT', updated_at = p_now
  WHERE id = p_attempt;
  INSERT INTO skill_evidence (user_id, skill_id, source, score, attempt_id, at, blueprint_id,
                              passed, valid_until)
  VALUES (a.user_id, b.primary_skill_id, 'ROLE_ASSESSMENT', v_score, p_attempt, p_now, b.id,
          v_passed,
          CASE WHEN v_passed THEN p_now + make_interval(days => a.validity_days) END);
END;
$$;

-- The caller's own role attempt, locked, with its window token checked. Raises the domain code
-- (MESSAGE) for a wrong owner (no_data_found) or token; returns the row.
CREATE FUNCTION role_own_attempt(p_attempt uuid, p_token_hash bytea) RETURNS test_attempts
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
  v_state text;
BEGIN
  SELECT * INTO a FROM test_attempts
  WHERE id = p_attempt AND user_id = app_uid() AND kind = 'ROLE' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  v_state := role_token_state(a.attempt_token_hash, a.retired_token_hashes, p_token_hash);
  IF v_state <> 'OK' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = v_state;
  END IF;
  RETURN a;
END;
$$;
"""

HELPER_NAMES = (
    "role_token_state(bytea, bytea[], bytea)",
    "role_touch(uuid, timestamptz)",
    "role_score_core(uuid, timestamptz, terminated_reason)",
    "role_own_attempt(uuid, bytea)",
)

# Web-facing definers (§10). Domain errors are raised with SQLSTATE P0001 and the error code as
# the message (DETAIL carries JSON where the API needs more); outcomes that need a side effect
# first (scoring an expired attempt) are returned as a status instead of raised, so the scoring
# commits.
DEFINERS = r"""
CREATE FUNCTION create_slot_assessment(p_project uuid, p_slot uuid, p_blueprint jsonb,
                                       p_requirements_hash text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_id uuid;
BEGIN
  IF NOT (caller_is_system() OR EXISTS (
            SELECT 1 FROM projects p WHERE p.id = p_project AND p.client_id = app_uid()
            AND p.status IN ('DRAFT', 'BIDDING'))) THEN
    RAISE EXCEPTION 'only the project''s client links blueprints'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM project_slots s WHERE s.id = p_slot AND s.project_id = p_project) THEN
    RAISE EXCEPTION 'slot not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF p_blueprint ->> 'status' = 'AVAILABLE' AND (
       SELECT coalesce(sum((c ->> 'weight_bp')::int), 0)
       FROM jsonb_array_elements(p_blueprint -> 'competencies') c) <> 10000 THEN
    RAISE EXCEPTION 'blueprint weights must sum to 10000' USING ERRCODE = 'check_violation';
  END IF;
  INSERT INTO assessment_blueprints (algo_version, fingerprint, primary_skill_id, label,
                                     competencies, question_count, time_limit_seconds,
                                     difficulty_mix, pass_rule, status, unavailable_reason)
  VALUES ((p_blueprint ->> 'algo_version')::smallint, p_blueprint ->> 'fingerprint',
          (p_blueprint ->> 'primary_skill_id')::uuid, p_blueprint ->> 'label',
          p_blueprint -> 'competencies', (p_blueprint ->> 'question_count')::smallint,
          (p_blueprint ->> 'time_limit_seconds')::int, p_blueprint -> 'difficulty_mix',
          p_blueprint -> 'pass_rule', (p_blueprint ->> 'status')::blueprint_status,
          p_blueprint ->> 'unavailable_reason')
  ON CONFLICT (fingerprint) DO NOTHING;
  SELECT id INTO v_id FROM assessment_blueprints WHERE fingerprint = p_blueprint ->> 'fingerprint';
  INSERT INTO slot_assessments (slot_id, project_id, blueprint_id, requirements_hash)
  VALUES (p_slot, p_project, v_id, p_requirements_hash)
  ON CONFLICT (slot_id) DO NOTHING;
  RETURN (SELECT blueprint_id FROM slot_assessments WHERE slot_id = p_slot);
END;
$$;

-- Approved question counts per (competency, difficulty) for the blueprint builder; no content.
CREATE FUNCTION role_bank_counts(p_skill_ids uuid[], p_min_review review_level)
RETURNS TABLE (competency_id uuid, difficulty smallint, approved int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT q.competency_id, q.difficulty, count(*)::int
  FROM question_bank q JOIN competencies c ON c.id = q.competency_id
  WHERE (app_uid() IS NOT NULL OR caller_is_system())
    AND c.skill_id = ANY (p_skill_ids) AND c.active
    AND q.status = 'APPROVED' AND q.review_level >= p_min_review
  GROUP BY q.competency_id, q.difficulty
$$;

-- The approved pool of a blueprint's competencies for the selector: ids and exposure only.
CREATE FUNCTION role_question_pool(p_blueprint uuid, p_min_review review_level)
RETURNS TABLE (question_id uuid, competency_id uuid, difficulty smallint, times_served int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT q.id, q.competency_id, q.difficulty, q.times_served
  FROM question_bank q
  JOIN assessment_blueprints b ON b.id = p_blueprint
  WHERE (app_uid() IS NOT NULL OR caller_is_system())
    AND q.status = 'APPROVED' AND q.review_level >= p_min_review
    AND q.competency_id IN (SELECT (c ->> 'competency_id')::uuid
                            FROM jsonb_array_elements(b.competencies) c)
$$;

-- Question ids the caller saw in any attempt (practice or role) since a date.
CREATE FUNCTION user_recent_questions(p_since timestamptz)
RETURNS TABLE (question_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT DISTINCT u.qid
  FROM test_attempts a CROSS JOIN LATERAL unnest(a.question_ids) AS u(qid)
  WHERE a.user_id = app_uid() AND a.started_at >= p_since
$$;

-- Start a role attempt (§6.2 rules 7–9 re-checked under the per-developer lock; the question ids
-- chosen by the Python selector are validated against the blueprint's allocation).
CREATE FUNCTION start_role_attempt(
  p_blueprint uuid, p_question_ids uuid[], p_now timestamptz, p_seed bigint, p_project uuid,
  p_slot uuid, p_token_hash bytea, p_extra_time int, p_rules_version smallint,
  p_retake_days int, p_leave_limit smallint, p_validity_days smallint, p_reused_seen boolean,
  p_min_review review_level)
RETURNS TABLE (attempt_id uuid, deadline_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  v_user uuid := app_uid();
  b assessment_blueprints%ROWTYPE;
  v_open test_attempts%ROWTYPE;
  v_last timestamptz;
  v_bad int;
BEGIN
  IF v_user IS NULL OR app_role() <> 'DEVELOPER' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ROLE_NOT_ALLOWED';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(v_user::text || '|attempt-start', 0));
  SELECT * INTO b FROM assessment_blueprints WHERE id = p_blueprint;
  IF NOT FOUND OR b.status <> 'AVAILABLE' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'BLUEPRINT_UNAVAILABLE';
  END IF;
  -- Rule 7: a valid passing result for this blueprint (= fingerprint) already exists.
  IF EXISTS (SELECT 1 FROM skill_evidence e
             WHERE e.user_id = v_user AND e.source = 'ROLE_ASSESSMENT'
               AND e.blueprint_id = p_blueprint AND e.passed AND e.voided_at IS NULL
               AND e.valid_until > p_now) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ALREADY_PASSED';
  END IF;
  -- Rule 8: one open attempt of any kind.
  SELECT * INTO v_open FROM test_attempts a
  WHERE a.user_id = v_user AND a.submitted_at IS NULL
    AND a.deadline_at + CASE WHEN a.kind = 'ROLE' THEN interval '5 seconds'
                             ELSE interval '0 seconds' END > p_now
  ORDER BY a.started_at DESC LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ATTEMPT_OPEN',
      DETAIL = jsonb_build_object('attempt_id', v_open.id, 'kind', v_open.kind,
                                  'blueprint_id', v_open.blueprint_id)::text;
  END IF;
  -- Rule 9: one scored attempt per fingerprint per retake window (voided ones don't count).
  SELECT max(a.submitted_at) INTO v_last FROM test_attempts a
  WHERE a.user_id = v_user AND a.kind = 'ROLE' AND a.blueprint_id = p_blueprint
    AND a.submitted_at IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM skill_evidence e
                    WHERE e.attempt_id = a.id AND e.voided_at IS NOT NULL);
  IF v_last IS NOT NULL AND v_last > p_now - make_interval(days => p_retake_days) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'RETAKE_LOCKED',
      DETAIL = jsonb_build_object('next_allowed_at',
                                  v_last + make_interval(days => p_retake_days))::text;
  END IF;
  -- The selection must be exactly the blueprint's allocation, from the approved pool.
  IF cardinality(p_question_ids) <> b.question_count
     OR (SELECT count(DISTINCT x) FROM unnest(p_question_ids) x) <> b.question_count THEN
    RAISE EXCEPTION 'selection does not match the blueprint' USING ERRCODE = 'check_violation';
  END IF;
  SELECT count(*) INTO v_bad FROM (
    SELECT (c ->> 'competency_id')::uuid AS cid, d.difficulty,
           (c ->> d.field)::int AS wanted,
           (SELECT count(*) FROM question_bank q
            WHERE q.id = ANY (p_question_ids) AND q.competency_id = (c ->> 'competency_id')::uuid
              AND q.difficulty = d.difficulty AND q.status = 'APPROVED'
              AND q.review_level >= p_min_review) AS got
    FROM jsonb_array_elements(b.competencies) c
    CROSS JOIN (VALUES (1, 'easy'), (2, 'medium'), (3, 'hard')) AS d(difficulty, field)
  ) t WHERE t.wanted <> t.got;
  IF v_bad > 0 THEN
    RAISE EXCEPTION 'selection does not match the blueprint' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE question_bank SET times_served = times_served + 1 WHERE id = ANY (p_question_ids);
  RETURN QUERY
  INSERT INTO test_attempts (kind, blueprint_id, user_id, question_ids, answers, seed, started_at,
                             deadline_at, scored, context_project_id, context_slot_id,
                             attempt_token_hash, consent_at, rules_version, extra_time_seconds,
                             reused_seen, leave_limit, validity_days, last_heartbeat_at)
  VALUES ('ROLE', p_blueprint, v_user, p_question_ids, '{}'::jsonb, p_seed, p_now,
          p_now + make_interval(secs => b.time_limit_seconds + p_extra_time), true, p_project,
          p_slot, p_token_hash, p_now, p_rules_version, p_extra_time, p_reused_seen,
          p_leave_limit, p_validity_days, p_now)
  RETURNING id, test_attempts.deadline_at;
END;
$$;

-- The current question only (owner + window token); empty once the attempt is closed.
CREATE FUNCTION role_current_question(p_attempt uuid, p_token_hash bytea)
RETURNS TABLE (idx int, total int, question_id uuid, text text, code_snippet text,
               options jsonb, competency_name text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  a := role_own_attempt(p_attempt, p_token_hash);
  IF a.submitted_at IS NOT NULL OR a.current_index >= cardinality(a.question_ids) THEN
    RETURN;
  END IF;
  RETURN QUERY
  SELECT a.current_index::int, cardinality(a.question_ids), q.id, q.text, q.code_snippet,
         q.options, c.name
  FROM question_bank q LEFT JOIN competencies c ON c.id = q.competency_id
  WHERE q.id = a.question_ids[a.current_index + 1];
END;
$$;

-- Lock one answer (or a skip) for the current question and move on (§6.4). Status:
-- NEXT · SCORED (that was the last question) · DUPLICATE (a retry of the last answer) ·
-- CLOSED (already scored) · EXPIRED (deadline + grace passed: scored now, answer refused).
CREATE FUNCTION record_role_answer(p_attempt uuid, p_question uuid, p_choice int,
                                   p_now timestamptz, p_token_hash bytea)
RETURNS TABLE (status text, current_index int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
  v_total int;
  v_last jsonb;
BEGIN
  a := role_own_attempt(p_attempt, p_token_hash);
  IF a.submitted_at IS NOT NULL THEN
    RETURN QUERY SELECT 'CLOSED', a.current_index::int;
    RETURN;
  END IF;
  IF p_now > a.deadline_at + interval '5 seconds' THEN
    PERFORM role_score_core(p_attempt, p_now, NULL);
    RETURN QUERY SELECT 'EXPIRED', a.current_index::int;
    RETURN;
  END IF;
  IF p_choice IS NOT NULL AND p_choice NOT BETWEEN 0 AND 3 THEN
    RAISE EXCEPTION 'invalid choice' USING ERRCODE = 'check_violation';
  END IF;
  PERFORM role_touch(p_attempt, p_now);
  v_total := cardinality(a.question_ids);
  IF a.current_index > 0 THEN
    v_last := a.answers_locked -> (jsonb_array_length(a.answers_locked) - 1);
    IF (v_last ->> 'question_id')::uuid = p_question THEN
      IF (v_last -> 'choice') IS NOT DISTINCT FROM to_jsonb(p_choice) THEN
        RETURN QUERY SELECT 'DUPLICATE', a.current_index::int;
        RETURN;
      END IF;
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NOT_CURRENT_QUESTION';
    END IF;
  END IF;
  IF a.current_index >= v_total OR a.question_ids[a.current_index + 1] <> p_question THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NOT_CURRENT_QUESTION';
  END IF;
  UPDATE test_attempts SET
    answers_locked = answers_locked || jsonb_build_array(jsonb_build_object(
      'question_id', p_question, 'choice', to_jsonb(p_choice), 'answered_at', p_now)),
    current_index = current_index + 1, updated_at = p_now
  WHERE id = p_attempt;
  IF a.current_index + 1 >= v_total THEN
    PERFORM role_score_core(p_attempt, p_now, NULL);
    RETURN QUERY SELECT 'SCORED', (a.current_index + 1)::int;
    RETURN;
  END IF;
  RETURN QUERY SELECT 'NEXT', (a.current_index + 1)::int;
END;
$$;

-- End early: the remaining questions count as wrong (§6.4). Status SCORED or CLOSED.
CREATE FUNCTION finish_role_attempt(p_attempt uuid, p_now timestamptz, p_token_hash bytea)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  a := role_own_attempt(p_attempt, p_token_hash);
  IF a.submitted_at IS NOT NULL THEN
    RETURN 'CLOSED';
  END IF;
  PERFORM role_score_core(p_attempt, p_now, NULL);
  RETURN 'SCORED';
END;
$$;

-- One counted leave (§7.4), idempotent by seq. Status: WARNING · TERMINATED (the limit was
-- reached: scored, can't pass, flagged) · DUPLICATE · CLOSED · EXPIRED.
CREATE FUNCTION record_focus_event(p_attempt uuid, p_seq int, p_type text, p_now timestamptz,
                                   p_client_at timestamptz, p_fullscreen_supported boolean,
                                   p_token_hash bytea)
RETURNS TABLE (status text, focus_leaves int)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
  v_event jsonb;
BEGIN
  a := role_own_attempt(p_attempt, p_token_hash);
  IF a.submitted_at IS NOT NULL THEN
    RETURN QUERY SELECT 'CLOSED', a.focus_leaves::int;
    RETURN;
  END IF;
  IF p_now > a.deadline_at + interval '5 seconds' THEN
    PERFORM role_score_core(p_attempt, p_now, NULL);
    RETURN QUERY SELECT 'EXPIRED', a.focus_leaves::int;
    RETURN;
  END IF;
  IF p_seq NOT BETWEEN 1 AND 100
     OR p_type NOT IN ('VISIBILITY_HIDDEN', 'FULLSCREEN_EXIT', 'WINDOW_BLUR', 'PAGE_UNLOAD') THEN
    RAISE EXCEPTION 'invalid focus event' USING ERRCODE = 'check_violation';
  END IF;
  PERFORM role_touch(p_attempt, p_now);
  IF p_seq <= a.last_focus_seq THEN
    RETURN QUERY SELECT 'DUPLICATE', a.focus_leaves::int;
    RETURN;
  END IF;
  v_event := jsonb_build_object('seq', p_seq, 'type', p_type, 'server_at', p_now,
                                'client_at', p_client_at);
  IF p_fullscreen_supported IS NOT NULL THEN
    v_event := v_event || jsonb_build_object('fullscreen_supported', p_fullscreen_supported);
  END IF;
  UPDATE test_attempts SET
    focus_events = CASE WHEN jsonb_array_length(focus_events) < 30
                        THEN focus_events || jsonb_build_array(v_event) ELSE focus_events END,
    focus_leaves = focus_leaves + 1, last_focus_seq = p_seq, updated_at = p_now
  WHERE id = p_attempt;
  IF a.focus_leaves + 1 >= coalesce(a.leave_limit, 2) THEN
    PERFORM role_score_core(p_attempt, p_now, 'FOCUS_LIMIT');
    RETURN QUERY SELECT 'TERMINATED', (a.focus_leaves + 1)::int;
    RETURN;
  END IF;
  RETURN QUERY SELECT 'WARNING', (a.focus_leaves + 1)::int;
END;
$$;

-- Heartbeat (§7.4): records contact and measures gaps. Status OK · CLOSED · EXPIRED.
CREATE FUNCTION record_heartbeat(p_attempt uuid, p_now timestamptz, p_token_hash bytea)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  a := role_own_attempt(p_attempt, p_token_hash);
  IF a.submitted_at IS NOT NULL THEN
    RETURN 'CLOSED';
  END IF;
  IF p_now > a.deadline_at + interval '5 seconds' THEN
    PERFORM role_score_core(p_attempt, p_now, NULL);
    RETURN 'EXPIRED';
  END IF;
  PERFORM role_touch(p_attempt, p_now);
  RETURN 'OK';
END;
$$;

-- Resume in a (new) window: a new token, the old one retired (§6.6). The owner needs no token
-- here. Status OK · CLOSED · EXPIRED.
CREATE FUNCTION rotate_attempt_token(p_attempt uuid, p_new_hash bytea, p_now timestamptz)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  SELECT * INTO a FROM test_attempts
  WHERE id = p_attempt AND user_id = app_uid() AND kind = 'ROLE' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF a.submitted_at IS NOT NULL THEN
    RETURN 'CLOSED';
  END IF;
  IF p_now > a.deadline_at + interval '5 seconds' THEN
    PERFORM role_score_core(p_attempt, p_now, NULL);
    RETURN 'EXPIRED';
  END IF;
  PERFORM role_touch(p_attempt, p_now);
  UPDATE test_attempts SET
    retired_token_hashes = (array_append(retired_token_hashes, attempt_token_hash))[
      greatest(1, cardinality(retired_token_hashes) - 8):cardinality(retired_token_hashes) + 1],
    attempt_token_hash = p_new_hash, updated_at = p_now
  WHERE id = p_attempt;
  RETURN 'OK';
END;
$$;

-- Score once the deadline (+ grace) has passed: by the owner's next request or the expiry job.
CREATE FUNCTION score_role_attempt(p_attempt uuid, p_now timestamptz)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  SELECT * INTO a FROM test_attempts
  WHERE id = p_attempt AND kind = 'ROLE' AND (user_id = app_uid() OR caller_is_system())
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF a.submitted_at IS NOT NULL THEN
    RETURN 'CLOSED';
  END IF;
  IF p_now <= a.deadline_at + interval '5 seconds' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'INVALID_STATE';
  END IF;
  PERFORM role_score_core(p_attempt, p_now, NULL);
  RETURN 'SCORED';
END;
$$;

-- Admin void (§12.1): an open attempt is scored as ADMIN_VOID first; the evidence is voided.
CREATE FUNCTION void_role_attempt(p_attempt uuid, p_reason text, p_now timestamptz)
RETURNS TABLE (user_id uuid, blueprint_id uuid, evidence_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
  a test_attempts%ROWTYPE;
BEGIN
  IF NOT is_admin() THEN
    RAISE EXCEPTION 'admins only' USING ERRCODE = 'insufficient_privilege';
  END IF;
  SELECT * INTO a FROM test_attempts WHERE id = p_attempt AND kind = 'ROLE' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'attempt not found' USING ERRCODE = 'no_data_found';
  END IF;
  IF a.submitted_at IS NULL THEN
    PERFORM role_score_core(p_attempt, p_now, 'ADMIN_VOID');
  END IF;
  RETURN QUERY
  UPDATE skill_evidence e SET voided_at = p_now, void_reason = p_reason, updated_at = p_now
  WHERE e.attempt_id = p_attempt AND e.voided_at IS NULL
  RETURNING e.user_id, e.blueprint_id, e.id;
END;
$$;

CREATE FUNCTION mark_role_attempt_reviewed(p_attempt uuid, p_now timestamptz) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF NOT is_admin() THEN
    RAISE EXCEPTION 'admins only' USING ERRCODE = 'insufficient_privilege';
  END IF;
  UPDATE test_attempts SET admin_reviewed_at = p_now, admin_reviewed_by = app_uid(),
         updated_at = p_now
  WHERE id = p_attempt AND kind = 'ROLE';
  RETURN FOUND;
END;
$$;
"""

DEFINER_NAMES = (
    "create_slot_assessment(uuid, uuid, jsonb, text)",
    "role_bank_counts(uuid[], review_level)",
    "role_question_pool(uuid, review_level)",
    "user_recent_questions(timestamptz)",
    "start_role_attempt(uuid, uuid[], timestamptz, bigint, uuid, uuid, bytea, int, smallint, "
    "int, smallint, smallint, boolean, review_level)",
    "role_current_question(uuid, bytea)",
    "record_role_answer(uuid, uuid, int, timestamptz, bytea)",
    "finish_role_attempt(uuid, timestamptz, bytea)",
    "record_focus_event(uuid, int, text, timestamptz, timestamptz, boolean, bytea)",
    "record_heartbeat(uuid, timestamptz, bytea)",
    "rotate_attempt_token(uuid, bytea, timestamptz)",
    "score_role_attempt(uuid, timestamptz)",
    "void_role_attempt(uuid, text, timestamptz)",
    "mark_role_attempt_reviewed(uuid, timestamptz)",
)

TRIGGERS = r"""
-- Approved (and retired) questions keep their content: a correction is a new row (§4.2).
CREATE FUNCTION question_bank_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'DRAFT' THEN
      RAISE EXCEPTION 'approved or retired questions are kept' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status <> 'DRAFT' THEN
    IF (NEW.skill_id, NEW.text, NEW.options, NEW.correct_index, NEW.code_snippet,
        NEW.competency_id, NEW.difficulty, NEW.slug, NEW.version)
       IS DISTINCT FROM (OLD.skill_id, OLD.text, OLD.options, OLD.correct_index, OLD.code_snippet,
                         OLD.competency_id, OLD.difficulty, OLD.slug, OLD.version) THEN
      RAISE EXCEPTION 'approved questions are immutable: retire it and add a new version'
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT (NEW.status = OLD.status OR (OLD.status = 'APPROVED' AND NEW.status = 'RETIRED')) THEN
      RAISE EXCEPTION 'an approved question can only be retired' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER question_bank_immutable BEFORE UPDATE OR DELETE ON question_bank
  FOR EACH ROW EXECUTE FUNCTION question_bank_guard();

CREATE FUNCTION blueprint_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  RAISE EXCEPTION 'assessment blueprints are immutable' USING ERRCODE = 'insufficient_privilege';
END;
$$;
CREATE TRIGGER assessment_blueprints_immutable BEFORE UPDATE OR DELETE ON assessment_blueprints
  FOR EACH ROW EXECUTE FUNCTION blueprint_immutable();
"""

TRIGGER_FUNCTIONS = ("question_bank_guard()", "blueprint_immutable()")


def _profile_0008() -> str:
    """`public_developer_profile` as migration 0008 left it (restored on downgrade)."""
    spec = importlib.util.spec_from_file_location(
        "m0008", Path(__file__).with_name("0008_public_best_score.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.BEST)


# Public profiles (§11.6): `verified_scores` are practice-test results only (best per skill, as
# in 0008); `role_assessments` lists valid passes with the role label — never project names,
# failed or ended attempts, flags or answers.
_OLD_SCORES = """FROM (SELECT DISTINCT ON (skill_id) skill_id, score, at FROM skill_evidence
            WHERE user_id = u.id ORDER BY skill_id, score DESC, at DESC) e
      JOIN skills s ON s.id = e.skill_id), '[]'),"""
_NEW_SCORES = """FROM (SELECT DISTINCT ON (skill_id) skill_id, score, at FROM skill_evidence
            WHERE user_id = u.id AND source = 'TEST'
            ORDER BY skill_id, score DESC, at DESC) e
      JOIN skills s ON s.id = e.skill_id), '[]'),
    'role_assessments', coalesce((
      SELECT jsonb_agg(jsonb_build_object('label', b.label, 'score', e.score::text, 'at', e.at,
                                          'valid_until', e.valid_until) ORDER BY e.at DESC)
      FROM skill_evidence e JOIN assessment_blueprints b ON b.id = e.blueprint_id
      WHERE e.user_id = u.id AND e.source = 'ROLE_ASSESSMENT' AND e.passed
        AND e.voided_at IS NULL AND e.valid_until > now()), '[]'),"""


def _profile_0011() -> str:
    old = _profile_0008()
    assert _OLD_SCORES in old, "0008's public_developer_profile changed"
    return old.replace(_OLD_SCORES, _NEW_SCORES)
NEW_TABLES = ("competencies", "assessment_blueprints", "slot_assessments", "user_accommodations")


def _ddl(sql: str) -> None:
    """Run a block of function DDL exactly as written, on the migration's own transaction.

    Neither SQLAlchemy's bind parameters (`a[1:cardinality(a)]` reads as `:cardinality`) nor the
    driver's placeholders (plpgsql's `RAISE … '%'`) may touch it, so it goes to the raw cursor,
    which does no parameter processing when no parameters are given.
    """
    cursor = op.get_bind().connection.dbapi_connection.cursor()  # type: ignore[union-attr]
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def _policies() -> str:
    stmts: list[str] = []
    for table in NEW_TABLES:
        stmts += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY migrator_all ON {table} TO devsync_migrator USING (true) WITH CHECK (true)",
        ]
    stmts += [
        # The competency catalogue is public (guests included); admins maintain it.
        f"CREATE POLICY read_all ON competencies FOR SELECT TO {DML_ROLES} USING (true)",
        f"CREATE POLICY admin_write ON competencies FOR ALL TO {DML_ROLES} "
        "USING (is_admin() OR is_system()) WITH CHECK (is_admin() OR is_system())",
        # Blueprints hold no secrets: any signed-in user reads them; inserts only through
        # create_slot_assessment (no write policy for the runtime roles).
        f"CREATE POLICY signed_in_select ON assessment_blueprints FOR SELECT TO {DML_ROLES} "
        "USING (app_uid() IS NOT NULL OR is_system())",
        # A slot's link is visible to whoever can see the project (projects' own RLS applies).
        f"CREATE POLICY project_visible ON slot_assessments FOR SELECT TO {DML_ROLES} "  # noqa: S608 - DDL from constants
        "USING (is_system() OR EXISTS (SELECT 1 FROM projects p WHERE p.id = project_id))",
        f"CREATE POLICY owner_select ON user_accommodations FOR SELECT TO {DML_ROLES} "
        "USING (user_id = app_uid() OR is_admin() OR is_system())",
        f"CREATE POLICY admin_write ON user_accommodations FOR ALL TO {DML_ROLES} "
        "USING (is_admin()) WITH CHECK (is_admin())",
    ]
    return ";\n".join(stmts) + ";"


def _seed_bank() -> None:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    conn = op.get_bind()
    for skill in data["skills"]:
        skill_id = conn.execute(
            sa.text("SELECT id FROM skills WHERE name = :n"), {"n": skill["name"]}
        ).scalar_one()
        codes: dict[str, str] = {}
        for c in skill["competencies"]:
            codes[c["code"]] = conn.execute(
                sa.text(
                    "INSERT INTO competencies (skill_id, code, name, description, is_core, "
                    "keywords, position) VALUES (:s, :code, :name, :d, :core, :kw, :pos) "
                    "RETURNING id"
                ),
                {"s": skill_id, "code": c["code"], "name": c["name"], "d": c["description"],
                 "core": c["is_core"], "kw": c["keywords"], "pos": c["position"]},
            ).scalar_one()  # fmt: skip
        for q in skill["questions"]:
            values = {
                "s": skill_id, "slug": q["id"], "text": q["text"],
                "comp": codes[q["competency"]] if q["competency"] else None,
                "status": q["status"], "source": q["source"], "snippet": q["code_snippet"],
                "expl": q["explanation"], "level": q["review_level"],
                "rname": q["reviewed_by_name"], "rat": q["reviewed_at"],
                "ver": json.dumps(q["verification"]) if q["verification"] is not None else None,
                "options": json.dumps(q["options"]), "correct": q["correct_index"],
                "difficulty": q["difficulty"], "active": q["active"],
            }  # fmt: skip
            if q["legacy"]:
                # The original question, found by text in its skill (stored by 0004).
                updated = conn.execute(
                    sa.text(
                        "UPDATE question_bank SET slug = :slug, competency_id = :comp, "
                        "status = CAST(:status AS question_status), "
                        "source = CAST(:source AS question_source), code_snippet = :snippet, "
                        "explanation = :expl, review_level = CAST(:level AS review_level), "
                        "reviewed_by_name = :rname, reviewed_at = CAST(:rat AS timestamptz), "
                        "verification = CAST(:ver AS jsonb) "
                        "WHERE skill_id = :s AND text = :text AND slug IS NULL "
                        "AND options = CAST(:options AS jsonb) AND correct_index = :correct"
                    ),
                    values,
                ).rowcount
                if updated != 1:
                    raise RuntimeError(f"legacy question {q['id']} matched {updated} rows")
            else:
                conn.execute(
                    sa.text(
                        "INSERT INTO question_bank (skill_id, text, options, correct_index, "
                        "difficulty, active, slug, competency_id, status, source, code_snippet, "
                        "explanation, review_level, reviewed_by_name, reviewed_at, verification) "
                        "VALUES (:s, :text, CAST(:options AS jsonb), :correct, :difficulty, "
                        ":active, :slug, :comp, CAST(:status AS question_status), "
                        "CAST(:source AS question_source), :snippet, :expl, "
                        "CAST(:level AS review_level), :rname, CAST(:rat AS timestamptz), "
                        "CAST(:ver AS jsonb))"
                    ),
                    values,
                )


def upgrade() -> None:
    # A new enum value must be committed before anything uses it (PostgreSQL), so it gets its
    # own transaction; ADD VALUE IF NOT EXISTS keeps a re-run harmless.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidence_source ADD VALUE IF NOT EXISTS 'ROLE_ASSESSMENT'")
    for name, values in NEW_ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind())

    op.create_table(
        "competencies",
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_core", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("code ~ '^[a-z][a-z0-9_]{2,40}$'", name=op.f("ck_competencies_code_format")),
        sa.CheckConstraint("char_length(name) BETWEEN 3 AND 60", name=op.f("ck_competencies_name_len")),
        sa.CheckConstraint("char_length(description) <= 300", name=op.f("ck_competencies_description_len")),
        sa.CheckConstraint("cardinality(keywords) BETWEEN 1 AND 40", name=op.f("ck_competencies_keywords_count")),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], name=op.f("fk_competencies_skill_id_skills")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competencies")),
        sa.UniqueConstraint("skill_id", "code", name=op.f("uq_competencies_skill_id")),
    )  # fmt: skip

    for column in (
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("competency_id", sa.UUID(), nullable=True),
        sa.Column("status", _enum("question_status"), server_default="DRAFT", nullable=False),
        sa.Column("source", _enum("question_source"), server_default="HUMAN", nullable=False),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("review_level", _enum("review_level"), server_default="NONE", nullable=False),
        sa.Column("reviewed_by_name", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("times_served", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ):
        op.add_column("question_bank", column)
    op.create_foreign_key(
        op.f("fk_question_bank_competency_id_competencies"), "question_bank", "competencies",
        ["competency_id"], ["id"],
    )  # fmt: skip
    op.create_foreign_key(
        op.f("fk_question_bank_reviewed_by_user_users"), "question_bank", "users",
        ["reviewed_by_user"], ["id"], ondelete="SET NULL",
    )  # fmt: skip
    op.create_unique_constraint(op.f("uq_question_bank_slug"), "question_bank", ["slug"])
    op.create_index(
        "ix_question_bank_competency_status", "question_bank",
        ["competency_id", "status", "difficulty"],
    )  # fmt: skip

    op.create_table(
        "assessment_blueprints",
        sa.Column("algo_version", sa.SmallInteger(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("primary_skill_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("competencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("question_count", sa.SmallInteger(), nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("difficulty_mix", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pass_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", _enum("blueprint_status"), nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name=op.f("ck_assessment_blueprints_fingerprint_format")),
        sa.CheckConstraint("question_count BETWEEN 1 AND 50", name=op.f("ck_assessment_blueprints_count_range")),
        sa.CheckConstraint("time_limit_seconds BETWEEN 60 AND 7200", name=op.f("ck_assessment_blueprints_time_range")),
        sa.CheckConstraint(
            "(status = 'UNAVAILABLE') = (unavailable_reason IS NOT NULL)",
            name=op.f("ck_assessment_blueprints_reason_iff_unavailable"),
        ),
        sa.ForeignKeyConstraint(["primary_skill_id"], ["skills.id"], name=op.f("fk_assessment_blueprints_primary_skill_id_skills")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_blueprints")),
        sa.UniqueConstraint("fingerprint", name=op.f("uq_assessment_blueprints_fingerprint")),
    )  # fmt: skip
    op.create_table(
        "slot_assessments",
        sa.Column("slot_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("blueprint_id", sa.UUID(), nullable=False),
        sa.Column("requirements_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blueprint_id"], ["assessment_blueprints.id"], name=op.f("fk_slot_assessments_blueprint_id_assessment_blueprints")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_slot_assessments_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slot_id"], ["project_slots.id"], name=op.f("fk_slot_assessments_slot_id_project_slots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("slot_id", name=op.f("pk_slot_assessments")),
    )  # fmt: skip
    op.create_index(op.f("ix_slot_assessments_project_id"), "slot_assessments", ["project_id"])
    op.create_table(
        "user_accommodations",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("extra_time_pct", sa.SmallInteger(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("granted_by", sa.UUID(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("extra_time_pct IN (0, 25, 50)", name=op.f("ck_user_accommodations_extra_time_values")),
        sa.CheckConstraint("char_length(note) <= 300", name=op.f("ck_user_accommodations_note_len")),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], name=op.f("fk_user_accommodations_granted_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_accommodations_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_accommodations")),
    )  # fmt: skip

    for column in (
        sa.Column("kind", _enum("attempt_kind"), server_default="PRACTICE", nullable=False),
        sa.Column("blueprint_id", sa.UUID(), nullable=True),
        sa.Column("context_project_id", sa.UUID(), nullable=True),
        sa.Column("context_slot_id", sa.UUID(), nullable=True),
        sa.Column("current_index", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("answers_locked", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("attempt_token_hash", sa.LargeBinary(), nullable=True),
        sa.Column("retired_token_hashes", postgresql.ARRAY(sa.LargeBinary()), server_default="{}", nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rules_version", sa.SmallInteger(), nullable=True),
        sa.Column("leave_limit", sa.SmallInteger(), nullable=True),
        sa.Column("validity_days", sa.SmallInteger(), nullable=True),
        sa.Column("focus_leaves", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("focus_events", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("last_focus_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_gaps", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("terminated_reason", _enum("terminated_reason"), nullable=True),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overall_bp", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("flagged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("extra_time_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reused_seen", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("admin_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_reviewed_by", sa.UUID(), nullable=True),
    ):  # fmt: skip
        op.add_column("test_attempts", column)
    op.alter_column("test_attempts", "test_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        op.f("fk_test_attempts_blueprint_id_assessment_blueprints"), "test_attempts",
        "assessment_blueprints", ["blueprint_id"], ["id"],
    )  # fmt: skip
    op.create_foreign_key(
        op.f("fk_test_attempts_admin_reviewed_by_users"), "test_attempts", "users",
        ["admin_reviewed_by"], ["id"], ondelete="SET NULL",
    )  # fmt: skip
    for name, condition in (
        ("kind_target",
         "(kind = 'PRACTICE' AND test_id IS NOT NULL AND blueprint_id IS NULL) OR "
         "(kind = 'ROLE' AND blueprint_id IS NOT NULL AND test_id IS NULL "
         "AND consent_at IS NOT NULL)"),
        ("overall_range", "overall_bp IS NULL OR overall_bp BETWEEN 0 AND 10000"),
        ("counters_valid", "focus_leaves >= 0 AND connection_gaps >= 0"),
        ("focus_events_bounded", "jsonb_array_length(focus_events) <= 30"),
        ("extra_time_range", "extra_time_seconds BETWEEN 0 AND 3600"),
    ):  # fmt: skip
        op.create_check_constraint(op.f(f"ck_test_attempts_{name}"), "test_attempts", condition)
    op.create_index(
        "ix_test_attempts_open_by_user", "test_attempts", ["user_id"],
        postgresql_where=sa.text("submitted_at IS NULL"),  # forbidden-ok: DDL
    )  # fmt: skip
    op.create_index(
        "ix_test_attempts_blueprint_user", "test_attempts", ["blueprint_id", "user_id", "submitted_at"]
    )
    op.create_index(
        "ix_test_attempts_flagged", "test_attempts", ["submitted_at"],
        postgresql_where=sa.text("flagged"),  # forbidden-ok: DDL
    )  # fmt: skip

    for column in (
        sa.Column("blueprint_id", sa.UUID(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
    ):
        op.add_column("skill_evidence", column)
    op.create_foreign_key(
        op.f("fk_skill_evidence_blueprint_id_assessment_blueprints"), "skill_evidence",
        "assessment_blueprints", ["blueprint_id"], ["id"],
    )  # fmt: skip
    op.create_check_constraint(
        op.f("ck_skill_evidence_role_evidence_complete"), "skill_evidence",
        "source::text <> 'ROLE_ASSESSMENT' OR (blueprint_id IS NOT NULL AND passed IS NOT NULL)",
    )  # fmt: skip
    op.create_check_constraint(
        op.f("ck_skill_evidence_void_reason_len"), "skill_evidence", "char_length(void_reason) <= 500"
    )
    op.create_index(
        "ix_skill_evidence_user_blueprint", "skill_evidence", ["user_id", "blueprint_id"]
    )

    op.add_column("bids", sa.Column("assessment_evidence_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_bids_assessment_evidence_id_skill_evidence"), "bids", "skill_evidence",
        ["assessment_evidence_id"], ["id"], ondelete="SET NULL",
    )  # fmt: skip

    _seed_bank()
    for name, condition in (
        ("snippet_len", "char_length(code_snippet) <= 1500"),
        ("explanation_len", "char_length(explanation) <= 600"),
        ("approved_is_reviewed",
         "status <> 'APPROVED' OR (competency_id IS NOT NULL "
         "AND review_level IN ('SELF_VERIFIED', 'HUMAN_APPROVED'))"),
        ("human_approval_named", "review_level <> 'HUMAN_APPROVED' OR reviewed_by_name IS NOT NULL"),
        ("counters_valid", "times_served >= 0 AND version >= 1"),
    ):  # fmt: skip
        op.create_check_constraint(op.f(f"ck_question_bank_{name}"), "question_bank", condition)

    _ddl(PRACTICE)
    _ddl(HELPERS)
    _ddl(DEFINERS)
    _ddl(TRIGGERS)
    _ddl(_profile_0011())
    for fn in HELPER_NAMES:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
    for fn in DEFINER_NAMES:
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC, devsync_readonly")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {DML_ROLES}")
    op.execute(_policies())

    settings_table = sa.table(
        "platform_settings",
        sa.column("version", sa.Integer()),
        sa.column("values", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
    )
    op.bulk_insert(
        settings_table,
        [{"version": 5, "values": json.loads(SETTINGS_V5.read_text(encoding="utf-8")),
          "reason": "Role assessment settings and rate limits (role assessment spec §4.9, §9)"}],
    )  # fmt: skip


def downgrade() -> None:
    op.execute("ALTER TABLE platform_settings DISABLE TRIGGER platform_settings_immutable")
    op.execute("DELETE FROM platform_settings WHERE version = 5")
    op.execute("ALTER TABLE platform_settings ENABLE TRIGGER platform_settings_immutable")
    for fn in DEFINER_NAMES:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    for fn in HELPER_NAMES:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    op.execute("DROP TRIGGER IF EXISTS question_bank_immutable ON question_bank")
    op.execute("DROP TRIGGER IF EXISTS assessment_blueprints_immutable ON assessment_blueprints")
    for fn in TRIGGER_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    _ddl(ORIGINAL_PRACTICE)
    _ddl(_profile_0008())

    # Role data goes first: its rows can't exist in the 0010 schema.
    op.execute("UPDATE bids SET assessment_evidence_id = NULL")
    op.execute("DELETE FROM skill_evidence WHERE source = 'ROLE_ASSESSMENT'")
    op.execute("DELETE FROM test_attempts WHERE kind = 'ROLE'")
    op.execute("DELETE FROM question_bank WHERE slug NOT LIKE '%-legacy-%' OR slug IS NULL AND false")

    op.drop_constraint(op.f("fk_bids_assessment_evidence_id_skill_evidence"), "bids", type_="foreignkey")
    op.drop_column("bids", "assessment_evidence_id")

    op.drop_index("ix_skill_evidence_user_blueprint", table_name="skill_evidence")
    op.drop_constraint(op.f("ck_skill_evidence_void_reason_len"), "skill_evidence", type_="check")
    op.drop_constraint(op.f("ck_skill_evidence_role_evidence_complete"), "skill_evidence", type_="check")
    op.drop_constraint(op.f("fk_skill_evidence_blueprint_id_assessment_blueprints"), "skill_evidence", type_="foreignkey")
    for column in ("void_reason", "voided_at", "valid_until", "passed", "blueprint_id"):
        op.drop_column("skill_evidence", column)

    op.drop_index("ix_test_attempts_flagged", table_name="test_attempts")
    op.drop_index("ix_test_attempts_blueprint_user", table_name="test_attempts")
    op.drop_index("ix_test_attempts_open_by_user", table_name="test_attempts")
    for name in ("extra_time_range", "focus_events_bounded", "counters_valid", "overall_range", "kind_target"):
        op.drop_constraint(op.f(f"ck_test_attempts_{name}"), "test_attempts", type_="check")
    op.drop_constraint(op.f("fk_test_attempts_admin_reviewed_by_users"), "test_attempts", type_="foreignkey")
    op.drop_constraint(op.f("fk_test_attempts_blueprint_id_assessment_blueprints"), "test_attempts", type_="foreignkey")
    op.alter_column("test_attempts", "test_id", existing_type=sa.UUID(), nullable=False)
    for column in (
        "admin_reviewed_by", "admin_reviewed_at", "reused_seen", "extra_time_seconds", "flagged",
        "passed", "overall_bp", "breakdown", "terminated_reason", "connection_gaps",
        "last_heartbeat_at", "last_focus_seq", "focus_events", "focus_leaves", "validity_days",
        "leave_limit", "rules_version", "consent_at", "retired_token_hashes",
        "attempt_token_hash", "answers_locked", "current_index", "context_slot_id",
        "context_project_id", "blueprint_id", "kind",
    ):  # fmt: skip
        op.drop_column("test_attempts", column)

    op.drop_table("user_accommodations")
    op.drop_index(op.f("ix_slot_assessments_project_id"), table_name="slot_assessments")
    op.drop_table("slot_assessments")
    op.drop_table("assessment_blueprints")

    for name in ("counters_valid", "human_approval_named", "approved_is_reviewed", "explanation_len", "snippet_len"):
        op.drop_constraint(op.f(f"ck_question_bank_{name}"), "question_bank", type_="check")
    op.drop_index("ix_question_bank_competency_status", table_name="question_bank")
    op.drop_constraint(op.f("uq_question_bank_slug"), "question_bank", type_="unique")
    op.drop_constraint(op.f("fk_question_bank_reviewed_by_user_users"), "question_bank", type_="foreignkey")
    op.drop_constraint(op.f("fk_question_bank_competency_id_competencies"), "question_bank", type_="foreignkey")
    for column in (
        "version", "times_served", "verification", "reviewed_at", "reviewed_by_user",
        "reviewed_by_name", "review_level", "explanation", "code_snippet", "source", "status",
        "competency_id", "slug",
    ):  # fmt: skip
        op.drop_column("question_bank", column)
    op.drop_table("competencies")
    for name in NEW_ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")

    # PostgreSQL can't drop an enum value: rebuild evidence_source without ROLE_ASSESSMENT (its
    # rows were deleted above).
    op.execute("ALTER TABLE skill_evidence ALTER COLUMN source TYPE text")
    op.execute("DROP TYPE evidence_source")
    op.execute("CREATE TYPE evidence_source AS ENUM ('TEST', 'CODING', 'ADMIN_PORTFOLIO')")
    op.execute(
        "ALTER TABLE skill_evidence ALTER COLUMN source TYPE evidence_source "
        "USING source::evidence_source"
    )
