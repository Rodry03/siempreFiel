from datetime import date
from sqlalchemy import Boolean, Column, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class Sexo(str, enum.Enum):
    macho = "macho"
    hembra = "hembra"


class EstadoPerro(str, enum.Enum):
    activo = "activo"
    adoptado = "adoptado"
    fallecido = "fallecido"


class TipoUbicacion(str, enum.Enum):
    refugio = "refugio"
    acogida = "acogida"
    residencia = "residencia"
    adoptado = "adoptado"


class PerfilVoluntario(str, enum.Enum):
    directiva = "directiva"
    veterano = "veterano"
    voluntario = "voluntario"
    guagua = "guagua"
    eventos = "eventos"
    colaboradores = "colaboradores"


class RolUsuario(str, enum.Enum):
    admin = "admin"
    editor = "editor"


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
    num_chip = Column(String(20), unique=True, nullable=True)
    num_pasaporte = Column(String(50), unique=True, nullable=True)
    color = Column(String(100), nullable=True)
    fecha_entrada = Column(Date, nullable=False, default=date.today)
    estado = Column(Enum(EstadoPerro), default=EstadoPerro.activo, nullable=False)
    notas = Column(Text, nullable=True)

    raza = relationship("Raza", back_populates="perros")
    vacunas = relationship("Vacuna", back_populates="perro", cascade="all, delete-orphan")
    ubicaciones = relationship("Ubicacion", back_populates="perro", cascade="all, delete-orphan", order_by="Ubicacion.fecha_inicio.desc()")


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
    notas = Column(Text, nullable=True)

    turnos = relationship("TurnoVoluntario", back_populates="voluntario", cascade="all, delete-orphan", order_by="TurnoVoluntario.fecha.desc()")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(Enum(RolUsuario), nullable=False, default=RolUsuario.editor)
    activo = Column(Boolean, default=True, nullable=False)


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
