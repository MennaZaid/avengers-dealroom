-- Manual permission checks for the source registry. Run against a seeded dev database:
--   docker compose exec -T db psql -U venture -d venture_os < tests/sql/registry_roles.sql
-- Each step prints what it expects; cleans up after itself.
\echo '1 validator adds provisional tier B (expect INSERT 0 1)'
SET ROLE vos_validator;
INSERT INTO sources(id,scope,source_name,url,tier,provisional,expires_at,created_by) VALUES ('P-1','country','Test stats','https://stats.gov.zz','B',true,now()+interval '30 days','validator');
\echo '2 validator tries tier A (expect row-level security violation)'
INSERT INTO sources(id,scope,source_name,tier,provisional,expires_at,created_by) VALUES ('P-2','country','x','A',true,now()+interval '30 days','validator');
\echo '3 validator tries non-provisional (expect violation)'
INSERT INTO sources(id,scope,source_name,tier,created_by) VALUES ('P-3','country','x','B','validator');
\echo '4 validator tries a 1-year expiry (expect violation)'
INSERT INTO sources(id,scope,source_name,tier,provisional,expires_at,created_by) VALUES ('P-4','country','x','B',true,now()+interval '365 days','validator');
\echo '5 validator tries to edit a source (expect permission denied)'
UPDATE sources SET tier='A' WHERE id='P-1';
RESET ROLE; SET ROLE vos_agent;
\echo '6 agent tries to add a source (expect permission denied)'
INSERT INTO sources(id,scope,source_name,tier,created_by) VALUES ('X','global','x','A','agent');
\echo '7 agent proposes a candidate (expect INSERT 0 1)'
INSERT INTO source_candidates(url,proposed_by) VALUES ('https://stats.gov.zz','run-1');
RESET ROLE; SET ROLE vos_admin;
\echo '8 admin confirms the provisional source (expect UPDATE 1)'
UPDATE sources SET provisional=false, expires_at=NULL, verified=true WHERE id='P-1';
\echo '9 admin tries to delete (expect permission denied)'
DELETE FROM sources WHERE id='P-1';
RESET ROLE;
DELETE FROM sources WHERE id='P-1';
DELETE FROM source_candidates WHERE proposed_by='run-1';
