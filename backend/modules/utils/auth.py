
import bcrypt

def hash_password(password):
    # Gera um salt e hasheia a senha
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")

def check_password(password, hashed_password):
    # Verifica se a senha fornecida corresponde ao hash
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


