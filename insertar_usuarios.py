from app.database import SessionLocal
from app.models import Usuario, RolUsuario
from app.auth import hash_password

usuarios = [
    {"nombre": "Estela",    "username": "estela",     "password": "estelasiemprefiel123"},
    {"nombre": "Guillermo", "username": "guillermoc", "password": "guillermocsiemprefiel123"},
    {"nombre": "Izadi",     "username": "izadim",     "password": "izadimsiemprefiel123"},
    {"nombre": "Mer",       "username": "merv",       "password": "mervsiemprefiel123"},
    {"nombre": "Miguel",    "username": "migueld",    "password": "migueldsiemprefiel123"},
    {"nombre": "Rafa",      "username": "rafac",      "password": "rafacsiemprefiel123"},
    {"nombre": "Rocío",     "username": "rocioc",     "password": "rociocsiemprefiel123"},
    {"nombre": "Sandra",    "username": "sandra",     "password": "sandrasiemprefiel123"},
    {"nombre": "Sara",      "username": "saramd",     "password": "saramdsiemprefiel123"},
    {"nombre": "Sofía",     "username": "sofiarm",    "password": "sofiarmsiemprefiel123"},
]

db = SessionLocal()
try:
    creados = 0
    for u in usuarios:
        existe = db.query(Usuario).filter(Usuario.username == u["username"]).first()
        if existe:
            print(f"  OMITIDO (ya existe): {u['username']}")
            continue
        db.add(Usuario(
            username=u["username"],
            password_hash=hash_password(u["password"]),
            nombre=u["nombre"],
            rol=RolUsuario.veterano,
            activo=True,
        ))
        creados += 1
        print(f"  Creado: {u['username']} ({u['nombre']})")
    db.commit()
    print(f"\n{creados} usuario(s) creado(s).")
finally:
    db.close()
