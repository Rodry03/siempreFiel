# Claude Code Instructions — Siempre Fiel

App de gestión de la protectora de perros. FastAPI + Jinja2 + PostgreSQL + dbt.

## Quick Start

```bash
venv\Scripts\activate
uvicorn app.main:app --reload
```

**Neon DB:** App local y Render usan la misma Neon DB (producción y desarrollo apuntan al mismo sitio).

**dbt run** (desde `dbt_protectora/`):
```bash
$env:DBT_PASSWORD="rodrymolamucho"; dbt run
```

---

## Stack

- **Backend:** FastAPI + Jinja2 + Bootstrap 5
- **DB:** PostgreSQL (Neon), base `protectora`, usuario `postgres`
- **ORM:** SQLAlchemy
- **Analytics:** dbt-postgres
- **Image upload:** Cloudinary (URL-only, stored in `Perro.foto_url`)
- **Deployment:** Render

---

## System: Roles & Permissions

**Three-tier role system** (`app/models.py`: `RolUsuario` enum):

### Admin
- Full access: CRUD usuarios, voluntarios, perros, turnos, visitas
- Can run dbt from dashboard button
- Default role when creating users: **junta**

### Junta (formerly "editor")
- Everything **except** create/edit/delete users
- Full access to perros, voluntarios, turnos, visitas
- Can see all dashboard data and analytics
- Cannot run dbt

### Veterano (read-only + own profile)
- Can view **only perros in refugio with estado=activos** (no filters, no tabs, no location change)
- Can view **own volunteer profile** only (profile + turnos)
- Cannot: register turnos, edit profile, change perfil, see other profiles
- **Redirect target on auth fail:** `/perros/` (not `/`), avoids infinite loop
- Associated with a `Usuario.voluntario_id` (can be null for admin/junta)

**Access control:**
- Router-level: `dependencies=[Depends(get_current_user), Depends(require_not_veterano)]`
- Route-level: `dependencies=[Depends(require_not_veterano)]` or `dependencies=[Depends(require_admin)]`
- Template-level: `{% set es_veterano = ... %}` to hide UI

---

## Key Models & Concepts

### Perro
- `nombre`: always saved in **UPPERCASE** (enforced in create/edit endpoints)
- `edad`: calculated (not stored) from `fecha_nacimiento`
- `num_chip`: microchip number (unique, nullable)
- `num_pasaporte`: passport number (unique, nullable)
- `ppp`: boolean (perro potencialmente peligroso)
- `foto_url`: Cloudinary URL (nullable)
- `fecha_adopcion`: date when adopted (nullable). Set automatically when ubicación changes to `casa_adoptiva` or estado set to `adoptado`.
- `fecha_reserva`: date when estado changed to `reservado` (nullable). Set in `crear_perro`/`editar_perro`, cleared when leaving `reservado`. Used for auto-adoption after 30 days.
- `estado`: `EstadoPerro` — **libre** (bajo gestión, nadie interesado), **reservado**, **adoptado**, **fallecido**
  - "activo" (bajo gestión) se deriva: `estado in ('libre', 'reservado')`
  - Cambiar ubicación ↔ estado están sincronizados bidireccionalmente (ver lógica abajo)
- `ubicaciones`: historial de ubicaciones físicas — `TipoUbicacion`: **refugio**, **acogida**, **residencia**, **casa_adoptiva**
  - `reservado` y `adoptado` fueron eliminados de `TipoUbicacion` (eran estados disfrazados de ubicación)
- `pesos`: one-to-many `PesoPerro` (ordered by fecha desc)
- `celos`: one-to-many `CeloPerro` (ordered by fecha_inicio desc)

### Auto-adopción de reservados
- `_auto_adoptar_reservados(db)` en `perros.py`: se llama al cargar `/perros/` (solo junta/admin)
- Perros con `estado=reservado` y `fecha_reserva <= hoy - 30 días` pasan automáticamente a `adoptado`, se les pone `fecha_adopcion=hoy` y se crea ubicación `casa_adoptiva`
- Perros sin `fecha_reserva` (anteriores a esta feature) no se tocan

