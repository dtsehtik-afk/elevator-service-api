-- Clear operational data while keeping technicians, buildings, management companies, contacts
-- Run with: docker exec -i elevator-service-api-db-1 psql -U postgres -d elevator_service

BEGIN;

-- Inspection data
DELETE FROM inspection_reports;
DELETE FROM inspection_email_scans;

-- Service calls (children first due to FK constraints)
DELETE FROM audit_logs;
DELETE FROM assignments;
DELETE FROM service_calls;

-- Incoming calls
DELETE FROM incoming_call_logs;

-- Elevators (children first)
DELETE FROM maintenance_schedules;
DELETE FROM elevators;

COMMIT;

SELECT 'Done — elevators, calls, inspections cleared. Technicians and buildings preserved.' AS status;
