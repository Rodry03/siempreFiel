from datetime import date, datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class Sexo(str, enum.Enum):
    macho = "macho"
    hembra = "hembra"


class EstadoPerro(str, enum.Enum):
    libre = "libre"
    reservado = "reservado"
    adoptado = "adoptado"
    fallecido = "fallecido"


class TipoUbicacion(str, enum.Enum):
    refugio = "refugio"
    acogida = "acogida"
    residencia = "residencia"
    casa_adoptiva = "casa_adoptiva"


class PerfilVoluntario(str, enum.Enum):
    directiva = "directiva"
    apoyo_en_junta = "apoyo_en_junta"
    veterano = "veterano"
    voluntario = "voluntario"
    guagua = "guagua"
    eventos = "eventos"
    colaboradores = "colaboradores"


class EstadoContrato(str, enum.Enum):
    pendiente = "pendiente"
    enviado = "enviado"
    firmado = "firmado"


class RolUsuario(str, enum.Enum):
    admin = "admin"
    junta = "junta"
    veterano = "veterano"


class EstadoVisitante(str, enum.Enum):
    interesado = "interesado"
    visita_programada = "visita_programada"
    visita_realizada = "visita_realizada"
    se_convirtio = "se_convirtio"
    descartado = "descartado"


class FranjaTurno(str, enum.Enum):
    manana = "manana"
    tarde = "tarde"


class EstadoTurno(str, enum.Enum):
    realizado = "realizado"
    medio_turno = "medio_turno"
    falta_justificada = "falta_justificada"
    falta_injustificada = "falta_injustificada"
    no_apuntado = "no_apuntado"


class PrioridadIncidencia(str, enum.Enum):
    baja = "baja"
    media = "media"
    alta = "alta"
    urgente = "urgente"


class EstadoIncidencia(str, enum.Enum):
    pendiente = "pendiente"
    en_proceso = "en_proceso"
    resuelto = "resuelto"


class Raza(Base):
    __tablename__ = "razas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)

    perros = relationship("Perro", back_populates="raza")


class Perro(Base):
    __tablename__ = "perros"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    raza_id = Column(Integer, ForeignKey("razas.id"), nullable=False)
    fecha_nacimiento = Column(Date, nullable=True)
    sexo = Column(Enum(Sexo), nullable=False)
    esterilizado = Column(Boolean, default=False, nullable=False)
    ppp = Column(Boolean, default=False, nullable=False, server_default="false")
    num_chip = Column(String(20), unique=True, nullable=True)
    num_pasaporte = Column(String(50), unique=True, nullable=True)
    color = Column(String(100), nullable=True)
    fecha_entrada = Column(Date, nullable=False, default=date.today)
    estado = Column(Enum(EstadoPerro), default=EstadoPerro.libre, nullable=False)
    fecha_adopcion = Column(Date, nullable=True)
    fecha_reserva = Column(Date, nullable=True)
    notas = Column(Text, nullable=True)
    foto_url = Column(String, nullable=True)

    raza = relationship("Raza", back_populates="perros")
    vacunas = relationship("Vacuna", back_populates="perro", cascade="all, delete-orphan")
    ubicaciones = relationship("Ubicacion", back_populates="perro", cascade="all, delete-orphan", order_by="Ubicacion.fecha_inicio.desc()")
    pesos = relationship("PesoPerro", back_populates="perro", cascade="all, delete-orphan", order_by="PesoPerro.fecha.desc()")
    celos = relationship("CeloPerro", back_populates="perro", cascade="all, delete-orphan", order_by="CeloPerro.fecha_inicio.desc()")


class Vacuna(Base):
    __tablename__ = "vacunas"

    id = Column(Integer, primary_key=True, index=True)
    perro_id = Column(Integer, ForeignKey("perros.id"), nullable=False)
    tipo = Column(String(100), nullable=False)
    fecha_administracion = Column(Date, nullable=False)
    fecha_proxima = Column(Date, nullable=True)
    veterinario = Column(String(150), nullable=True)
    notas = Column(Text, nullable=True)

    perro = relationship("Perro", back_populates="vacunas")


