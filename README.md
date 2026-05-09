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

| Rol | Acceso |
|---|---|
| `admin` | Acceso total: CRUD usuarios, voluntarios, perros, turnos, visitas. Puede ejecutar dbt. |
| `junta` | Todo excepto gestión de usuarios. No puede ejecutar dbt. |
| `veterano` | Solo lectura: perros en refugio bajo gestión y su propio perfil de voluntario. |

## Modelos de datos

### Perros

- **Perro** — nombre (siempre en mayúsculas), raza (FK), fecha nacimiento, sexo, esterilizado, PPP, chip, pasaporte, color, fecha entrada, **estado**, **fecha_adopcion**, **fecha_reserva**, foto (Cloudinary URL), notas
- **Raza** — tabla normalizada de razas
- **Vacuna** — tipo (desplegable con tipos predefinidos), fecha administración, próxima dosis (auto +1 año), veterinario, notas
- **Ubicacion** — tipo (`refugio` / `acogida` / `residencia` / `casa_adoptiva`), fecha inicio/fin, contacto, notas
- **PesoPerro** — fecha, peso en kg, notas
- **CeloPerro** — fecha inicio, fecha fin, notas

#### Estados del perro

| Estado | Significado | Bajo gestión |
|---|---|---|
| `libre` | En la protectora, nadie interesado | Sí |
| `reservado` | Reservado por alguien | Sí |
| `adoptado` | Adoptado (puede ser devuelto) | No |
| `fallecido` | Fallecido | No |

**"Activo"** (bajo gestión) se deriva: `estado in ('libre', 'reservado')`.

#### Sincronización estado ↔ ubicación

Estado y ubicación se sincronizan automáticamente:
- Cambiar ubicación a `casa_adoptiva` → estado pasa a `adoptado`
- Guardar estado `adoptado` sin `casa_adoptiva` → se crea registro `casa_adoptiva` automáticamente
- Volver a ubicación física (refugio/acogida/residencia) → estado vuelve a `libre`

#### Auto-adopción de reservados

Los perros con `estado=reservado` pasan automáticamente a `adoptado` al cabo de 30 días. El campo `fecha_reserva` registra cuándo se marcó como reservado. La comprobación se ejecuta cada vez que un usuario junta/admin carga la lista de perros.

### Voluntarios

- **Voluntario** — nombre, apellidos, DNI, email, teléfono, perfil, fecha alta, activo, PPP, dirección, provincia, CP, contrato, teaming, notas
- **TurnoVoluntario** — fecha, franja (`manana` / `tarde`), estado

#### Perfiles de voluntario

| Perfil | Hace turnos | Nota |
|---|---|---|
| `veterano` | Sí | Cuenta como cobertura veterana |
| `apoyo_en_junta` | Sí | Cuenta como cobertura veterana; semanas de apoyo son neutras en saldo |
| `voluntario` | Sí | — |
| `directiva` | No | — |
| `guagua` | No | — |
| `eventos` | No | — |
| `colaboradores` | No | — |

#### Saldo de turnos

| Estado | Valor |
|---|---|
| `realizado` | 1.0 |
| `medio_turno` | 0.5 |
| `falta_justificada` | 0.0 |
| `falta_injustificada` | 0.0 |
| `no_apuntado` | 0.0 |

Saldo in-app = `turnos_realizados − semanas_activo` desde `max(2026-04-01, fecha_alta)`.