### Vacuna
- `tipo`: String libre, pero el frontend usa `TIPOS_VACUNA` (lista en `perros.py`) como desplegable
- `fecha_proxima`: se auto-calcula como `fecha_administracion + 1 año` (JS en detail.html + fallback en servidor)
- CRUD: `POST /perros/{id}/vacuna`, `POST /perros/{id}/vacuna/{id}/editar`, `POST /perros/{id}/vacuna/{id}/eliminar`
- Tipos habituales en la protectora: Rabia, Canigen, DPT (Difteria/Pertussis/Tétanos)

### Sincronización estado ↔ ubicación
- Cambiar ubicación a `casa_adoptiva` → `estado = adoptado`, `fecha_adopcion` se guarda si no había
- Cambiar ubicación a física (refugio/acogida/residencia) estando adoptado → `estado = libre`
- Guardar formulario con `estado = adoptado` y ubicación actual ≠ `casa_adoptiva` → se crea automáticamente registro `casa_adoptiva` (sin datos de contacto, rellenar después)
- Guardar formulario con `estado ≠ adoptado` viniendo de adoptado con `casa_adoptiva` → se cierra `casa_adoptiva` y se crea `refugio`

### PesoPerro
- `perro_id`, `fecha`, `peso_kg` (Float), `notas` (nullable)
- CRUD via `POST /perros/{id}/peso` and `POST /perros/{id}/peso/{peso_id}/eliminar`
- Displayed in `perros/detail.html` as a collapsible section (hidden for veterano)
- Columna "Peso" visible en `list.html`, ordenable (subquery del último peso por perro)

### CeloPerro
- `perro_id`, `fecha_inicio`, `fecha_fin` (nullable), `notas` (nullable)
- CRUD via `POST /perros/{id}/celo` and `POST /perros/{id}/celo/{celo_id}/eliminar`
- Displayed in `perros/detail.html` as a collapsible section (hidden for veterano)
- `fecha_fin` se precarga con `fecha_inicio + 15 días` por defecto (JS en detail.html)

### Voluntario
- `perfil`: PerfilVoluntario enum
  - **Hacen turnos:** veterano, voluntario
  - **No hacen turnos:** directiva, guagua, eventos, colaboradores
- `ppp`: boolean (permiso PPP)
- `dni`, `email`, `telefono`, `direccion`, `provincia`, `codigo_postal`
- `fecha_contrato`, `contrato_estado`: EstadoContrato (pendiente, enviado, firmado)
- `teaming`: boolean
- `activo`: boolean
- Turnos: one-to-many `TurnoVoluntario`

### Visitante
Pipeline de adopción/acogida. `EstadoVisitante`: interesado → visita_programada → visita_realizada → se_convirtio / descartado
- Auto-transición: si se fija `fecha_visita` y ya pasó, el estado pasa a `visita_realizada`
- Acción **convertir a voluntario**: marca al visitante como `se_convirtio` y redirige a `/voluntarios/nuevo` con nombre/apellido/email/teléfono prefilled

### TurnoVoluntario
- `fecha`, `franja` (manana/tarde), `estado` (realizado, medio_turno, falta_justificada, falta_injustificada, no_apuntado)
- **Saldo calculation** (`app/routers/turnos.py: calcular_saldo`):
  - Fecha inicio: `max(2026-04-01, fecha_alta_voluntario)`
  - Semanas activas: `(today - fecha_inicio).days // 7`
  - Turnos acumulados: sum estado valores (realizado=1.0, medio_turno=0.5, others=0)
  - **Saldo = turnos_acumulados - semanas_activos**

---

## Cloudinary Image Upload

**Important:** `cloudinary.config()` must be called **inside** the upload function, not at import time (env var timing issue).

```python
def _subir_foto(file: UploadFile, perro_id: int) -> Optional[str]:
    if not file or not file.filename:
        return None
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )
    contents = file.file.read()
    result = cloudinary.uploader.upload(
        contents, folder="protectora", public_id=f"perro_{perro_id}", 
        overwrite=True, transformation=[{"width": 800, "crop": "limit"}]
    )
    return result["secure_url"]
```

**Thumbnail transformation:** `.replace('/upload/', '/upload/c_fill,w_72,h_72/')`

---

## Project Structure

