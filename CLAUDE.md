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
# prod (Neon) — target por defecto
$env:DBT_NEON_HOST="<host>"; $env:DBT_NEON_USER="<user>"; $env:DBT_NEON_PASSWORD="<pass>"; $env:DBT_NEON_DBNAME="<db>"; dbt run

# dev (PostgreSQL local)
$env:DBT_PASSWORD="rodrymolamucho"; dbt run --target dev

# solo un modelo
$env:DBT_NEON_...; dbt run --select mart_cobertura_semanal
```

---

## Stack

- **Backend:** FastAPI + Jinja2 + Bootstrap 5
- **DB:** PostgreSQL (Neon), base `protectora`, usuario `postgres`
- **ORM:** SQLAlchemy
- **Analytics:** dbt-postgres
- **Image upload:** Cloudinary (URL-only, stored in `Perro.foto_url`)
- **AI assistant:** Groq (llama-3.3-70b-versatile) — Text-to-SQL, solo lectura
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
- Can view **own volunteer profile** only (profile + turnos + medicación perros)
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
- `medicaciones`: one-to-many `MedicacionPerro` (ordered by fecha_inicio desc) — **visible a todos los roles**

### Auto-adopción de reservados
- `_auto_adoptar_reservados(db)` en `perros.py`: se llama al cargar `/perros/` (solo junta/admin)
- Perros con `estado=reservado` y `fecha_reserva <= hoy - 30 días` pasan automáticamente a `adoptado`, se les pone `fecha_adopcion=hoy` y se crea ubicación `casa_adoptiva`
- Perros sin `fecha_reserva` (anteriores a esta feature) no se tocan

### Vacuna
- `tipo`: String libre, pero el frontend usa `TIPOS_VACUNA` (lista en `perros.py`) como desplegable
- `fecha_proxima`: se auto-calcula como `fecha_administracion + 1 año` (JS en detail.html + fallback en servidor)
- CRUD: `POST /perros/{id}/vacuna`, `POST /perros/{id}/vacuna/{id}/editar`, `POST /perros/{id}/vacuna/{id}/eliminar`
- Tipos habituales en la protectora: Rabia, Canigen, DPT (Difteria/Pertussis/Tétanos)
- **Oculto para veteranos**

### MedicacionPerro
- `perro_id`, `medicamento`, `dosis` (nullable), `frecuencia` (nullable), `turno` (nullable String, comma-separated: `'manana'`, `'tarde'`, `'manana,tarde'`), `fecha_inicio`, `fecha_fin` (nullable = en curso), `notas` (nullable)
- CRUD: `POST /perros/{id}/medicacion`, `POST /perros/{id}/medicacion/{id}/editar`, `POST /perros/{id}/medicacion/{id}/eliminar` (solo junta/admin)
- **Visible para todos los roles** (incluido veterano), edición solo junta/admin
- Medicaciones con `fecha_fin IS NULL OR fecha_fin >= hoy` se muestran en verde como "En curso"
- `turno`: checkboxes múltiples en el formulario; se guarda como string separado por coma. Badges: Mañana (amarillo), Tarde (azul)

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
  - **Hacen turnos:** veterano, apoyo_en_junta, voluntario
  - **No hacen turnos:** directiva, guagua, eventos, colaboradores
  - `apoyo_en_junta`: voluntario que actúa como veterano de apoyo; **cuenta como veterano** para cobertura y regla de medio_turno
- `fecha_veterano`: fecha desde la que el voluntario es veterano (nullable)
- `fecha_fin_veterano`: fecha en que el voluntario dejó de ser veterano ("baja de nivel") (nullable). Al rellenarse en el formulario, el perfil se fuerza automáticamente a `voluntario`.
- `ppp`: boolean (permiso PPP)
- `dni`, `email`, `telefono`, `direccion`, `provincia`, `codigo_postal`
- `fecha_contrato`, `contrato_estado`: EstadoContrato (pendiente, enviado, firmado)
- `teaming`: boolean
- `activo`: boolean
- Turnos: one-to-many `TurnoVoluntario`
- Periodos de apoyo: one-to-many `PeriodoApoyo` (`fecha_inicio`, `fecha_fin` nullable). Las semanas cubiertas por un periodo de apoyo se neutralizan en el saldo (no suman ni restan).

### Visitante
Pipeline de adopción/acogida. `EstadoVisitante`: interesado → visita_programada → visita_realizada → se_convirtio / descartado
- Auto-transición: si se fija `fecha_visita` y ya pasó, el estado pasa a `visita_realizada`
- Acción **convertir a voluntario**: marca al visitante como `se_convirtio` y redirige a `/voluntarios/nuevo` con nombre/apellido/email/teléfono prefilled

### TurnoVoluntario
- `fecha`, `franja` (manana/tarde), `estado` (realizado, medio_turno, falta_justificada, falta_injustificada, no_apuntado)
- **Saldo in-app** (`app/routers/turnos.py: calcular_saldo`):
  - Fecha inicio: `max(2025-08-04, fecha_veterano or fecha_alta)`
  - Fórmula por semana completada: `sum(valores_turnos) - 1.0` donde realizado=1.0, medio_turno=0.5, resto=0. Solo cuentan `realizado` y `medio_turno`.
  - Ejemplos: 0 turnos=−1, 1 turno=0, 2 turnos=+1, 1 medio_turno=−0.5. En PeriodoApoyo=0.
  - Semana actual (incompleta) no se procesa.
  - **Saldo = suma de contribuciones semanales**
- **Saldo dbt** (`mart_saldo_turnos_semanal`): usa `COALESCE(fecha_veterano, fecha_alta)` como inicio; misma fórmula `valor - 1.0` por semana; semanas con `PeriodoApoyo` = 0; semana actual (`semana >= date_trunc('week', current_date)`) = 0 (no penaliza).
- **Historial en perfil:** muestra todas las semanas desde 04/08/2025 (o `fecha_alta` si es posterior). Columna "Saldo" muestra contribución semanal (+1, 0, −1, ±0.5). Semanas sin turno → fila roja, −1. Semanas en PeriodoApoyo → badge azul, sin penalización. Semana actual → badge "Esta semana", sin −1.
- **Saldo en lista de voluntarios:** columna con badge verde/rojo/gris calculado con `calcular_saldo`.
- **Regla auto medio_turno:** si hay 2+ voluntarios con perfil `veterano` o `apoyo_en_junta` **que eran veteranos en esa fecha** (fecha_veterano ≤ fecha ≤ fecha_fin_veterano, o perfil apoyo_en_junta) en el mismo hueco con estado `realizado`, todos pasan a `medio_turno`. Se aplica en `turnos_admin.py: anadir_turno` y al insertar estadillo.

### Evento
- `titulo`, `fecha`, `hora_inicio`/`hora_fin` (String HH:MM, nullable), `ubicacion` (nullable), `tipo` (Text, comma-separated, nullable), `notas` (nullable)
- `participantes`: one-to-many `EventoVoluntario` (UniqueConstraint evento_id+voluntario_id)
- CRUD en `app/routers/eventos.py` (prefix `/eventos/`), visible para junta/admin
- Tipos libres seleccionables con checkboxes múltiples; se almacenan como texto separado por comas

### EventoVoluntario
- `evento_id`, `voluntario_id`, `hora_llegada` (String HH:MM, nullable), `hora_salida` (String HH:MM, nullable)
- `POST /eventos/{id}/voluntario/{vid}/horario` guarda hora_llegada y hora_salida (junta/admin)
- La duración se calcula en el router (`_duracion()`) y se pasa al template como dict `{ep.id: "Xh YYm"}`
- En detail.html: junta/admin ven inputs time editables + badge verde con duración; veteranos ven solo lectura

### MovimientoEconomico
- `tipo`: TipoMovimiento enum — **ingreso**, **gasto**, **deuda**
- `concepto` (String), `categoria` (String libre, nullable), `importe` (Float), `fecha`, `pagado` (Boolean, para deudas), `notas` (nullable)
- CRUD en `app/routers/economia.py` (prefix `/economia/`), **solo junta/admin** (oculto a veteranos)
- Vista: tarjetas resumen (total ingresos, total gastos, balance, deuda pendiente) + tabla con filtro por tipo
- Deudas: botón toggle para marcar como pagada/pendiente (`POST /economia/{id}/marcar-pagado`)

### Familia
- Representa familias adoptantes o acogedoras de perros.
- Campos obligatorios: `nombre`, `apellidos`, `dni` (unique, guardado en mayúsculas)
- `tipo`: String nullable — `'adopcion'` | `'acogida'`
- `perro_id`: FK nullable a `perros.id`
- Campos opcionales: `email`, `telefono`, `direccion`, `municipio`, `provincia`, `codigo_postal`, `notas`
- `fecha_contrato`: Date (obligatoria, default hoy) — fecha de firma del contrato
- `contrato_firmado_url`, `contrato_firmado_fecha`, `contrato_firmado_nombre`: upload del contrato firmado a Cloudinary (`protectora/contratos/contrato_familia_{id}`, resource_type=raw)
- CRUD en `app/routers/familias.py` (prefix `/familias/`), **solo junta/admin** (oculto a veteranos)
- Detalle: dos botones deshabilitados para generar contrato adopción/acogida (pendiente recibir plantillas Word); tarjeta upload contrato firmado igual que voluntarios
- Sidebar: entre Visitas y Turnos

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
  models.py           — SQLAlchemy models (Perro, Voluntario, TurnoVoluntario, MedicacionPerro, MovimientoEconomico, Evento, EventoVoluntario, etc.)
  auth.py             — get_current_user, require_not_veterano, require_admin
  database.py         — Session factory
  templates_config.py — Jinja2 setup
  main.py             — FastAPI app, NotAuthorized redirect to /perros/
  estadillo_parser.py — Parser del estadillo semanal (texto → turnos). (T.C.) se ignora; otras anotaciones entre paréntesis en veterano → medio_turno; "Visita" se omite.
  routers/
    dashboard.py      — Dashboard stats, dbt run button (admin-only), GET /dashboard/detalle-mes, GET /dashboard/detalle-conversion (drill-down charts)
    perros.py         — CRUD perros, photo upload, location tabs, sync estado↔ubicación, auto-adopción reservados, CRUD vacunas, CRUD medicaciones
    voluntarios.py    — CRUD voluntarios (fecha_fin_veterano → auto-set perfil a voluntario)
    turnos.py         — Detalle voluntario + historial de turnos (desde 04/08/2025, semanas vacías como -1). Prefix: /voluntarios
    turnos_admin.py   — Gestión centralizada de turnos (junta/admin). Prefix: /turnos. CRUD + filtros semana/perfil. POST /limpiar-semana (admin). POST /dbt-run-model.
    visitas.py        — CRUD visitantes, pipeline estados, convertir a voluntario
    usuarios.py       — User management (admin-only)
    eventos.py        — CRUD eventos + asignación de voluntarios. Prefix: /eventos/
    economia.py       — CRUD movimientos económicos (ingreso/gasto/deuda). Prefix: /economia/
    familias.py       — CRUD familias adoptantes/acogedoras + upload contrato firmado (Cloudinary). Prefix: /familias/
    consulta.py       — Asistente AntonIA: Text-to-SQL con Groq. GET /consulta/ (UI chat), POST /consulta/preguntar (AJAX). Solo junta/admin. Requiere GROQ_API_KEY.
  templates/
    base.html         — Sidebar desktop + offcanvas móvil. Colores marca verde #31ae90→#1d8a6e. Nunito en headings. Fondo #eef4f2
    login.html        — Login form (with logo). Fondo gradiente verde marca
    dashboard.html    — Stat cards + charts + dbt button. Drill-down en entradas/adopciones y conversión visitantes. Gráficos: entradas/salidas, conversión visitantes, cobertura semanal (20 semanas), evolución saldo (20 semanas), tiempo adopción, tiempo acogida.
    perros/
      list.html       — Tabs: En refugio / En acogida / Reservados / Adoptados / Todos. 35 por página. Contador. Ordenación preservada al paginar.
      detail.html     — Photo, edit/delete, pesos, celos, medicaciones (visible a todos), vacunas (ocultas a veterano). Ubicaciones: cambio + edición individual. Botón atrás usa history.back().
      form.html       — Create/edit, name uppercase, photo upload, fecha_adopcion (visible si estado=adoptado)
    voluntarios/
      list.html       — Active volunteers
      detail.html     — Profile + historial turnos (desde 04/08/2025, semanas vacías en rojo con -1, apoyo en azul)
      form.html       — Create/edit. fecha_veterano + fecha_fin_veterano (rellenar fin → fuerza perfil a voluntario)
    turnos/
      list.html       — Vista semanal con nav ◀▶, filtro por perfil, modal añadir, eliminar. Botón "Limpiar semana" (admin). Saldo en float (1 decimal).
      estadillo_form.html    — Pegar texto estadillo
      estadillo_preview.html — Previsualizar antes de insertar; muestra ½ para medio_turno detectado por anotación
    visitas/
      list.html       — Filtros por estado, tabla con color por estado
      detail.html     — Detalle visitante + botón convertir a voluntario
      form.html       — Create/edit visitante
    usuarios/
      list.html       — Lista de usuarios con rol y estado
      form.html       — Create/edit, rol selector, volunteer dropdown (toggleVol JS)
    eventos/
      list.html       — Lista de eventos con badges de tipo
      detail.html     — Detalle + gestión de voluntarios participantes + hora_llegada/hora_salida editable por participante con duración calculada
      form.html       — Create/edit con checkboxes multi-tipo
    economia/
      list.html       — Tarjetas resumen + filtro por tipo + tabla con acciones
    familias/
      ...
    consulta/
      chat.html       — UI de chat: burbujas, typing dots, chips de sugerencias, autoexpand textarea
      list.html       — Lista con filtro por tipo (adopcion/acogida), columnas: nombre, apellidos, DNI, tipo, perro, teléfono, fecha contrato
      detail.html     — Ficha + tarjeta contrato firmado (upload/descarga/eliminar) + dos botones disabled para generar contratos
      form.html       — Create/edit con dropdown de perros (no fallecidos)

dbt_protectora/
  profiles.yml        — Default target: prod (points to Neon)
  models/
    staging/          — stg_perros, stg_voluntarios (incluye fecha_fin_veterano), etc.
    marts/            — Business logic tables
      mart_entradas_salidas_por_mes  — usa perros.fecha_adopcion (no ubicaciones.tipo='adoptado')
      mart_tiempo_adopcion           — usa perros.fecha_adopcion
      mart_patrones_dificultad       — usa perros.fecha_adopcion
      mart_perros_sin_adoptar        — filtra estado='libre'
      mart_vacunas_proximas          — materializado como VIEW (tiempo real, no tabla)
      mart_perros_no_esterilizados   — materializado como VIEW (tiempo real, no tabla)
      mart_tiempo_acogida_mes        — días medios en acogida por mes
      mart_conversion_visitantes     — tasa conversión visitante→voluntario por mes
      mart_saldo_turnos_semanal      — saldo semanal por voluntario (usa fecha_veterano + periodos_apoyo). Alimenta mart_evolucion_saldo_semanal.
      mart_evolucion_saldo_semanal   — saldo medio agregado por semana (últimas 20 semanas)
      mart_cobertura_semanal         — cobertura de turnos por semana (últimas 20 semanas). Usa es_veterano_en_fecha (boolean que respeta fecha_veterano y fecha_fin_veterano) para determinar si un turno cuenta como veterano.
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

### Añadir columnas hora asistencia eventos (migración ya aplicada)
```sql
ALTER TABLE evento_voluntarios ADD COLUMN hora_llegada VARCHAR(5);
ALTER TABLE evento_voluntarios ADD COLUMN hora_salida VARCHAR(5);
```

### Run dbt (prod/Neon)
```bash
cd dbt_protectora
$env:DBT_NEON_HOST="<host>"; $env:DBT_NEON_USER="<user>"; $env:DBT_NEON_PASSWORD="<pass>"; $env:DBT_NEON_DBNAME="<db>"; dbt run
# Solo un modelo (y dependientes):
... dbt run --select mart_cobertura_semanal
... dbt run --select mart_saldo_turnos_semanal+
```

### Insertar estadillo semanal (web)
Ir a `/turnos/estadillo`, pegar el texto y previsualizar antes de insertar.

Convenciones del parser (`app/estadillo_parser.py`):
- NOMBRE en mayúsculas = veterano; nombre minúsculas = voluntario
- `(T.C.)` en cualquier posición = anotación informativa, se ignora
- Otra anotación entre paréntesis en un veterano = medio_turno (ej: `NOAH (a partir de las 11h)`)
- `Visita` = entrada ficticia, se omite silenciosamente
- Lista vacía en un slot = sin cubrir, no se inserta nada

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
12. **Turnos admin separado de perfil voluntario:** `/turnos/` (junta/admin) para CRUD centralizado con filtro por perfil. El perfil del voluntario solo muestra el historial.
13. **Color de marca:** `#31ae90` (verde protectora). Sidebar, login y fondo de página usan esta paleta.
14. **dbt materialización mixta:** Marts de datos históricos = `table`. Marts que deben reflejar estado actual en tiempo real (`mart_vacunas_proximas`, `mart_perros_no_esterilizados`) = `view` con `{{ config(materialized='view') }}`.
15. **Auto-adopción reservados:** Se dispara en cada carga de `/perros/` (no en background). Requiere `fecha_reserva` en el perro; perros sin ese campo no se procesan.
16. **Drill-down charts:** Entradas/adopciones → `/dashboard/detalle-mes?mes=&tipo=`. Conversión visitantes → `/dashboard/detalle-conversion?mes=&tipo=`. La línea de tasa (%) no tiene drill-down.
17. **dbt run logging:** Errores se loguean con `logging.getLogger(__name__)` en `dashboard.py` y las últimas 20 líneas del output se muestran en flash al admin.
18. **Botón atrás en detalle perro:** Usa `history.back()` para respetar filtros activos (tab adoptados, acogida, etc.). Fallback a `/perros/` si JS desactivado.
19. **Regla medio_turno respeta ventana de veterano:** Si 2+ personas coinciden en el mismo hueco y estado=realizado, todos pasan a medio_turno — pero solo si eran veteranos en esa fecha (fecha_veterano ≤ fecha ≤ fecha_fin_veterano, o perfil apoyo_en_junta sin restricción de fecha). Implementado en `turnos_admin.py` y en el insertar estadillo.
20. **Per-model dbt refresh:** `POST /dbt-run-model` (admin) acepta un modelo de `_ALLOWED_MODELS`. Botón ↻ en la tarjeta de cobertura semanal dispara `mart_cobertura_semanal` sin bloquear el resto de analytics.
21. **Cobertura semanal usa es_veterano_en_fecha:** `mart_cobertura_semanal` evalúa si el turno fue realizado cuando el voluntario era veterano (respeta `fecha_fin_veterano`). `apoyo_en_junta` siempre cuenta como veterano. Ventana: últimas 20 semanas.
22. **dbt Neon env vars:** `profiles.yml` target prod usa `DBT_NEON_HOST`, `DBT_NEON_USER`, `DBT_NEON_PASSWORD`, `DBT_NEON_DBNAME`. PowerShell no carga `.env` automáticamente — hay que setearlos manualmente antes de `dbt run`.
23. **fecha_fin_veterano → auto-perfil voluntario:** En el formulario de voluntario, al rellenar `fecha_fin_veterano` el JS fuerza el selector de perfil a `voluntario`. En el servidor, si `fecha_fin_veterano` tiene valor, el perfil se sobreescribe a `voluntario` antes de guardar.
24. **Historial turnos desde 04/08/2025:** `FECHA_HISTORIAL = date(2025, 7, 28)` en `turnos.py`. Se generan todas las semanas desde esa fecha (o `fecha_alta` del voluntario si es posterior) hasta hoy. Semanas sin turno y sin apoyo → fila roja, valor -1. Semana actual → no penaliza aunque no haya turno.
25. **Limpiar semana (admin):** `POST /turnos/limpiar-semana` elimina todos los `TurnoVoluntario` de la semana visible. Botón con confirmación, solo admin.
26. **Medicación visible a veteranos:** A diferencia de vacunas/pesos, `MedicacionPerro` es visible para todos los roles en el perfil del perro. Solo junta/admin pueden añadir/editar/eliminar.
27. **Economía oculta a veteranos:** `MovimientoEconomico` solo accesible a junta/admin. Tipos: ingreso, gasto, deuda. Las deudas tienen campo `pagado` (toggle). Categoría es texto libre.
28. **Fórmula saldo turnos:** `sum(valores_semana) - 1` por semana (no `sum(valores_semana)`). 1 turno = neutro (0), no +1. Aplica igual en Python (`calcular_saldo`) y dbt (`mart_saldo_turnos_semanal`). La semana actual nunca penaliza.
29. **Familias ocultas a veteranos:** `Familia` solo accesible a junta/admin. Los botones de generación de contrato están deshabilitados hasta recibir las plantillas Word (mismo mecanismo que voluntarios).
30. **MedicacionPerro.turno multi-valor:** se guardan como string separado por coma (`"manana,tarde"`). En el formulario son checkboxes independientes; FastAPI recibe `List[str]` y los une con `","`.  En la plantilla se hace `m.turno.split(',')` para mostrar los badges correspondientes.
31. **AntonIA (Text-to-SQL):** Asistente IA en `/consulta/` solo para junta/admin. Flujo: pregunta en lenguaje natural → Groq genera SQL → validación estricta (solo SELECT, bloquea DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/CREATE) → ejecuta en Neon → Groq formatea respuesta. Modelo: `llama-3.3-70b-versatile`. Requiere `GROQ_API_KEY` en env vars. El tiempo en la protectora usa `COALESCE(fecha_adopcion, CURRENT_DATE) - fecha_entrada` para perros ya adoptados.
32. **Gestión de errores HTTP:** Handler para 404 (`404.html`) y 500 (`500.html`). Handler global para excepciones Python no controladas (`Exception`) → loguea el traceback y muestra `500.html`. Endpoint `/health` (GET+HEAD) para el health check de Render.

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

**dbt Neon vars no cargadas (PowerShell):** PowerShell no lee `.env` automáticamente. Hay que setear las 4 vars (`DBT_NEON_HOST`, `DBT_NEON_USER`, `DBT_NEON_PASSWORD`, `DBT_NEON_DBNAME`) en la misma línea antes de `dbt run`. Error típico: `DBT_NEON_HOST not provided`.

**Acento en nombre no encuentra voluntario:** `func.lower()` de SQLAlchemy es accent-sensitive en PostgreSQL. `insertar_turnos.py` usa `unicodedata.normalize("NFD", ...)` en Python para comparar sin tildes — si se añaden búsquedas similares en otros sitios, aplicar el mismo patrón.

**Redirect loop al arrancar con columna nueva:** Si SQLAlchemy incluye en SELECT una columna que no existe en la BD (ej: `fecha_fin_veterano`), el middleware de auth falla en cada request → bucle de redirect. Solución: ejecutar el `ALTER TABLE` correspondiente antes de arrancar.