El mart dbt `mart_saldo_turnos_semanal` usa `COALESCE(fecha_veterano, fecha_alta)` como inicio del grid y neutraliza las semanas cubiertas por un `PeriodoApoyo` (saldo = 0 en esas semanas).

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
│   │   ├── dashboard.py     # Stats, botón dbt (admin), drill-down entradas/adopciones y conversión visitantes
│   │   ├── perros.py        # CRUD perros, pesos, celos, vacunas, foto, ubicación, auto-adopción reservados
│   │   ├── voluntarios.py   # CRUD voluntarios
│   │   ├── turnos.py        # Perfil voluntario + registro de turnos. Prefix: /voluntarios
│   │   ├── turnos_admin.py  # Gestión centralizada de turnos (junta/admin). Prefix: /turnos
│   │   ├── visitas.py       # Pipeline visitantes
│   │   └── usuarios.py      # Gestión de usuarios (admin)
│   └── templates/
│       ├── base.html        # Sidebar (verde #31ae90), Nunito, fondo #eef4f2
│       ├── login.html       # Fondo gradiente verde marca
│       ├── dashboard.html   # Charts con drill-down al clicar mes/barra (entradas, adopciones, visitantes)
│       ├── perros/          # list (35/pág, tabs, orden preservado), detail (vacunas CRUD, edición ubicaciones), form
│       ├── voluntarios/     # list, detail (turnos históricos), form
│       ├── turnos/          # list (vista semanal, CRUD turnos)
│       ├── visitas/         # list, detail, form
│       └── usuarios/        # list, form
└── dbt_protectora/
    ├── profiles.yml         # Target: prod (Neon)
    └── models/
        ├── staging/         # Limpieza y normalización
        └── marts/           # Modelos de negocio
```

## Analítica con dbt

### Staging

- `stg_perros` — perros bajo gestión (`estado in ('libre', 'reservado')`)
- `stg_voluntarios`, `stg_turnos_voluntarios`

### Marts

| Mart | Descripción | Materialización |
|---|---|---|
| `mart_entradas_salidas_por_mes` | Entradas vs adopciones por mes (usa `perros.fecha_adopcion`) | tabla |
| `mart_tiempo_adopcion` | Días medios hasta adopción por mes | tabla |
| `mart_patrones_dificultad` | Días medios hasta adopción por factor (sexo, PPP, edad, esterilizado) | tabla |
| `mart_perros_sin_adoptar` | Perros libres con más tiempo esperando (alertas crítico/atención) | tabla |
| `mart_vacunas_proximas` | Vacunas próximas a vencer o vencidas (solo activos) | **vista** |
| `mart_perros_no_esterilizados` | Perros activos sin esterilizar | **vista** |
| `mart_saldo_turnos` | Saldo de turnos por voluntario | tabla |
| `mart_saldo_turnos_semanal` | Saldo semanal por voluntario (usa `fecha_veterano` + `periodos_apoyo`). Alimenta `mart_evolucion_saldo_semanal`. | tabla |
| `mart_cobertura_semanal` | Cobertura semanal: slots cubiertos por veterano/apoyo_en_junta vs sin cubrir (últimos 8 meses) | tabla |
| `mart_faltas_voluntario` | Faltas e incumplimientos por voluntario | tabla |
| `mart_tiempo_acogida_mes` | Días medios que los perros pasan en acogida por mes | tabla |
| `mart_conversion_visitantes` | Tasa de conversión visitante → voluntario por mes | tabla |
| `mart_evolucion_saldo_semanal` | Saldo medio agregado por semana (últimos 8 meses) | tabla |

Los marts marcados como **vista** reflejan datos en tiempo real sin necesidad de ejecutar `dbt run`.

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

### Variables de entorno

```
DATABASE_URL=postgresql://...
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

### Ejecutar dbt

El target por defecto es `prod` (Neon). Requiere las 4 variables de entorno:

```bash
cd dbt_protectora

# Windows PowerShell — prod (Neon)
$env:DBT_NEON_HOST="<host>"; $env:DBT_NEON_USER="<user>"; $env:DBT_NEON_PASSWORD="<pass>"; $env:DBT_NEON_DBNAME="<db>"; dbt run

# Solo un modelo
... dbt run --select mart_cobertura_semanal

# Dev (PostgreSQL local)
$env:DBT_PASSWORD="<pass>"; dbt run --target dev
```

## Despliegue

Despliegue continuo en **Render** via GitHub Actions: cada push a `main` dispara el redeploy. La app local y Render comparten la misma base de datos Neon.

## Tareas habituales

### Añadir una raza

```sql
INSERT INTO razas (nombre) VALUES ('Nueva Raza');
```

### Modificar un enum de PostgreSQL

```sql
ALTER TYPE nombre_enum RENAME VALUE 'old' TO 'new';
ALTER TYPE nombre_enum ADD VALUE 'new_value';
-- Nota: no se pueden eliminar valores de un enum sin recrear el tipo
```
