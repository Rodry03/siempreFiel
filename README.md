# Siempre Fiel — App de gestión de protectora de perros

Aplicación web para la gestión interna de la protectora **Siempre Fiel**: registro de perros, voluntarios, turnos y analítica con dbt.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | FastAPI + Jinja2 |
| Frontend | Bootstrap 5 |
| Base de datos | PostgreSQL |
| ORM | SQLAlchemy |
| Analítica | dbt-postgres |

## Estructura del proyecto

```
protectora/
├── app/
│   ├── main.py              # Entrada FastAPI
│   ├── database.py          # Conexión y sesión SQLAlchemy
│   ├── models.py            # Modelos ORM
│   ├── schemas.py           # Schemas Pydantic
│   ├── routers/
│   │   ├── dashboard.py
│   │   ├── perros.py
│   │   └── voluntarios.py
│   ├── templates/           # Jinja2 + Bootstrap
│   └── static/
├── scripts/                 # Pipeline de carga de datos
│   ├── load_raw_perros.py   # xlsx → PostgreSQL raw schema
│   ├── cargar_perros.py     # mart → app (perros activos)
│   ├── cargar_vacunas.py    # staging → app (vacunas)
│   └── cargar_adoptados.py  # raw → app (perros adoptados)
└── dbt_protectora/
    ├── macros/              # Macros Jinja reutilizables
    ├── models/
    │   ├── staging/         # Limpieza y normalización de datos crudos
    │   └── marts/           # Modelos de negocio listos para consumir
    └── tests/               # Tests singulares SQL
```

## Modelos de datos

### Perros
- **Perro** — nombre, raza (FK), fecha nacimiento, sexo, esterilizado, chip, pasaporte, color, fecha entrada, estado (`activo` / `adoptado` / `fallecido`), notas
- **Raza** — tabla normalizada de razas
- **Vacuna** — tipo, fecha administración, próxima dosis, veterinario
- **Ubicacion** — tipo (`refugio` / `acogida` / `residencia` / `adoptado`), periodo, contacto

### Voluntarios
- **Voluntario** — nombre, apellido, DNI, email, teléfono, perfil, fecha alta, activo, permiso PPP, notas
- **TurnoVoluntario** — fecha, franja (`manana` / `tarde`), estado

#### Perfiles de voluntario
| Perfil | Hace turnos |
|---|---|
| `veterano` | Sí |
| `voluntario` | Sí |
| `directiva` | No |
| `guagua` | No |
| `eventos` | No |
| `colaboradores` | No |

#### Estados de turno
| Estado | Valor saldo |
|---|---|
| `realizado` | 1.0 |
| `medio_turno` | 0.5 |
| `falta_justificada` | 0.0 |
| `falta_injustificada` | 0.0 |
| `no_apuntado` | 0.0 |

## Analítica con dbt

El proyecto dbt transforma los datos de PostgreSQL en modelos listos para analizar, siguiendo el patrón **ELT** (Extract → Load → Transform).

### Sources declaradas

```yaml
# dbt_protectora/models/staging/sources.yml
sources:
  - name: protectora   # schema: public  (tablas de la app)
  - name: raw          # schema: raw     (datos crudos del xlsx)
```

### Staging (limpieza y normalización)

Modelos de la app:
- `stg_perros` — perros activos con raza denormalizada
- `stg_vacunas` — historial de vacunas
- `stg_ubicaciones` — historial de ubicaciones
- `stg_voluntarios` — voluntarios activos con perfiles que hacen turnos
- `stg_turnos_voluntarios` — registro de turnos (**incremental**, unique_key: `id`)

Pipeline de carga desde xlsx:
- `stg_perros_entrada` — perros activos del xlsx con limpieza completa (razas normalizadas, fechas validadas, PPP extraído)
- `stg_perros_adoptados` — perros adoptados del xlsx

### Marts (negocio)

- `mart_vacunas_proximas` — vacunas próximas a vencer
- `mart_perros_no_esterilizados` — perros que aún no están esterilizados
- `mart_tiempo_en_refugio` — tiempo que lleva cada perro en el refugio
- `mart_saldo_turnos` — saldo de turnos por voluntario (turnos realizados vs semanas activo desde `2026-04-01`)
- `mart_perros_a_cargar` — estado de cada perro del xlsx para la carga a la app (`listo` / `pendiente_raza` / `pendiente_datos` / `ya_cargado`)

### Macros

- `ubicacion_actual_perro()` — devuelve la ubicación vigente de cada perro (sin `fecha_fin`), usada en varios marts

### Tests

**Tests genéricos** (`schema.yml`) — `not_null`, `unique`, `accepted_values`, `relationships`. Algunos con `severity: warn`.

**Tests singulares** (`tests/`):
- `vacuna_proxima_antes_de_administracion.sql` — detecta vacunas con próxima dosis anterior a la administración
- `perro_activo_sin_ubicacion.sql` — detecta perros activos sin ubicación registrada
- `voluntario_deuda_excesiva.sql` — detecta voluntarios con saldo de turnos inferior a -30

### Documentación

```bash
cd dbt_protectora
dbt docs generate
dbt docs serve
```

Genera documentación interactiva con el grafo de linaje completo del DAG.

## Pipeline de carga de datos

Para poblar la app desde el fichero xlsx de la protectora:

```bash
# 1. Cargar xlsx al schema raw de PostgreSQL
python scripts/load_raw_perros.py

# 2. Transformar con dbt (staging + mart_perros_a_cargar)
cd dbt_protectora && dbt run

# 3. Cargar perros activos a la app
python scripts/cargar_perros.py

# 4. Cargar vacunas
python scripts/cargar_vacunas.py

# 5. Cargar perros adoptados
python scripts/cargar_adoptados.py
```

## Instalación y arranque

### Requisitos
- Python 3.10+
- PostgreSQL con base de datos `protectora` y usuario `postgres`

### Puesta en marcha

```bash
# Clonar el repositorio
git clone https://github.com/Rodry03/siempreFiel.git
cd siempreFiel

# Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno (copiar y editar)
cp .env.example .env

# Arrancar la app
uvicorn app.main:app --reload
```

La app estará disponible en `http://localhost:8000`.

### Ejecutar dbt

```bash
cd dbt_protectora

# Windows PowerShell
$env:DBT_PASSWORD="tu_password"; dbt run

# Linux/Mac
DBT_PASSWORD=tu_password dbt run
```

## Variables de entorno

Ver `.env.example` para la configuración necesaria (conexión a PostgreSQL).

## Añadir razas

Las razas se gestionan directamente en base de datos:

```sql
INSERT INTO razas (nombre) VALUES ('Nueva Raza');
```
