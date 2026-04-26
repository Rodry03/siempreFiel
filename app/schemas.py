from datetime import date
from typing import Optional
from pydantic import BaseModel, EmailStr


class PerroForm(BaseModel):
    nombre: str
    raza: str
    fecha_nacimiento: Optional[date] = None
    sexo: str
    esterilizado: bool = False
    num_chip: Optional[str] = None
    color: Optional[str] = None
    fecha_entrada: date
    estado: str = "activo"
    notas: Optional[str] = None


class VacunaForm(BaseModel):
    tipo: str
    fecha_administracion: date
    fecha_proxima: Optional[date] = None
    veterinario: Optional[str] = None
    notas: Optional[str] = None


class UbicacionForm(BaseModel):
    tipo: str
    fecha_inicio: date
    nombre_contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None
    notas: Optional[str] = None


class VoluntarioForm(BaseModel):
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str] = None
    perfil: str
    fecha_alta: date
    activo: bool = True
    notas: Optional[str] = None


class TurnoVoluntarioForm(BaseModel):
    fecha: date
    franja: str
    estado: str
    notas: Optional[str] = None
