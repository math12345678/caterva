-- Migration: add parameter_provenance column to simulations
BEGIN;

ALTER TABLE "simulations"
  ADD COLUMN "parameter_provenance" jsonb DEFAULT NULL;

COMMIT;