class Ubicacion(Base):
    __tablename__ = "ubicaciones"

    id = Column(Integer, primary_key=True, index=True)
    perro_id = Column(Integer, ForeignKey("perros.id"), nullable=False)
    tipo = Column(Enum(TipoUbicacion), nullable=False)
    fecha_inicio = Column(Date, nullable=False, default=date.today)
    fecha_fin = Column(Date, nullable=True)
    nombre_contacto = Column(String(150), nullable=True)
    telefono_contacto = Column(String(30), nullable=True)
    notas = Column(Text, nullable=True)

    perro = relationship("Perro", back_populates="ubicaciones")


class Voluntario(Base):
    __tablename__ = "voluntarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    dni = Column(String(20), unique=True, nullable=True)
    email = Column(String(200), unique=True, nullable=False)
    telefono = Column(String(30), nullable=True)
    perfil = Column(Enum(PerfilVoluntario), nullable=False)
    fecha_alta = Column(Date, nullable=False, default=date.today)
    activo = Column(Boolean, default=True, nullable=False)
    ppp = Column(Boolean, default=False, nullable=False)
    direccion = Column(String(200), nullable=True)
    ciudad = Column(String(100), nullable=True)
    provincia = Column(String(100), nullable=True)
    codigo_postal = Column(String(10), nullable=True)
    fecha_contrato = Column(Date, nullable=True)
    contrato_estado = Column(Enum(EstadoContrato), nullable=True)
    teaming = Column(Boolean, default=False, nullable=False)
    notas = Column(Text, nullable=True)

    deuda_inicial = Column(Float, default=0.0, nullable=False)
    recuperar_turnos_urgentes = Column(Float, default=0.0, nullable=False)
    saldo_manual = Column(Float, nullable=True)

    turnos = relationship("TurnoVoluntario", back_populates="voluntario", cascade="all, delete-orphan", order_by="TurnoVoluntario.fecha.desc()")
    turnos_mensuales = relationship("TurnoMensual", back_populates="voluntario", cascade="all, delete-orphan", order_by="TurnoMensual.mes.desc()")


class GrupoTarea(Base):
    __tablename__ = "grupos_tarea"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(100), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)
    capitan_id  = Column(Integer, ForeignKey("voluntarios.id"), nullable=True)

    capitan    = relationship("Voluntario", foreign_keys=[capitan_id])
    miembros   = relationship("MiembroGrupoTarea", back_populates="grupo", cascade="all, delete-orphan")
    ejecuciones = relationship("EjecucionGrupoTarea", back_populates="grupo", cascade="all, delete-orphan",
                               order_by="EjecucionGrupoTarea.semana.desc()")


class MiembroGrupoTarea(Base):
    __tablename__ = "miembros_grupo_tarea"

    id            = Column(Integer, primary_key=True, index=True)
    grupo_id      = Column(Integer, ForeignKey("grupos_tarea.id"), nullable=False)
    voluntario_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=False)

    grupo      = relationship("GrupoTarea", back_populates="miembros")
    voluntario = relationship("Voluntario")


class EjecucionGrupoTarea(Base):
    __tablename__ = "ejecuciones_grupo_tarea"

    id          = Column(Integer, primary_key=True, index=True)
    grupo_id    = Column(Integer, ForeignKey("grupos_tarea.id"), nullable=False)
    semana      = Column(Date, nullable=False)
    realizado   = Column(Boolean, default=False, nullable=False)
    ejecutor_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=True)
    notas       = Column(Text, nullable=True)

    grupo    = relationship("GrupoTarea", back_populates="ejecuciones")
    ejecutor = relationship("Voluntario", foreign_keys=[ejecutor_id])


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(Enum(RolUsuario), nullable=False, default=RolUsuario.junta)
    activo = Column(Boolean, default=True, nullable=False)
    voluntario_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=True)

    voluntario = relationship("Voluntario", foreign_keys=[voluntario_id])