```
app/
  models.py           — SQLAlchemy models (Perro, Voluntario, TurnoVoluntario, etc.)
  auth.py             — get_current_user, require_not_veterano, require_admin
  database.py         — Session factory
  templates_config.py — Jinja2 setup
  main.py             — FastAPI app, NotAuthorized redirect to /perros/
  routers/
    dashboard.py      — Dashboard stats, dbt run button (admin-only), GET /dashboard/detalle-mes, GET /dashboard/detalle-conversion (drill-down charts)
    perros.py         — CRUD perros, photo upload, location tabs, sync estado↔ubicación, auto-adopción reservados, CRUD vacunas
    voluntarios.py    — CRUD voluntarios
    turnos.py         — Detalle voluntario + registro/eliminación de turnos desde perfil. Prefix: /voluntarios
    turnos_admin.py   — Gestión centralizada de turnos (junta/admin). Prefix: /turnos. CRUD + filtros semana/voluntario/estado
    visitas.py        — CRUD visitantes, pipeline estados, convertir a voluntario
    usuarios.py       — User management (admin-only)
  templates/
    base.html         — Sidebar desktop + offcanvas móvil. Colores marca verde #31ae90→#1d8a6e. Nunito en headings. Fondo #eef4f2
    login.html        — Login form (with logo). Fondo gradiente verde marca
    dashboard.html    — Stat cards + charts + dbt button. Drill-down en entradas/adopciones y conversión visitantes. Gráficos: entradas/salidas, conversión visitantes, cobertura semanal, evolución saldo, tiempo adopción, tiempo acogida.
    perros/
      list.html       — Tabs: En refugio / En acogida / Reservados / Adoptados / Todos. 35 por página. Contador. Ordenación preservada al paginar.
      detail.html     — Photo, edit/delete, pesos, celos, vacunas (select tipo, auto fecha_proxima, editar/borrar). Ubicaciones: cambio + edición individual. Botón atrás usa history.back().
      form.html       — Create/edit, name uppercase, photo upload, fecha_adopcion (visible si estado=adoptado)
    voluntarios/
      list.html       — Active volunteers
      detail.html     — Profile + turnos históricos (solo lectura; edición en /turnos/)
      form.html       — Create/edit (label now says "Apellidos", not "Apellido")
    turnos/
      list.html       — Vista semanal con nav ◀▶, filtros voluntario/estado, modal editar, modal añadir, eliminar
    visitas/
      list.html       — Filtros por estado, tabla con color por estado
      detail.html     — Detalle visitante + botón convertir a voluntario
      form.html       — Create/edit visitante
    usuarios/
      list.html       — Lista de usuarios con rol y estado
      form.html       — Create/edit, rol selector, volunteer dropdown (toggleVol JS)

dbt_protectora/
  profiles.yml        — Default target: prod (points to Neon)
  models/
    staging/          — stg_perros (estado in libre/reservado), stg_voluntarios, etc.
    marts/            — Business logic tables
      mart_entradas_salidas_por_mes  — usa perros.fecha_adopcion (no ubicaciones.tipo='adoptado')
      mart_tiempo_adopcion           — usa perros.fecha_adopcion
      mart_patrones_dificultad       — usa perros.fecha_adopcion
      mart_perros_sin_adoptar        — filtra estado='libre'
      mart_vacunas_proximas          — materializado como VIEW (tiempo real, no tabla)
      mart_perros_no_esterilizados   — materializado como VIEW (tiempo real, no tabla)
      mart_tiempo_acogida_mes        — días medios en acogida por mes
      mart_conversion_visitantes     — tasa conversión visitante→voluntario por mes
      mart_evolucion_saldo_semanal   — saldo medio de turnos semana a semana
```

---

## Common Tasks

### Add a Raza
```sql
INSERT INTO razas (nombre) VALUES ('Nueva Raza');
```

### DB Role Migration
```sql
ALTER TYPE nombre_enum RENAME VALUE 'old' TO 'new';
ALTER TYPE nombre_enum ADD VALUE 'new_value';
```

### Run dbt
```bash
cd dbt_protectora
$env:DBT_PASSWORD="rodrymolamucho"; dbt run
```

### Deploy to Render
GitHub Actions runs on push to `main`. Render pulls and restarts.

---

## Design Decisions

