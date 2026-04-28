-- Crear raza si no existe
INSERT INTO razas (nombre) SELECT 'Pastor Belga Malinois' WHERE NOT EXISTS (SELECT 1 FROM razas WHERE nombre = 'Pastor Belga Malinois');

-- BALU
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'BALU', id, 'macho', false, false, '941010000314480', 'ES081060973', 'Barcino', '2020-10-13', '2026-03-27', 'activo'
FROM razas WHERE nombre = 'Galgo Español'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'refugio', '2026-03-27' FROM perros WHERE num_chip = '941010000314480'
ON CONFLICT DO NOTHING;

-- TOTO
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'TOTO', id, 'macho', false, false, '941000032543225', 'ES081321426', 'Marrón y negro', '2026-01-15', '2026-04-19', 'activo'
FROM razas WHERE nombre = 'Pastor Belga Malinois'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'acogida', '2026-04-19' FROM perros WHERE num_chip = '941000032543225'
ON CONFLICT DO NOTHING;

-- CATANA
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'CATANA', id, 'hembra', false, true, '941000031099004', 'ES0811293277', 'Marrón blanca', '2025-04-05', '2026-04-28', 'activo'
FROM razas WHERE nombre = 'American Staffordshire'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'refugio', '2026-04-28' FROM perros WHERE num_chip = '941000031099004'
ON CONFLICT DO NOTHING;

-- CHISPA
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'CHISPA', id, 'macho', false, false, '941010000642395', 'ES081143385', 'Atigrada', '2022-07-21', '2026-04-28', 'activo'
FROM razas WHERE nombre = 'Galgo Español'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'refugio', '2026-04-28' FROM perros WHERE num_chip = '941010000642395'
ON CONFLICT DO NOTHING;

-- OBI
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'OBI', id, 'macho', true, false, '941000017921967', 'ES080616050', 'Gris blanca', '2014-11-01', '2014-11-12', 'activo'
FROM razas WHERE nombre = 'Mestizo'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'residencia', '2014-11-12' FROM perros WHERE num_chip = '941000017921967'
ON CONFLICT DO NOTHING;

-- SPOTTER
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'SPOTTER', id, 'macho', true, false, '941000023583040', 'ES080896268', 'Marrón', '2018-12-03', '2026-04-28', 'activo'
FROM razas WHERE nombre = 'Pastor Alemán'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'refugio', '2026-04-28' FROM perros WHERE num_chip = '941000023583040'
ON CONFLICT DO NOTHING;

-- PONGO
INSERT INTO perros (nombre, raza_id, sexo, esterilizado, ppp, num_chip, num_pasaporte, color, fecha_nacimiento, fecha_entrada, estado)
SELECT 'PONGO', id, 'macho', true, false, '941000016585335', 'ES080547064', 'Blanco y negro', '2014-03-04', '2026-03-20', 'activo'
FROM razas WHERE nombre = 'Dálmata'
ON CONFLICT (num_chip) DO NOTHING;
INSERT INTO ubicaciones (perro_id, tipo, fecha_inicio)
SELECT id, 'acogida', '2026-03-20' FROM perros WHERE num_chip = '941000016585335'
ON CONFLICT DO NOTHING;
