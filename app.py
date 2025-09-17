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
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-local-para-testes')
bcrypt = Bcrypt(app)

# --- FUNÇÕES AUXILIARES ---

def get_db():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        conn = psycopg2.connect(db_url)
        conn.cursor_factory = DictCursor
    else:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
    return conn

def converter_para_fuso_local(utc_dt):
    if not isinstance(utc_dt, datetime):
        try:
            # Tenta converter de string, se necessário
            utc_dt = datetime.strptime(str(utc_dt), '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
             return utc_dt
    fuso_local = pytz.timezone("America/Sao_Paulo")
    utc_tz = pytz.utc
    # Garante que o datetime tenha um fuso horário antes de converter
    if utc_dt.tzinfo is None:
        utc_dt = utc_tz.localize(utc_dt)
    return utc_dt.astimezone(fuso_local)

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
    # Ordena os dias do mais recente para o mais antigo
    sorted_keys = sorted(agrupado.keys(), key=lambda k: datetime.strptime(k[1], '%d/%m/%Y'), reverse=True)
    for chave in sorted_keys:
        dia = chave[1]
        info = agrupado[chave]
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
        total_horas_str = "00h 00m"
        if total_segundos > 0:
            horas = int(total_segundos // 3600)
            minutos = int((total_segundos % 3600) // 60)
            total_horas_str = f"{horas:02d}h {minutos:02d}m"
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
    create_user_table_sql = "CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, senha TEXT NOT NULL, is_admin INTEGER DEFAULT 0)" if is_postgres else "CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE NOT NULL, senha TEXT NOT NULL, is_admin INTEGER DEFAULT 0)"
    create_registros_table_sql = "CREATE TABLE IF NOT EXISTS registros (id SERIAL PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE, timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, tipo TEXT CHECK(tipo IN ('Entrada','Saida')) NOT NULL, latitude REAL, longitude REAL)" if is_postgres else "CREATE TABLE IF NOT EXISTS registros (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, tipo TEXT CHECK(tipo IN ('Entrada','Saida')) NOT NULL, latitude REAL, longitude REAL, FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE)"
    cursor.execute(create_user_table_sql)
    cursor.execute(create_registros_table_sql)
    senha_hash = bcrypt.generate_password_hash("admin").decode('utf-8')
    placeholder = '%s' if is_postgres else '?'
    insert_sql_start = "INSERT INTO usuarios (usuario, senha, is_admin)"
    insert_sql_values = f" VALUES ({placeholder}, {placeholder}, {placeholder})"
    if is_postgres:
        insert_sql = insert_sql_start + insert_sql_values + " ON CONFLICT (usuario) DO NOTHING"
    else:
        insert_sql = "INSERT OR IGNORE INTO usuarios (usuario, senha, is_admin)" + insert_sql_values
    cursor.execute(insert_sql, ("admin", senha_hash, 1))
    conn.commit()
    cursor.close()
    conn.close()
    return "Banco de dados inicializado com sucesso! O usuário 'admin' foi criado com a senha 'admin'."

# --- ROTAS DA APLICAÇÃO ---

@app.route('/')
def index():
    if 'usuario_id' in session:
        return redirect(url_for('painel') if session.get('is_admin') else url_for('funcionario'))
    return render_template("login.html")

@app.route('/login', methods=["POST"])
def login():
    usuario = request.form['usuario']
    senha = request.form['senha']
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    cursor.execute(f"SELECT * FROM usuarios WHERE usuario = {placeholder}", (usuario,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user and bcrypt.check_password_hash(user['senha'], senha):
        session['usuario_id'] = user['id']
        session['usuario_nome'] = user['usuario']
        session['is_admin'] = user['is_admin']
        return redirect(url_for('painel') if user['is_admin'] else url_for('funcionario'))
    else:
        flash("Usuário ou senha inválidos!", "danger")
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Você saiu com sucesso.", "success")
    return redirect(url_for('index'))

@app.route('/funcionario')
def funcionario():
    if 'usuario_id' not in session or session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    cursor.execute(f"SELECT tipo, timestamp FROM registros WHERE usuario_id = {placeholder} ORDER BY timestamp DESC LIMIT 10", (session['usuario_id'],))
    registros_db = cursor.fetchall()
    cursor.close()
    conn.close()
    registros_convertidos = []
    for r in registros_db:
        hora_local = converter_para_fuso_local(r['timestamp']).strftime('%d/%m/%Y %H:%M:%S')
        registros_convertidos.append({'tipo': r['tipo'], 'hora': hora_local})
    return render_template("funcionario.html", registros=registros_convertidos, nome_usuario=session.get('usuario_nome'))

@app.route('/registrar', methods=["POST"])
def registrar():
    if 'usuario_id' not in session: return redirect(url_for('index'))
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    cursor.execute(f"SELECT tipo FROM registros WHERE usuario_id = {placeholder} ORDER BY timestamp DESC LIMIT 1", (session['usuario_id'],))
    ultimo = cursor.fetchone()
    novo_tipo = "Entrada" if not ultimo or ultimo['tipo'] == "Saida" else "Saida"
    cursor.execute(f"INSERT INTO registros (usuario_id, tipo, latitude, longitude) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})", (session['usuario_id'], novo_tipo, latitude, longitude))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"'{novo_tipo}' registrada com sucesso!", "success")
    return redirect(url_for('funcionario'))

@app.route('/painel')
def painel():
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    filtro_usuario = request.args.get('filtro_usuario')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    query = "SELECT r.*, u.usuario FROM registros r JOIN usuarios u ON r.usuario_id = u.id WHERE 1=1"
    params = []
    if filtro_usuario:
        query += f" AND r.usuario_id = {'%s' if is_postgres else '?'}"
        params.append(int(filtro_usuario))
    if data_inicio:
        query += f" AND date(r.timestamp) >= {'%s' if is_postgres else '?'}"
        params.append(data_inicio)
    if data_fim:
        query += f" AND date(r.timestamp) <= {'%s' if is_postgres else '?'}"
        params.append(data_fim)
    query += " ORDER BY r.timestamp DESC"
    cursor.execute(query, params)
    registros_db = cursor.fetchall()
    cursor.execute("SELECT id, usuario FROM usuarios WHERE is_admin = 0 ORDER BY usuario")
    usuarios_para_filtro = cursor.fetchall()
    cursor.close()
    conn.close()
    registros_agrupados = calcular_horas_e_agrupar(registros_db)
    return render_template("painel.html", registros_agrupados=registros_agrupados, usuarios_para_filtro=usuarios_para_filtro, nome_usuario=session.get('usuario_nome'))

@app.route('/gerenciar_usuarios')
def gerenciar_usuarios():
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, usuario FROM usuarios WHERE is_admin = 0 ORDER BY usuario")
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("gerenciar_usuarios.html", usuarios=usuarios)

@app.route('/adicionar_usuario', methods=["POST"])
def adicionar_usuario():
    if not session.get('is_admin'): return redirect(url_for('index'))
    usuario = request.form['usuario']
    senha = request.form['senha']
    if not senha:
        flash("O campo de senha não pode ser vazio.", "danger")
        return redirect(url_for('gerenciar_usuarios'))
    senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    insert_sql_start = "INSERT INTO usuarios (usuario, senha, is_admin)"
    insert_sql_values = f" VALUES ({placeholder}, {placeholder}, {placeholder})"
    if is_postgres:
        insert_sql = insert_sql_start + insert_sql_values + " ON CONFLICT (usuario) DO NOTHING"
    else:
        insert_sql = "INSERT OR IGNORE INTO usuarios (usuario, senha, is_admin)" + insert_sql_values
    try:
        cursor.execute(insert_sql, (usuario, senha_hash, 0))
        conn.commit()
        if cursor.rowcount > 0:
            flash(f"Usuário '{usuario}' adicionado com sucesso!", "success")
        else:
            flash(f"Erro: Usuário '{usuario}' já existe.", "danger")
    except Exception as e:
        flash(f"Ocorreu um erro: {e}", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/editar_usuario/<int:usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    if request.method == 'POST':
        novo_nome = request.form['usuario']
        nova_senha = request.form['senha']
        if nova_senha:
            senha_hash = bcrypt.generate_password_hash(nova_senha).decode('utf-8')
            cursor.execute(f"UPDATE usuarios SET usuario = {placeholder}, senha = {placeholder} WHERE id = {placeholder}", (novo_nome, senha_hash, usuario_id))
        else:
            cursor.execute(f"UPDATE usuarios SET usuario = {placeholder} WHERE id = {placeholder}", (novo_nome, usuario_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Usuário '{novo_nome}' atualizado com sucesso!", "success")
        return redirect(url_for('gerenciar_usuarios'))
    cursor.execute(f"SELECT id, usuario FROM usuarios WHERE id = {placeholder}", (usuario_id,))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()
    if not usuario: return redirect(url_for('gerenciar_usuarios'))
    return render_template("editar_usuario.html", usuario=usuario)

@app.route('/excluir_usuario/<int:usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    placeholder = '%s' if is_postgres else '?'
    cursor.execute(f"DELETE FROM registros WHERE usuario_id = {placeholder}", (usuario_id,))
    cursor.execute(f"DELETE FROM usuarios WHERE id = {placeholder}", (usuario_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Usuário e todos os seus registros foram excluídos com sucesso.", "success")
    return redirect(url_for('gerenciar_usuarios'))
    
@app.route('/exportar')
def exportar():
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = hasattr(conn, 'cursor_factory')
    filtro_usuario = request.args.get('filtro_usuario')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    query = "SELECT u.usuario, r.timestamp, r.tipo, r.latitude, r.longitude FROM registros r JOIN usuarios u ON r.usuario_id = u.id WHERE 1=1"
    params = []
    if filtro_usuario:
        query += f" AND r.usuario_id = {'%s' if is_postgres else '?'}"
        params.append(int(filtro_usuario))
    if data_inicio:
        query += f" AND date(r.timestamp) >= {'%s' if is_postgres else '?'}"
        params.append(data_inicio)
    if data_fim:
        query += f" AND date(r.timestamp) <= {'%s' if is_postgres else '?'}"
        params.append(data_fim)
    query += " ORDER BY u.usuario, r.timestamp"
    cursor.execute(query, params)
    registros_db = cursor.fetchall()
    cursor.close()
    conn.close()
    registros_local = []
    for r in registros_db:
        hora_local = converter_para_fuso_local(r['timestamp']).strftime('%d/%m/%Y %H:%M:%S')
        registros_local.append((r['usuario'], hora_local, r['tipo'], r['latitude'], r['longitude']))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Usuário", "Data/Hora", "Tipo", "Latitude", "Longitude"])
    writer.writerows(registros_local)
    output.seek(0)
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    output.close()
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="relatorio_ponto.csv")

# --- INICIAR APLICAÇÃO ---
if __name__ == "__main__":
    app.run(debug=True)