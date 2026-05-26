-- ChessLoop migration: consolidate public libraries under SEEDBOT_USER_ID
-- Run these in order, reviewing output at each step

-- ============================================================================
-- STEP 1: DIAGNOSTIC — Find orphan accounts that own public libraries
-- ============================================================================

-- Show all users who own public libraries (excluding seedbot and real admin/nick)
SELECT
    u.id,
    u.username,
    u.email,
    u.role,
    u.created_at,
    COUNT(l.id) as public_library_count,
    GROUP_CONCAT(l.name, ' | ') as library_names
FROM user u
LEFT JOIN library l ON u.id = l.owner_user_id AND l.is_public = TRUE
WHERE u.id != '00000000-0000-0000-0000-000000000001'  -- Exclude seedbot
  AND (
    -- Only show users who own public libraries
    u.id IN (SELECT DISTINCT owner_user_id FROM library WHERE is_public = TRUE)
  )
GROUP BY u.id
ORDER BY public_library_count DESC, u.created_at DESC;

-- ============================================================================
-- STEP 2: OPTIONAL — Check if these orphan accounts have ANY activity
-- ============================================================================

-- Check for any practice sessions, review logs, or stars/comments created by orphan accounts
-- (helps identify truly abandoned vs. active accounts)
SELECT
    u.id,
    u.username,
    COUNT(DISTINCT ps.id) as practice_sessions,
    COUNT(DISTINCT rl.id) as review_logs,
    COUNT(DISTINCT sig.id) as public_signals
FROM user u
LEFT JOIN practice_session ps ON u.id = ps.user_id
LEFT JOIN review_log rl ON u.id = rl.user_id
LEFT JOIN public_signal sig ON u.id = sig.user_id
WHERE u.id != '00000000-0000-0000-0000-000000000001'  -- Exclude seedbot
  AND u.id IN (SELECT DISTINCT owner_user_id FROM library WHERE is_public = TRUE)
GROUP BY u.id
ORDER BY u.created_at DESC;

-- ============================================================================
-- STEP 3: MIGRATION — Reassign all public libraries to SEEDBOT_USER_ID
-- ============================================================================

-- IMPORTANT: Review steps 1 & 2 first to confirm which accounts to migrate
-- Then uncomment and run only the accounts you want to migrate

-- Migrate a SPECIFIC orphan account (replace {USER_ID} with the actual UUID)
-- UPDATE library
-- SET owner_user_id = '00000000-0000-0000-0000-000000000001'
-- WHERE is_public = TRUE
--   AND owner_user_id = '{USER_ID}';

-- OR: Migrate ALL orphan accounts at once (only if you've reviewed step 1 & 2)
UPDATE library
SET owner_user_id = '00000000-0000-0000-0000-000000000001'
WHERE is_public = TRUE
  AND owner_user_id NOT IN (
    -- Keep these accounts as-is (add real admin/nick usernames as needed)
    SELECT id FROM user WHERE username IN ('seedbot', 'admin', 'nick')
  )
  AND owner_user_id != '00000000-0000-0000-0000-000000000001';

-- Verify the migration worked
SELECT COUNT(*) as migrated_libraries FROM library WHERE is_public = TRUE AND owner_user_id = '00000000-0000-0000-0000-000000000001';

-- ============================================================================
-- STEP 4: CLEANUP — Delete orphan user accounts (only if step 3 confirmed)
-- ============================================================================

-- IMPORTANT: Only delete after confirming step 3 worked
-- First, list the accounts to be deleted:
SELECT
    u.id,
    u.username,
    u.email,
    u.created_at,
    COUNT(l.id) as remaining_libraries
FROM user u
LEFT JOIN library l ON u.id = l.owner_user_id
WHERE u.id IN (
    -- Find accounts that now have NO libraries (orphans after migration)
    SELECT u2.id FROM user u2
    WHERE NOT EXISTS (SELECT 1 FROM library WHERE owner_user_id = u2.id)
      AND u2.id != '00000000-0000-0000-0000-000000000001'
      AND u2.username NOT IN ('seedbot', 'admin', 'nick')  -- Protect real accounts
)
GROUP BY u.id;

-- Delete orphan accounts (no libraries, no other activity)
-- CAREFUL: Only run this after reviewing the list above
-- DELETE FROM user
-- WHERE id IN (
--     SELECT u.id FROM user u
--     WHERE NOT EXISTS (SELECT 1 FROM library WHERE owner_user_id = u.id)
--       AND u.id != '00000000-0000-0000-0000-000000000001'
--       AND u.username NOT IN ('seedbot', 'admin', 'nick')
-- );

-- ============================================================================
-- STEP 5: VERIFY — Check final state
-- ============================================================================

-- Count public libraries by owner
SELECT
    u.username,
    u.email,
    COUNT(l.id) as public_library_count
FROM user u
JOIN library l ON u.id = l.owner_user_id
WHERE l.is_public = TRUE
GROUP BY u.id
ORDER BY public_library_count DESC;

-- List all remaining user accounts
SELECT id, username, email, role, created_at
FROM user
ORDER BY created_at DESC;
