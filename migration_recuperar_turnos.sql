-- Migration: Add recuperar_turnos_urgentes field to voluntarios table
-- Description: Add a field to track urgent turns to recover for each volunteer

ALTER TABLE voluntarios 
ADD COLUMN IF NOT EXISTS recuperar_turnos_urgentes INTEGER NOT NULL DEFAULT 0;