class Visitante(Base):
    __tablename__ = "visitantes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
    telefono = Column(String(30), nullable=True)
    fecha_contacto = Column(Date, nullable=False, default=date.today)
    fecha_visita = Column(Date, nullable=True)
    estado = Column(Enum(EstadoVisitante), nullable=False, default=EstadoVisitante.interesado)
    notas = Column(Text, nullable=True)


class TurnoVoluntario(Base):
    __tablename__ = "turnos_voluntarios"

    id = Column(Integer, primary_key=True, index=True)
    voluntario_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    franja = Column(Enum(FranjaTurno), nullable=False)
    estado = Column(Enum(EstadoTurno), nullable=False)
    notas = Column(Text, nullable=True)

    voluntario = relationship("Voluntario", back_populates="turnos")


class TurnoMensual(Base):
    __tablename__ = "turnos_mensuales"

    id            = Column(Integer, primary_key=True, index=True)
    voluntario_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=False)
    mes           = Column(Date, nullable=False)
    turnos        = Column(Float, nullable=False, default=0.0)

    voluntario = relationship("Voluntario", back_populates="turnos_mensuales")

    __table_args__ = (UniqueConstraint("voluntario_id", "mes", name="uq_turno_mensual"),)


class NotaGestion(Base):
    __tablename__ = "notas_gestion"

    id             = Column(Integer, primary_key=True, index=True)
    texto          = Column(Text, nullable=False)
    fecha_limite   = Column(Date, nullable=True)
    encargado_id   = Column(Integer, ForeignKey("voluntarios.id"), nullable=True)
    hecha          = Column(Boolean, default=False, nullable=False)
    fecha_creacion = Column(Date, nullable=False, default=date.today)

    encargado = relationship("Voluntario", foreign_keys=[encargado_id])


class PesoPerro(Base):
    __tablename__ = "pesos_perro"

    id = Column(Integer, primary_key=True, index=True)
    perro_id = Column(Integer, ForeignKey("perros.id"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    peso_kg = Column(Float, nullable=False)
    notas = Column(Text, nullable=True)

    perro = relationship("Perro", back_populates="pesos")


class CeloPerro(Base):
    __tablename__ = "celos_perro"

    id = Column(Integer, primary_key=True, index=True)
    perro_id = Column(Integer, ForeignKey("perros.id"), nullable=False)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=True)
    notas = Column(Text, nullable=True)

    perro = relationship("Perro", back_populates="celos")


class SaldoMensual(Base):
    __tablename__ = "saldos_mensuales"

    id            = Column(Integer, primary_key=True, index=True)
    voluntario_id = Column(Integer, ForeignKey("voluntarios.id"), nullable=False)
    mes           = Column(Date, nullable=False)
    saldo         = Column(Float, nullable=False)

    voluntario = relationship("Voluntario")

    __table_args__ = (UniqueConstraint("voluntario_id", "mes", name="uq_saldo_mensual"),)


class SesionUsuario(Base):
    __tablename__ = "sesiones_usuario"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_inicio = Column(DateTime, nullable=False, default=datetime.utcnow)
    fecha_fin = Column(DateTime, nullable=True)
    ip = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    usuario = relationship("Usuario")


class IncidenciaInstalacion(Base):
    __tablename__ = "incidencias_instalacion"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    zona = Column(String(100), nullable=True)
    prioridad = Column(Enum(PrioridadIncidencia), nullable=False, default=PrioridadIncidencia.media)
    estado = Column(Enum(EstadoIncidencia), nullable=False, default=EstadoIncidencia.pendiente)
    fecha_reporte = Column(Date, nullable=False, default=date.today)
    reportado_por = Column(String(150), nullable=True)
    fecha_resolucion = Column(Date, nullable=True)
    resuelto_por = Column(String(150), nullable=True)
    notas_resolucion = Column(Text, nullable=True)
    coste = Column(Float, nullable=True)
