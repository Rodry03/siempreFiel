-- Migration: Add saldo_manual field to voluntarios table
-- Description: Allow manual override of calculated saldo

ALTER TABLE voluntarios 
ADD COLUMN IF NOT EXISTS saldo_manual FLOAT NULL;
