# Siempre Fiel — App de gestión de protectora de perros

Aplicación web para la gestión interna de la protectora **Siempre Fiel**: registro de perros, voluntarios, turnos, visitantes y analítica con dbt.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | FastAPI + Jinja2 |
| Frontend | Bootstrap 5 |
| Base de datos | PostgreSQL (Neon) |
| ORM | SQLAlchemy |
| Imágenes | Cloudinary |
| Analítica | dbt-postgres |
| Despliegue | Render |

## Roles y permisos

La app tiene tres roles de usuario:

| Rol | Acceso |
|---|---|
| `admin` | Acceso total: CRUD usuarios, voluntarios, perros, turnos, visitas. Puede ejecutar dbt. |
| `junta` | Todo excepto gestión de usuarios. No puede ejecutar dbt. |
| `veterano` | Solo lectura: perros activos en refugio y su propio perfil de voluntario. |

## Modelos de datos

### Perros

- **Perro** — nombre (siempre en mayúsculas), raza (FK), fecha nacimiento, sexo, esterilizado, PPP, chip, pasaporte, color, fecha entrada, estado (`activo` / `adoptado` / `fallecido`), foto (Cloudinary URL), notas
- **Raza** — tabla normalizada de razas
- **Vacuna** — tipo, fecha administración, próxima dosis, veterinario, notas
- **Ubicacion** — tipo (`refugio` / `acogida` / `residencia` / `adoptado`), fecha inicio/fin, contacto, notas
- **PesoPerro** — fecha, peso en kg, notas
- **CeloPerro** — fecha inicio, fecha fin (nullable), notas

### Voluntarios

- **Voluntario** — nombre, apellidos, DNI, email, teléfono, perfil, fecha alta, activo, PPP, dirección, provincia, CP, contrato, teaming, notas
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

#### Estados de turno y valor en saldo

| Estado | Valor |
|---|---|
| `realizado` | 1.0 |
| `medio_turno` | 0.5 |
| `falta_justificada` | 0.0 |
| `falta_injustificada` | 0.0 |
| `no_apuntado` | 0.0 |

El saldo se calcula como `turnos_realizados − semanas_activo` desde `max(2026-04-01, fecha_alta)`.

### Visitantes

Pipeline de adopción/acogida:

`interesado` → `visita_programada` → `visita_realizada` → `se_convirtio` / `descartado`

Si se registra `fecha_visita` y ya ha pasado, el estado pasa automáticamente a `visita_realizada`. Desde el detalle del visitante se puede convertir en voluntario (redirige al formulario prefilled).

### Usuarios

- **Usuario** — username, password (hash bcrypt), nombre, rol, activo, voluntario asociado (FK nullable)

## Estructura del proyecto

```
protectora/
├── app/
│   ├── main.py              # Entrada FastAPI
│   ├── database.py          # Conexión y sesión SQLAlchemy
│   ├── models.py            # Modelos ORM
│   ├── auth.py              # Autenticación y dependencias de rol
│   ├── templates_config.py  # Configuración Jinja2
│   ├── routers/
│   │   ├── dashboard.py     # Stats y botón dbt (admin)
│   │   ├── perros.py        # CRUD perros, pesos, celos, foto, ubicación
│   │   ├── voluntarios.py   # CRUD voluntarios
│   │   ├── turnos.py        # Registro de turnos y cálculo de saldo
│   │   ├── visitas.py       # Pipeline visitantes
│   │   └── usuarios.py      # Gestión de usuarios (admin)
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── dashboard.html
│   │   ├── perros/          # list, detail (pesos + celos), form
│   │   ├── voluntarios/     # list, detail, form
│   │   ├── visitas/         # list, detail, form
│   │   └── usuarios/        # list, form
│   └── static/
├── scripts/                 # Pipeline de carga inicial de datos
│   ├── load_raw_perros.py   # xlsx → PostgreSQL schema raw
│   ├── cargar_perros.py     # mart → app (perros activos)
│   ├── cargar_vacunas.py    # staging → app (vacunas)
│   └── cargar_adoptados.py  # raw → app (perros adoptados)
└── dbt_protectora/
    ├── profiles.yml         # Target: prod (Neon)
    ├── models/
    │   ├── staging/         # Limpieza y normalización
    │   └── marts/           # Modelos de negocio
    └── tests/               # Tests SQL singulares
```

## Analítica con dbt

### Staging

- `stg_perros`, `stg_vacunas`, `stg_ubicaciones`
- `stg_voluntarios`, `stg_turnos_voluntarios` (incremental, unique_key: `id`)
- `stg_perros_entrada`, `stg_perros_adoptados` (desde xlsx)

### Marts

- `mart_vacunas_proximas` — vacunas próximas a vencer
- `mart_perros_no_esterilizados` — perros sin esterilizar
- `mart_tiempo_en_refugio` — tiempo de estancia por perro
- `mart_saldo_turnos` — saldo de turnos por voluntario
- `mart_perros_a_cargar` — estado de carga desde xlsx (`listo` / `pendiente_raza` / `pendiente_datos` / `ya_cargado`)

### Macros

- `ubicacion_actual_perro()` — ubicación vigente de cada perro (sin `fecha_fin`)

### Tests

**Genéricos** (`schema.yml`): `not_null`, `unique`, `accepted_values`, `relationships`.

**Singulares** (`tests/`):
- `vacuna_proxima_antes_de_administracion.sql`
- `perro_activo_sin_ubicacion.sql`
- `voluntario_deuda_excesiva.sql`

## Instalación y arranque

### Requisitos

- Python 3.10+
- Cuenta en Neon (PostgreSQL) o PostgreSQL local

### Puesta en marcha

```bash
git clone https://github.com/Rodry03/siempreFiel.git
cd siempreFiel

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cp .env.example .env         # Editar con las credenciales

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

## Despliegue

El despliegue es continuo en **Render** via GitHub Actions: cada push a `main` dispara el redeploy. La app local y Render comparten la misma base de datos Neon.

## Tareas habituales

### Añadir una raza

```sql
INSERT INTO razas (nombre) VALUES ('Nueva Raza');
```

### Crear un usuario administrador

```bash
python scripts/crear_usuario.py
```

### Pipeline de carga inicial desde xlsx

```bash
python scripts/load_raw_perros.py   # 1. xlsx → schema raw
cd dbt_protectora && dbt run        # 2. transformaciones
python scripts/cargar_perros.py     # 3. perros activos → app
python scripts/cargar_vacunas.py    # 4. vacunas → app
python scripts/cargar_adoptados.py  # 5. adoptados → app
```
