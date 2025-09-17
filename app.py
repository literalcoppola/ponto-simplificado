import os
import sqlite3
import psycopg2
from psycopg2.extras import DictCursor
import csv
import io
from flask import Flask, render_template, request, redirect, session, send_file, flash, url_for
from flask_bcrypt import Bcrypt
from datetime import datetime
import pytz
from collections import defaultdict

app = Flask(__name__)

# --- CONFIGURAÇÃO ---
# MUITO IMPORTANTE: Lê as chaves secretas das variáveis de ambiente na Render
# Usa um valor padrão caso não encontre (para testes locais)
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-local-para-testes')
bcrypt = Bcrypt(app)

# --- FUNÇÕES AUXILIARES ---

# IMPORTANTE: Esta função agora se conecta ao PostgreSQL na Render ou ao SQLite localmente
def get_db():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        # Conexão de Produção (PostgreSQL na Render)
        conn = psycopg2.connect(db_url)
        # Permite acessar colunas por nome, como um dicionário
        conn.cursor_factory = DictCursor
    else:
        # Conexão de Desenvolvimento (SQLite local)
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
    return conn

def converter_para_fuso_local(utc_dt):
    if not isinstance(utc_dt, datetime):
        utc_dt = datetime.strptime(utc_dt, '%Y-%m-%d %H:%M:%S')
    fuso_local = pytz.timezone("America/Sao_Paulo")
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(fuso_local)

def calcular_horas_e_agrupar(registros):
    agrupado = defaultdict(lambda: {'registros': [], 'usuario': ''})
    for reg in registros:
        utc_dt = reg['timestamp']
        local_dt = converter_para_fuso_local(utc_dt)
        chave = (reg['usuario_id'], local_dt.strftime('%d/%m/%Y'))
        agrupado[chave]['usuario'] = reg['usuario']
        agrupado[chave]['registros'].append({
            'hora': local_dt.strftime('%H:%M:%S'),
            'tipo': reg['tipo'],
            'timestamp': utc_dt,
            'latitude': reg['latitude'],
            'longitude': reg['longitude']
        })
    resultado_final = {}
    for (usuario_id, dia), info in agrupado.items():
        registros_ordenados = sorted(info['registros'], key=lambda x: x['timestamp'])
        total_segundos = 0
        incompleto = False
        for i in range(0, len(registros_ordenados), 2):
            try:
                entrada = registros_ordenados[i]
                saida = registros_ordenados[i+1]
                if entrada['tipo'] == 'Entrada' and saida['tipo'] == 'Saida':
                    diferenca = saida['timestamp'] - entrada['timestamp']
                    total_segundos += diferenca.total_seconds()
                else:
                    incompleto = True
            except IndexError:
                incompleto = True
        if total_segundos > 0:
            horas = int(total_segundos // 3600)
            minutos = int((total_segundos % 3600) // 60)
            total_horas_str = f"{horas:02d}h {minutos:02d}m"
        else:
            total_horas_str = "00h 00m"
        resultado_final[dia] = {
            'usuario': info['usuario'],
            'registros': registros_ordenados,
            'total_horas': total_horas_str,
            'incompleto': incompleto
        }
    return resultado_final

# --- ROTA SECRETA PARA INICIALIZAR O BANCO DE DADOS NA NUVEM ---

@app.route('/init-db-super-secreto')
def init_db_route():
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')

    # Sintaxe SQL adaptada para PostgreSQL e SQLite
    create_user_table_sql = """
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0
    )""" if is_postgres else """
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0
    )"""
    
    create_registros_table_sql = """
    CREATE TABLE IF NOT EXISTS registros (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT CHECK(tipo IN ('Entrada','Saida')) NOT NULL,
        latitude REAL,
        longitude REAL
    )""" if is_postgres else """
    CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT CHECK(tipo IN ('Entrada','Saida')) NOT NULL,
        latitude REAL,
        longitude REAL,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
    )"""

    cursor.execute(create_user_table_sql)
    cursor.execute(create_registros_table_sql)
    
    # Criar usuário admin
    senha_hash = bcrypt.generate_password_hash("admin").decode('utf-8') # Senha inicial "admin"
    placeholder = '%s' if is_postgres else '?'
    
    # Prepara o comando de inserção para ser compatível com ambos
    insert_sql = f"INSERT INTO usuarios (usuario, senha, is_admin) VALUES ({placeholder}, {placeholder}, {placeholder})"
    if is_postgres:
        insert_sql += " ON CONFLICT (usuario) DO NOTHING"
    else: # SQLite
        insert_sql = insert_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO")

    cursor.execute(insert_sql, ("admin", senha_hash, 1))

    conn.commit()
    cursor.close()
    conn.close()
    return "Banco de dados inicializado com sucesso! O usuário 'admin' foi criado com a senha 'admin'."

# --- ROTAS DA APLICAÇÃO ---
# (O restante das rotas continua o mesmo, mas adaptado para usar a nova `get_db`)

@app.route('/')
def index():
    # ... (código existente)
    return "hello"


@app.route('/login', methods=["POST"])
def login():
    # ... (código existente)
    return "hello"


@app.route('/logout')
def logout():
    # ... (código existente)
    return "hello"


@app.route('/funcionario')
def funcionario():
    # ... (código existente)
    return "hello"


@app.route('/registrar', methods=["POST"])
def registrar():
    # ... (código existente)
    return "hello"


@app.route('/painel')
def painel():
    # ... (código existente)
    return "hello"


@app.route('/gerenciar_usuarios')
def gerenciar_usuarios():
    # ... (código existente)
    return "hello"


@app.route('/adicionar_usuario', methods=["POST"])
def adicionar_usuario():
    # ... (código existente)
    return "hello"


@app.route('/editar_usuario/<int:usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    # ... (código existente)
    return "hello"


@app.route('/excluir_usuario/<int:usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    # ... (código existente)
    return "hello"


@app.route('/exportar')
def exportar():
    # ... (código existente)
    return "hello"

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)