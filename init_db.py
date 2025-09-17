import sqlite3
from flask_bcrypt import Bcrypt
from flask import Flask

app = Flask(__name__)
bcrypt = Bcrypt(app)

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Criar tabelas
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    senha TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    tipo TEXT CHECK(tipo IN ('Entrada','Saida')) NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
)
""")

# Criar usuário admin com senha criptografada
senha_hash = bcrypt.generate_password_hash("1234").decode('utf-8')
cursor.execute("INSERT OR IGNORE INTO usuarios (usuario, senha, is_admin) VALUES (?, ?, ?)", 
               ("admin", senha_hash, 1))

conn.commit()
conn.close()
print("Banco de dados inicializado com sucesso!")