1. **Single DB (Neon):** Both local and Render point to the same DB. No migration needed.
2. **Photo storage:** Cloudinary URLs only (not bytes in DB). Avoids DB bloat.
3. **Veterano read-only:** Role restricted at route, template, and query levels.
4. **Synchronous dbt run:** `subprocess.run()` with 180s timeout. May block UI for 20–30s. Acceptable.
5. **Name uppercase:** Enforced in create/edit endpoints (`nombre = nombre.upper()`).
6. **Portrait photos:** `max-height: 300px; object-fit: contain; margin: 0 auto;`
7. **Photo display for veterano:** Can view photos but cannot change location or upload new ones.
8. **Estado vs ubicación separados:** `estado` = interés/adopción (libre/reservado/adoptado/fallecido). `TipoUbicacion` = lugar físico (refugio/acogida/residencia/casa_adoptiva). "Activo" se deriva de `estado in ('libre', 'reservado')`. Sincronización bidireccional automática entre estado y ubicación.
9. **fecha_adopcion en Perro:** Fecha de adopción guardada directamente en `perros.fecha_adopcion` (no en ubicaciones). Permite que los perros devueltos sigan en el sistema. Los marts dbt la usan para analytics de adopciones.
10. **Tabs de ubicación física usan estado=activos:** Las pestañas "En refugio" y "En acogida" muestran tanto `libre` como `reservado` para reflejar la ubicación real del perro independientemente de su estado de interés.
11. **Edición de ubicaciones individuales:** `POST /perros/{id}/ubicacion/{ubicacion_id}/editar` permite corregir fecha_inicio, tipo, contacto, etc. de cualquier registro del historial. Sincroniza estado del perro si la ubicación editada es la activa (sin fecha_fin).
12. **Turnos admin separado de perfil voluntario:** `/turnos/` (junta/admin) para CRUD centralizado con filtros. El perfil del voluntario solo muestra el historial.
13. **Color de marca:** `#31ae90` (verde protectora). Sidebar, login y fondo de página usan esta paleta.
14. **dbt materialización mixta:** Marts de datos históricos = `table`. Marts que deben reflejar estado actual en tiempo real (`mart_vacunas_proximas`, `mart_perros_no_esterilizados`) = `view` con `{{ config(materialized='view') }}`.
15. **Auto-adopción reservados:** Se dispara en cada carga de `/perros/` (no en background). Requiere `fecha_reserva` en el perro; perros sin ese campo no se procesan.
16. **Drill-down charts:** Entradas/adopciones → `/dashboard/detalle-mes?mes=&tipo=`. Conversión visitantes → `/dashboard/detalle-conversion?mes=&tipo=`. La línea de tasa (%) no tiene drill-down.
17. **dbt run logging:** Errores se loguean con `logging.getLogger(__name__)` en `dashboard.py` y las últimas 20 líneas del output se muestran en flash al admin.
18. **Botón atrás en detalle perro:** Usa `history.back()` para respetar filtros activos (tab adoptados, acogida, etc.). Fallback a `/perros/` si JS desactivado.

---

## User Preferences

- **Terse responses:** No trailing summaries unless asked.
- **Naming:** "Apellidos" (plural), not "Apellido".
- **Git workflow:** New commits, not amends. No force push to main.
- **File reading:** Always read before editing.
- **Memory:** Specific details about user preferences and project decisions are saved in `memory/` directory.

---

## Troubleshooting

**Veterano infinite redirect loop:** Fixed by redirecting `NotAuthorized` to `/perros/` (not `/`).

**Cloudinary config empty:** Move `cloudinary.config()` inside the upload function so it reads env vars at request time, not import time.

**PostgreSQL enum change:** Cannot rename or add values with a simple UPDATE. Use `ALTER TYPE` DDL. Cannot DROP enum values — recreate type if needed.

**dbt run timeout:** If it takes >180s, increase timeout in `dashboard.py:ejecutar_dbt()`.

**Adopciones en drill-down no cargaban:** El filtro usaba `TipoUbicacion.adoptado` que ya no existe. Corregido a `Perro.fecha_adopcion` (consistente con los marts).

**Vacunas con fecha_proxima vacía (datos históricos):** Corregido con `UPDATE vacunas SET fecha_proxima = fecha_administracion + INTERVAL '1 year' WHERE fecha_proxima IS NULL`.

**Badge invisible (mismo color que fondo):** Añadir `.badge-{tipo}` en `base.html` con el color correspondiente.
