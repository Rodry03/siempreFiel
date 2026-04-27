import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal, init_db
from app.models import Usuario, RolUsuario
from app.auth import hash_password


def main():
    init_db()
    db = SessionLocal()
    try:
        username = input("Username: ").strip()
        if not username:
            print("El username no puede estar vacío.")
            return
        if db.query(Usuario).filter(Usuario.username == username).first():
            print(f"El usuario '{username}' ya existe.")
            return

        password = input("Contraseña: ").strip()
        if not password:
            print("La contraseña no puede estar vacía.")
            return

        nombre = input("Nombre visible: ").strip()
        rol_input = input("Rol (admin/editor) [admin]: ").strip().lower() or "admin"
        if rol_input not in ("admin", "editor"):
            print("Rol inválido. Usa 'admin' o 'editor'.")
            return

        usuario = Usuario(
            username=username,
            password_hash=hash_password(password),
            nombre=nombre or username,
            rol=RolUsuario(rol_input),
            activo=True,
        )
        db.add(usuario)
        db.commit()
        print(f"\nUsuario '{username}' creado con rol '{rol_input}'.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
