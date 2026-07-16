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

**CI local** (lint + smoke tests, antes de hacer push):
```bash
pip install -r requirements-dev.txt
ruff check .
pytest tests/ -v
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
- **Login redirect:** goes directly to `/voluntarios/{voluntario_id}` (their own profile), not to `/`
- **Redirect target on auth fail:** `/voluntarios/{voluntario_id}` if has voluntario_id, else `/perros/`
- Associated with a `Usuario.voluntario_id` (can be null for admin/junta)

**Access control:**
- Router-level: `dependencies=[Depends(get_current_user), Depends(require_not_veterano)]`
- Route-level: `dependencies=[Depends(require_not_veterano)]` or `dependencies=[Depends(require_admin)]`
- Template-level: `{% set es_veterano = ... %}` to hide UI

---

## Key Models & Concepts

### Perro
- `nombre`: always saved in **UPPERCASE** (enforced in create/edit endpoints)
- `nombre_nuevo` (String, nullable): nuevo nombre que le pone la familia adoptante (ej. familias que adoptan y renombran al perro). Opcional, se guarda en mayúsculas. Editable desde la ficha de familia (al vincular el perro o con el lápiz junto a su nombre en "Perros asociados"). En el contrato de adopción aparece como `NOMBRE_VIEJO / NOMBRE_NUEVO`. También se muestra junto al nombre en `perros/detail.html`.
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
- `tamano`: desplegable con Pequeño, Mediano, Mediano-Grande, Grande, Gigante (`perros/form.html`)
- `raza_id`: desplegable de `Raza` con opción "+ Añadir nueva raza…" (`value="__nueva__"`) que revela un input de texto; el backend (`_resolver_raza_id` en `perros.py`) crea la `Raza` si no existe (comparación case-insensitive) o reutiliza la existente

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
- Cambiar ubicación a `casa_adoptiva` → `estado = adoptado`, `fecha_adopcion` se guarda si no había; se vincula opcionalmente a una `Familia` (dropdown "Familia adoptante")
- Cambiar ubicación a `acogida` → se vincula opcionalmente a una `Familia` (dropdown "Familia de acogida"); si venía de adoptado, `estado` vuelve a `libre`
- Cambiar ubicación a física sin familia (refugio/residencia) estando adoptado → `estado = libre`
- Guardar formulario con `estado = adoptado` y ubicación actual ≠ `casa_adoptiva` → se crea automáticamente registro `casa_adoptiva` (sin datos de contacto, rellenar después)
- Guardar formulario con `estado ≠ adoptado` viniendo de adoptado con `casa_adoptiva` → se cierra `casa_adoptiva` y se crea `refugio`
- **Familia por ubicación (`Ubicacion.familia_id`):** cada registro de `Ubicacion` de tipo `casa_adoptiva` o `acogida` guarda su propia familia asociada (igual que antes se guardaba `voluntario_id` para acogida). Permite que el historial muestre la familia correcta de cada periodo, no solo la actual del perro. `Perro.familia_id` siempre refleja la familia de la ubicación activa; se limpia a `None` al pasar a refugio/residencia.
- Los desplegables de familia (adoptante/acogida, tanto al crear como al editar una ubicación) muestran **todas** las familias, no filtradas por `Familia.tipo` — una misma familia puede adoptar un perro y acoger otro. Se etiqueta cada opción con "· Acogida" / "· Adopción" según `Familia.tipo` como pista visual.
- Los campos "Nombre contacto"/"Teléfono contacto" se ocultan en el formulario cuando el tipo es `casa_adoptiva` o `acogida` (esos datos salen de la familia); solo se muestran para refugio/residencia. La tarjeta "Ubicación actual" muestra el teléfono en vivo de `Familia.telefono` (no una copia guardada).
- El `voluntario_id` de `Ubicacion` ya **no se usa** para nuevas entradas (se sustituyó por `familia_id` en acogida); se conserva solo para mostrar el histórico de registros antiguos.

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
- `saldo_manual` (Float, nullable): **Saldo efectivo** anotado manualmente por el gestor. Independiente del saldo automático. Editable por junta/admin via `POST /voluntarios/{id}/saldo-gestor`. Visible (solo lectura) también por veteranos en su perfil.
- `notas_saldo_manual` (Text, nullable): contexto del saldo efectivo (ej. "Deuda temporada anterior").
- Turnos: one-to-many `TurnoVoluntario`
- Periodos de apoyo: one-to-many `PeriodoApoyo` (`fecha_inicio`, `fecha_fin` nullable). Las semanas cubiertas por un periodo de apoyo se neutralizan en el saldo (no suman ni restan).
- `en_redes` (Boolean, default false): marca si el voluntario pertenece al equipo de redes sociales. Un veterano con este flag tiene acceso a la sección `/redes/` aunque su rol siga siendo de solo lectura para el resto de la app (ver `require_redes_access` y sección PerroRedes).

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
- **`tipo` es TEXT** (no enum) — se almacena como string separado por comas. Históricamente existía un enum `tipoevento` que fue eliminado (`ALTER TABLE eventos ALTER COLUMN tipo TYPE TEXT USING tipo::TEXT`)
- `participantes`: one-to-many `EventoVoluntario` (UniqueConstraint evento_id+voluntario_id)
- CRUD en `app/routers/eventos.py` (prefix `/eventos/`), visible para junta/admin
- Tipos libres seleccionables con checkboxes múltiples; se almacenan como texto separado por comas

### EventoVoluntario
- `evento_id`, `voluntario_id`, `hora_llegada` (String HH:MM, nullable), `hora_salida` (String HH:MM, nullable)
- `POST /eventos/{id}/voluntario/{vid}/horario` guarda hora_llegada y hora_salida (junta/admin)
- `POST /eventos/{id}/apuntarme` — veterano se apunta a sí mismo con hora_llegada/hora_salida opcionales (accesible a todos los roles autenticados)
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
- `tipo`: String nullable — `'adopcion'` | `'acogida'`. Es solo una etiqueta/pista (mostrada en los desplegables como "· Acogida"/"· Adopción") — **no filtra** qué familias pueden vincularse a un perro, porque una misma familia puede adoptar un perro y acoger otro.
- `perros`: relación uno-a-muchos vía `Perro.familia_id` (no hay `Familia.perro_id`) — se vincula al cambiar la ubicación de un perro a `casa_adoptiva` o `acogida`, o desde la ficha de familia ("Vincular perro" / perro inicial al crear la familia)
- `voluntario_id`, `voluntario_id_2` (Integer, nullable, ambos `ON DELETE SET NULL`): permiten vincular hasta dos `Voluntario` a la misma familia (ej. pareja/conviviente que también es voluntario). Ambos son opcionales y solo los rellena junta/admin cuando lo sabe — no se pregunta a nadie por su situación personal. `detalle_voluntario` (`turnos.py`) busca `familia_vinculada` comprobando **ambos** campos (`or_(Familia.voluntario_id == id, Familia.voluntario_id_2 == id)`), y `perros_acogida` incluye las acogidas activas de esa familia (`Ubicacion.familia_id`) además de las históricas vinculadas directamente por `Ubicacion.voluntario_id` — así un perro en acogida por la familia le aparece a los dos voluntarios, no solo al que quedó registrado como principal.
- Campos opcionales: `email`, `telefono`, `direccion`, `municipio`, `codigo_postal`, `notas`
- `provincia`: desplegable con las 50 provincias españolas + Ceuta y Melilla (`PROVINCIAS` en `app/routers/familias.py`), no texto libre
- `fecha_contrato`: Date (obligatoria, default hoy) — fecha de firma del contrato
- `contrato_firmado_url`, `contrato_firmado_fecha`, `contrato_firmado_nombre`: upload del contrato firmado a Cloudinary (`protectora/contratos/contrato_familia_{id}`, resource_type=raw)
- `dni_frontal_url`, `dni_reverso_url` (String, nullable): fotos/documento del DNI subidas a Cloudinary (`protectora/dni/dni_{lado}_familia_{id}`, `resource_type=auto`). Cada hueco acepta imagen **o** PDF, porque el DNI a veces llega como una sola imagen por cara y otras como un único PDF con ambas caras — en ese caso se sube solo en `frontal` y `reverso` se deja vacío. El template detecta si la URL termina en `.pdf` para mostrar icono de documento en vez de miniatura. Endpoints: `POST /familias/{id}/dni/{lado}` y `POST /familias/{id}/dni/{lado}/eliminar` (`lado` = `frontal`|`reverso`).
- CRUD en `app/routers/familias.py` (prefix `/familias/`), **solo junta/admin** (oculto a veteranos)
- Detalle: tres botones de contrato (acogida azul, pre-adopción amarillo, adopción verde) activos si tiene perro asignado; tarjeta upload contrato firmado igual que voluntarios; tarjeta "Documentación DNI" con dos huecos (delantera/trasera)
- Vista `/familias/contratos`: resumen con/sin contrato firmado + tabla descargable, igual que voluntarios
- Sidebar: entre Visitas y Turnos
- El desplegable de perro (al crear una familia o en "Vincular perro") muestra **todos** los perros, sin filtrar por `estado` — antes excluía fallecidos/adoptados.
- Renombrado al adoptar: al vincular un perro (crear familia, "Vincular perro", o con el lápiz en "Perros asociados") hay un campo opcional "Nuevo nombre" que guarda `Perro.nombre_nuevo` (ver sección Perro).

### PerroRedes / PublicacionRedes
Sustituye el Excel manual del equipo de redes sociales (nombre del perro, última publicación, refugio/acogida/otro).
- `PerroRedes`: `nombre` (propio, mayúsculas), `perro_id` (FK `Perro`, nullable, `ON DELETE SET NULL`), `origen` (`'refugio'`|`'acogida'`|`'otro'`, String libre no enum), `activo` (Boolean, para archivar), `notas`
  - `perro_id` es opcional a propósito: puede ser un caso externo, una residencia o un perro que aún no ha entrado en el sistema
  - El desplegable "Vincular a perro existente" es un buscador cliente (input + lista JSON embebida vía `_perros_json()`, sin librería ni endpoint nuevo) que solo muestra perros `libre`/`reservado` (excluye adoptados/fallecidos)
- `PublicacionRedes`: `perro_redes_id` (FK, `ON DELETE CASCADE`), `fecha`, `plataforma` (`'instagram'`|`'tiktok'`, una plataforma por fila, no multi-select)
- CRUD en `app/routers/redes.py` (prefix `/redes/`). Página `/redes/{id}` combina en una sola vista: edición de campos, ficha resumida del `Perro` vinculado (si existe, con link a la ficha completa) e historial de publicaciones con alta/baja — no hay ruta `/editar` separada
- `/redes/` (listado): tarjetas resumen (últimos 3 publicados, top 5 sin publicarse hace más tiempo, top 5 más publicados) + tabla con nº publicaciones últimos 3 meses y total histórico. Tabs Activos/Archivados
- Acceso: admin, junta, o veterano con `Voluntario.en_redes=True` (`require_redes_access` en `auth.py`) — primer caso de acceso "por flag" en vez de solo por rol
- Tablas nuevas (`perros_redes`, `publicaciones_redes`) se crean solas vía `Base.metadata.create_all` en `init_db()`, sin SQL manual

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
  models.py           — SQLAlchemy models (Perro, Voluntario, TurnoVoluntario, MedicacionPerro, MovimientoEconomico, Evento, EventoVoluntario, PerroRedes, PublicacionRedes, etc.)
  auth.py             — get_current_user, require_not_veterano, require_admin, require_redes_access
  database.py         — Session factory
  templates_config.py — Jinja2 setup
  main.py             — FastAPI app, NotAuthorized redirect to /voluntarios/{id} para veteranos con voluntario_id, else /perros/
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
    familias.py       — CRUD familias + upload contrato firmado (Cloudinary) + GET /contratos. Prefix: /familias/
    consulta.py       — Asistente AntonIA: Text-to-SQL con Groq. GET /consulta/ (UI chat), POST /consulta/preguntar (AJAX). Solo junta/admin. Requiere GROQ_API_KEY.
    redes.py          — CRUD PerroRedes + PublicacionRedes. Prefix: /redes/. Admin/junta + veterano con en_redes=True.
  templates/
    base.html         — Sidebar desktop + offcanvas móvil. Colores marca verde #31ae90→#1d8a6e. Nunito en headings. Fondo #eef4f2
    login.html        — Login form (with logo). Fondo gradiente verde marca
    dashboard.html    — Stat cards (incl. widget próximo evento) + charts + dbt button. Drill-down en entradas/adopciones y conversión visitantes. Gráficos: entradas/salidas, conversión visitantes, cobertura semanal (20 semanas), evolución saldo (20 semanas), tiempo adopción, tiempo acogida.
    perros/
      list.html       — Tabs: En refugio / En acogida / Reservados / Adoptados / Todos. 35 por página. Contador. Ordenación preservada al paginar.
      detail.html     — Photo, edit/delete, pesos, celos, medicaciones (visible a todos), vacunas (ocultas a veterano). Ubicaciones: cambio + edición individual, con select de familia (adoptante/acogida) según tipo. Botón atrás usa history.back().
      form.html       — Create/edit, name uppercase, photo upload, fecha_adopcion (visible si estado=adoptado), raza con opción "+ Añadir nueva raza…", tamaño incluye "Mediano-Grande"
    voluntarios/
      list.html       — Active volunteers. Columnas: Saldo app (automático) + Saldo efectivo (manual).
      detail.html     — Profile + historial turnos (desde 04/08/2025, semanas vacías en rojo con -1, apoyo en azul). Tarjetas paralelas: Saldo de turnos (automático) + Saldo efectivo (manual, editable por junta/admin). Widget próximo evento con botón "Apuntarme" (solo veterano).
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
      list.html       — Lista con filtro por tipo + botón "Contratos"
      detail.html     — Ficha + botones generar contrato acogida/pre-adopción/adopción (activos si tiene perro) + tarjeta contrato firmado
      form.html       — Create/edit con dropdown de todos los perros, campo "Nuevo nombre" opcional, provincia como desplegable
      contratos.html  — Resumen con/sin contrato firmado + tabla descargable (igual que voluntarios/contratos_firmados.html)
    consulta/
      chat.html       — UI de chat: burbujas, typing dots, chips de sugerencias, autoexpand textarea
      list.html       — Lista con filtro por tipo (adopcion/acogida), columnas: nombre, apellidos, DNI, tipo, perro, teléfono, fecha contrato
      detail.html     — Ficha + tarjeta contrato firmado (upload/descarga/eliminar) + dos botones disabled para generar contratos
      form.html       — Create/edit con dropdown de perros (no fallecidos)
    redes/
      list.html       — Tarjetas resumen (últimos publicados, sin publicarse hace más tiempo, más publicados) + tabla + tabs Activos/Archivados
      detail.html     — Página única: edición de PerroRedes + ficha resumida del Perro vinculado + historial de publicaciones (alta/baja)
      form.html       — Solo alta de PerroRedes nuevo; buscador cliente de perro (libre/reservado) en vez de <select>

tests/
  conftest.py         — Fixture `client` (TestClient con SQLite en memoria). Mockea langfuse.get_client (auth_check en main.py haría una llamada de red real) y sobreescribe get_db + app.database.SessionLocal/engine para no tocar nunca Neon.
  test_smoke.py       — 4 smoke tests: /health, /login, / y /consulta/ sin sesión (solo comprueban que no hay 500, no lógica de negocio)

.github/workflows/ci.yml — Job único en push/PR a main: ruff check . (solo reglas F de pyflakes) + pytest tests/. No requiere secrets (ver Design Decision 47).

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
Desde la UI: en el formulario de perro, seleccionar "+ Añadir nueva raza…" en el desplegable de raza y escribir el nombre (se crea automáticamente al guardar). También por SQL directo si hace falta:
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

### Renombrado al adoptar + familia por ubicación (comprobar si ya se ejecutó en Neon)
```sql
ALTER TABLE perros ADD COLUMN nombre_nuevo VARCHAR(100);
ALTER TABLE ubicaciones ADD COLUMN familia_id INTEGER REFERENCES familias(id) ON DELETE SET NULL;
```

### Segundo voluntario vinculado a Familia (migración ya aplicada en Neon)
```sql
ALTER TABLE familias ADD COLUMN voluntario_id_2 INTEGER REFERENCES voluntarios(id) ON DELETE SET NULL;
```

### Flag en_redes en Voluntario (comprobar si ya se ejecutó en Neon)
```sql
ALTER TABLE voluntarios ADD COLUMN en_redes BOOLEAN NOT NULL DEFAULT false;
```
Las tablas `perros_redes` y `publicaciones_redes` no necesitan SQL manual: se crean solas al arrancar la app (`create_all`).

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
Render tiene su propia integración nativa con GitHub (no es un GitHub Action) y hace auto-deploy en cada push a `main`. En paralelo, `.github/workflows/ci.yml` corre ruff + smoke tests en push/PR a `main` — ambos son independientes, un fallo del CI no bloquea automáticamente el deploy de Render (es responsabilidad del equipo no mergear con el check en rojo).

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
29. **Familias ocultas a veteranos:** `Familia` solo accesible a junta/admin.
33. **Contratos familia (DOCX→PDF):** Tres tipos implementados, todos en `app/contracts/` y `app/utils/`. Conversión compartida en `app/utils/pdf_utils.py` (`docx_a_pdf`): Word COM en local, LibreOffice en Render. Devuelve PDF si tiene éxito, DOCX como fallback.
    - **Adopción** (`contrato_adopcion.docx` / `contrato_adopcion.py`): incluye tasa. Endpoint: `GET /familias/{id}/contrato-adopcion/{perro_id}`.
    - **Acogida** (`contrato_acogida.docx` / `contrato_acogida.py`): sin tasa. Fecha en run único con espacios como marcador (detecta "En Salamanca" sin "XX"). Endpoint: `GET /familias/{id}/contrato-acogida/{perro_id}`.
    - **Pre-adopción** (`contrato_preadopcion.docx` / `contrato_preadopcion.py`): sin tasa. Fecha con 8 runs distintos (day=run[2], month=run[5], year=run[6]). Endpoint: `GET /familias/{id}/contrato-preadopcion/{perro_id}`.
    - Orden de botones en detalle: acogida (azul) → pre-adopción (amarillo) → adopción (verde). Modal de advertencia de campos faltantes compartido por los tres.
    - **Email siempre en minúsculas:** en `contrato_acogida.py` y `contrato_adopcion.py`, el campo correo se rellena con `_set_run(..., upper=False)`. El resto de campos van en mayúsculas (`upper=True`, por defecto).
    - **Auto-ajuste de tamaño de letra sin mover la tabla:** ambos ficheros tienen `_fit_font_size()` + una tabla estática `_CHAR_WIDTH_EM` (anchos de carácter de Times New Roman Negrita, medidos una vez con la fuente real para no depender de tenerla instalada en Render). Las tablas de las plantillas usan `tblLayout type="fixed"` (ancho de columna fijo), así que si un valor no cabe en una línea se reduce el tamaño de letra (mínimo 6pt, pasos de 0.5pt) en vez de dejar que Word ensanche la fila/tabla. El tamaño base para reducir se toma del tamaño original de cada campo en la plantilla (no un valor fijo — `contrato_adopcion.docx` mezcla 10pt en la tabla de familia y 9pt en la de perro).
    - **contrato_adopcion.py — punto 21 (tasa) y fecha final:** la plantilla actual divide "la cantidad de ____ €" y "__ de ______ de ____." en varios runs distintos de Word. `_fill_tasa` busca el run que contiene literalmente `"____"` y lo sustituye (ya no busca la frase completa "la cantidad de  €", que dejó de existir tras editar la plantilla). `_fill_fecha` localiza con regex los runs que son solo guiones bajos (día/mes/año) y rellena cada uno con la fecha actual, en vez de reemplazar un único run con la frase entera.
34. **Vínculo familia al cambiar ubicación (casa_adoptiva o acogida):** El formulario de cambio de ubicación muestra un select de familia ("Familia adoptante" para `casa_adoptiva`, "Familia de acogida" para `acogida`), con **todas** las familias (no filtradas por `tipo`). Al seleccionar una, se actualiza `Perro.familia_id` y también `Ubicacion.familia_id` de esa entrada concreta (para que el historial recuerde la familia de cada periodo). Los selects aparecen/desaparecen con JS según el tipo elegido, tanto al crear como al editar una ubicación existente.
30. **MedicacionPerro.turno multi-valor:** se guardan como string separado por coma (`"manana,tarde"`). En el formulario son checkboxes independientes; FastAPI recibe `List[str]` y los une con `","`.  En la plantilla se hace `m.turno.split(',')` para mostrar los badges correspondientes.
31. **AntonIA (Text-to-SQL):** Asistente IA en `/consulta/` solo para junta/admin. Flujo: pregunta en lenguaje natural → Groq genera SQL → validación estricta (solo SELECT, bloquea DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE/CREATE) → ejecuta en Neon → Groq formatea respuesta. Modelo: `llama-3.3-70b-versatile`. Requiere `GROQ_API_KEY` en env vars. El tiempo en la protectora usa `COALESCE(fecha_adopcion, CURRENT_DATE) - fecha_entrada` para perros ya adoptados.
32. **Gestión de errores HTTP:** Handler para 404 (`404.html`) y 500 (`500.html`). Handler global para excepciones Python no controladas (`Exception`) → loguea el traceback y muestra `500.html`. Endpoint `/health` (GET+HEAD) para el health check de Render.
35. **Evento.tipo es TEXT:** La columna `tipo` de `eventos` fue migrada de enum `tipoevento` a `TEXT` (`ALTER TABLE eventos ALTER COLUMN tipo TYPE TEXT USING tipo::TEXT; DROP TYPE IF EXISTS tipoevento`). Se almacena como string separado por comas.
36. **Dashboard widget próximo evento:** Stat card que muestra el siguiente evento (fecha badge + título + horario). Sustituye a la antigua stat card "Sin esterilizar". La tarjeta grande de "Pendientes de esterilizar" se mantiene en la sección inferior.
37. **Veterano landing page:** Al hacer login, el veterano va directamente a `/voluntarios/{voluntario_id}` en lugar de pasar por el dashboard. El handler `NotAuthorized` también redirige a su perfil (no a `/perros/`) si tiene `voluntario_id`.
38. **Widget próximo evento en perfil veterano:** En `voluntarios/detail.html`, los veteranos ven un widget del próximo evento con botón "Apuntarme" que abre un modal para indicar hora de llegada/salida. Endpoint: `POST /eventos/{id}/apuntarme` (accesible a todos los roles).
39. **Saldo efectivo paralelo al saldo automático:** `Voluntario.saldo_manual` (Float, nullable) y `Voluntario.notas_saldo_manual` (Text, nullable) almacenan el saldo anotado manualmente por el gestor. Nunca se combina con `calcular_saldo()` — son dos sistemas paralelos independientes. Visibles en lista (columna "Saldo efectivo") y perfil (tarjeta con mismo estilo que "Saldo de turnos"). Editable solo por junta/admin.
40. **Documentación DNI de Familia:** dos campos independientes `dni_frontal_url`/`dni_reverso_url`, subida a Cloudinary con `resource_type="auto"` (deja que Cloudinary detecte imagen vs PDF; ambos casos se guardan como resource_type "image", por lo que `destroy()` sin parámetro explícito sigue sirviendo para borrar cualquiera de los dos). En la práctica el DNI llega unas veces como dos fotos (delante/detrás) y otras como un único PDF con ambas caras — en ese segundo caso se sube solo en el hueco `frontal` y `reverso` queda vacío. El template decide si mostrar miniatura de imagen o icono de PDF mirando si la URL termina en `.pdf`. No hay gating entre los dos huecos (se pueden rellenar en cualquier orden), simplemente se listan en el formulario primero delantera y después trasera.
41. **Perro.nombre_nuevo (renombrado al adoptar):** campo opcional en `Perro`, editable desde la ficha de familia (no desde el formulario de perro). Si tiene valor, se muestra como `NOMBRE / NOMBRE_NUEVO` en el contrato de adopción (`contrato_adopcion.py`, tabla del perro) y junto al nombre en `perros/detail.html` y en "Perros asociados" de la familia.
42. **Desplegables de perro/familia sin filtrar por estado o tipo:** el selector de perro al crear una familia (o "Vincular perro") muestra todos los perros sin filtrar por `estado`. Los selectores de familia en el cambio de ubicación del perro muestran todas las familias sin filtrar por `tipo`. Razón: una familia puede adoptar un perro y acoger otro; un perro puede necesitar re-vincularse aunque ya esté adoptado/fallecido en casos excepcionales.
43. **Ubicacion.familia_id (histórico por tipo de ubicación):** además de `Perro.familia_id` (familia actual), cada `Ubicacion` de tipo `casa_adoptiva`/`acogida` guarda su propia `familia_id`. Al editar una ubicación pasada, cambiar la familia solo afecta a esa entrada; si la ubicación editada es la activa (`fecha_fin is None`), también se sincroniza `Perro.familia_id`. El campo `Ubicacion.voluntario_id` (usado antes para acogida) se conserva solo para mostrar histórico antiguo, ya no se rellena en formularios nuevos.
44. **Contacto de ubicación como marcador temporal sin familia dada de alta:** "Nombre contacto"/"Teléfono contacto" del formulario de ubicación (form rápido y modal de edición) están siempre visibles, incluso con tipo `casa_adoptiva` o `acogida` — sirven para anotar un nombre provisional cuando la familia aún no está dada de alta en la app. La tarjeta "Ubicación actual" prioriza `Familia` > `voluntario` > `nombre_contacto` al mostrar el contacto, así que en cuanto se vincula una `Familia` real a esa ubicación, su nombre y el teléfono en vivo de `Familia.telefono` sustituyen al nombre/teléfono manual (que se conserva en la BD pero deja de mostrarse).
45. **Raza "Añadir nueva" en el formulario de perro:** el desplegable de raza incluye la opción `__nueva__` que revela un input de texto; `_resolver_raza_id()` en `perros.py` crea la `Raza` (o reutiliza una existente con el mismo nombre, comparación case-insensitive) antes de guardar el perro.
46. **Provincia de Familia como desplegable:** `PROVINCIAS` (lista fija de las 50 provincias + Ceuta y Melilla) en `app/routers/familias.py`, usada en `familias/form.html` en vez de texto libre. Registros antiguos con grafía distinta no quedan preseleccionados.
47. **CI (ruff + smoke tests), sin secrets:** `.github/workflows/ci.yml` corre `ruff check .` (solo reglas `F` de pyflakes — imports rotos, variables no usadas, nombres indefinidos; sin reglas de estilo `E` para no generar ruido sobre patrones ya asentados como `Columna == True`) y 4 smoke tests con pytest. Los tests usan SQLite en memoria (`tests/conftest.py` sobreescribe `get_db` y también `app.database.SessionLocal`/`engine`, porque `CurrentUserMiddleware` abre su propia sesión sin pasar por la dependencia) — nunca tocan Neon ni requieren credenciales. `langfuse.get_client` se mockea en el import porque `app/main.py` hace `assert langfuse.auth_check()` a nivel de módulo (llamada de red real). `app/database.py:init_db()` salta el `CREATE SCHEMA analytics` cuando el dialect no es Postgres, para que el `startup` event funcione contra SQLite en CI.
48. **Redes (PerroRedes/PublicacionRedes):** Sustituye el Excel manual del equipo de redes. `PerroRedes` no es un alias de `Perro`: tiene `nombre` propio y `perro_id` opcional (`ON DELETE SET NULL`), porque puede ser un caso externo, una residencia o un perro que aún no ha entrado en el sistema. `origen` (`refugio`|`acogida`|`otro`) y `PublicacionRedes.plataforma` (`instagram`|`tiktok`) son `String` con listas de constantes en `redes.py`, no enums de Postgres (mismo criterio que `Evento.tipo`, decisión 35). Una publicación = una fila (fecha + una sola plataforma).
49. **Acceso a Redes por flag, no solo por rol:** `Voluntario.en_redes` (Boolean) marca quién pertenece al equipo de redes. `require_redes_access` (`auth.py`) permite admin, junta, o veterano con `voluntario.en_redes=True` — primer caso de acceso que depende de un flag además del rol. El enlace del sidebar usa la misma condición; el resto de restricciones de veterano no cambian.
50. **Redes: página única editar+historial:** `/redes/{id}` combina edición de `PerroRedes`, ficha resumida del `Perro` vinculado (con link a la ficha completa) e historial de publicaciones (alta/baja) en una sola vista — no existe una ruta `/editar` separada. Mismo criterio que `perros/detail.html` (info + sub-registros como pesos/celos en una sola página).
51. **Buscador de perro en vez de `<select>`:** el campo "Vincular a perro existente" en Redes es un buscador cliente (input + JSON embebido vía `_perros_json()`, sin librería ni endpoint AJAX nuevo) porque un `<select>` con cientos de perros era inmanejable. Solo lista perros `libre`/`reservado`.
52. **Fuentes MS reales en Docker (contratos):** el `Dockerfile` instala `ttf-mscorefonts-installer` (Times New Roman auténtica) además de `fonts-liberation`, para que la conversión DOCX→PDF con LibreOffice en Render use la misma fuente que Word COM en local. Sin esto, LibreOffice sustituía Times New Roman por Liberation Serif (metric-compatible pero no idéntica), lo que desajustaba `_fit_font_size()` (calculado con el `timesbd.ttf` real) y descuadraba tablas/párrafos en los contratos generados desde Render/móvil.
53. **Salto de página explícito en contrato_adopcion.docx:** incluso con la misma fuente (decisión 52), Word y LibreOffice no paginan de forma idéntica cuando la página se llena "de forma natural" — pequeñas diferencias de interlineado hacían que LibreOffice metiera un párrafo más al final de la página 1 (partiendo la estipulación 3ª entre dos páginas) mientras que Word la mantenía entera en la página 2. Se fijó `paragraph_format.page_break_before = True` en el párrafo "3ª - En caso de ser adulto..." directamente en la plantilla (`app/contracts/contrato_adopcion.docx`), así la página 2 siempre arranca ahí en cualquier motor de renderizado. Si aparecen saltos de página inconsistentes en otras plantillas (`contrato_acogida.docx`, `contrato_preadopcion.docx`), aplicar el mismo criterio: forzar `page_break_before` en el párrafo donde deba empezar cada página, en vez de confiar en el reflow automático.

---

## User Preferences

- **Terse responses:** No trailing summaries unless asked.
- **Naming:** "Apellidos" (plural), not "Apellido".
- **Git workflow:** New commits, not amends. No force push to main.
- **File reading:** Always read before editing.
- **Memory:** Specific details about user preferences and project decisions are saved in `memory/` directory.

---

## Troubleshooting

**Veterano infinite redirect loop:** El handler `NotAuthorized` redirige a `/voluntarios/{id}` si el veterano tiene `voluntario_id`, o a `/perros/` como fallback. El login redirige directamente al perfil del veterano. No redirigir a `/` (causa loop con el dashboard que requiere `require_not_veterano`).

**Cloudinary config empty:** Move `cloudinary.config()` inside the upload function so it reads env vars at request time, not import time.

**PostgreSQL enum change:** Cannot rename or add values with a simple UPDATE. Use `ALTER TYPE` DDL. Cannot DROP enum values — recreate type if needed.

**dbt run timeout:** If it takes >180s, increase timeout in `dashboard.py:ejecutar_dbt()`.

**Adopciones en drill-down no cargaban:** El filtro usaba `TipoUbicacion.adoptado` que ya no existe. Corregido a `Perro.fecha_adopcion` (consistente con los marts).

**Vacunas con fecha_proxima vacía (datos históricos):** Corregido con `UPDATE vacunas SET fecha_proxima = fecha_administracion + INTERVAL '1 year' WHERE fecha_proxima IS NULL`.

**Badge invisible (mismo color que fondo):** Añadir `.badge-{tipo}` en `base.html` con el color correspondiente.

**dbt Neon vars no cargadas (PowerShell):** PowerShell no lee `.env` automáticamente. Hay que setear las 4 vars (`DBT_NEON_HOST`, `DBT_NEON_USER`, `DBT_NEON_PASSWORD`, `DBT_NEON_DBNAME`) en la misma línea antes de `dbt run`. Error típico: `DBT_NEON_HOST not provided`.

**Acento en nombre no encuentra voluntario:** `func.lower()` de SQLAlchemy es accent-sensitive en PostgreSQL. `insertar_turnos.py` usa `unicodedata.normalize("NFD", ...)` en Python para comparar sin tildes — si se añaden búsquedas similares en otros sitios, aplicar el mismo patrón.

**Redirect loop al arrancar con columna nueva:** Si SQLAlchemy incluye en SELECT una columna que no existe en la BD (ej: `fecha_fin_veterano`), el middleware de auth falla en cada request → bucle de redirect. Solución: ejecutar el `ALTER TABLE` correspondiente antes de arrancar.

**Contrato PDF descuadrado solo desde Render/móvil (no en local):** En local, `docx_a_pdf()` usa Word COM con la Times New Roman real instalada en Windows. En Render (y por tanto desde el móvil) usa el fallback de LibreOffice, que sin `ttf-mscorefonts-installer` sustituía Times New Roman por Liberation Serif — métricas parecidas pero no idénticas, que desajustaban el cálculo de `_fit_font_size()` (medido con el `timesbd.ttf` real) y descuadraban tablas/párrafos. Solucionado instalando fuentes MS reales en el `Dockerfile` (decisión 52).
