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
- Can view **only activos perros in refugio** (no filters, no tabs, no location change)
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
- `estado`: EstadoPerro (activo, adoptado, fallecido)
- `ubicacion_id`: FK to current location — `TipoUbicacion`: refugio, acogida, residencia, **adoptado**
- `pesos`: one-to-many `PesoPerro` (ordered by fecha desc)
- `celos`: one-to-many `CeloPerro` (ordered by fecha_inicio desc)

### PesoPerro
- `perro_id`, `fecha`, `peso_kg` (Float), `notas` (nullable)
- CRUD via `POST /perros/{id}/peso` and `POST /perros/{id}/peso/{peso_id}/eliminar`
- Displayed in `perros/detail.html` as a collapsible section (hidden for veterano)

### CeloPerro
- `perro_id`, `fecha_inicio`, `fecha_fin` (nullable), `notas` (nullable)
- CRUD via `POST /perros/{id}/celo` and `POST /perros/{id}/celo/{celo_id}/eliminar`
- Displayed in `perros/detail.html` as a collapsible section (hidden for veterano)

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
    dashboard.py      — Dashboard stats, dbt run button (admin-only)
    perros.py         — CRUD perros, photo upload, location tabs
    voluntarios.py    — CRUD voluntarios
    turnos.py         — Turno registration, saldo calculation, KPIs
    visitas.py        — CRUD visitantes, pipeline estados, convertir a voluntario
    usuarios.py       — User management (admin-only)
  templates/
    base.html         — Sidebar, role-gated menu items
    login.html        — Login form (with logo)
    dashboard.html    — 5 stat cards + dbt status alert + run button
    perros/
      list.html       — Tabs: En refugio (heart) / En acogida (house) / Adoptados / Todos
      detail.html     — Photo (portrait-friendly), edit/delete/location change (hidden for veterano), control de pesos y celos
      form.html       — Create/edit, name uppercase, photo upload, age/passport
    voluntarios/
      list.html       — Active volunteers
      detail.html     — Profile + turnos (KPIs: time as volunteer, total turnos done)
      form.html       — Create/edit (label now says "Apellidos", not "Apellido")
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
    staging/          — stg_perros, stg_voluntarios, etc.
    marts/            — Business logic tables
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

**PostgreSQL enum change:** Cannot rename or add values with a simple UPDATE. Use `ALTER TYPE` DDL.

**dbt run timeout:** If it takes >180s, increase timeout in `dashboard.py:ejecutar_dbt()`.
