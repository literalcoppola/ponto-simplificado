from flask import Flask, render_template, request, redirect, session, send_file, flash, url_for
import sqlite3
import csv
import io
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "sua-chave-secreta-forte-aqui"
bcrypt = Bcrypt(app)

# --- CONFIGURAÇÃO E FUNÇÕES AUXILIARES ---

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
    return conn

def converter_para_fuso_local(utc_dt):
    if not isinstance(utc_dt, datetime):
        return ""
    fuso_local = pytz.timezone("America/Sao_Paulo")
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(fuso_local)

def calcular_horas_e_agrupar(registros):
    agrupado = defaultdict(lambda: {'registros': [], 'usuario': ''})
    for reg in registros:
        utc_dt = datetime.strptime(reg['timestamp'], '%Y-%m-%d %H:%M:%S')
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

# --- ROTAS DE LOGIN, LOGOUT E PÁGINA INICIAL ---

@app.route('/')
def index():
    return render_template("login.html")

@app.route('/login', methods=["POST"])
def login():
    usuario = request.form['usuario']
    senha = request.form['senha']
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
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
    return redirect(url_for('index'))

# --- ROTAS DO FUNCIONÁRIO ---

@app.route('/funcionario')
def funcionario():
    if 'usuario_id' not in session or session.get('is_admin'):
        return redirect(url_for('index'))
    conn = get_db()
    registros_db = conn.execute("SELECT tipo, strftime('%Y-%m-%d %H:%M:%S', timestamp) as timestamp FROM registros WHERE usuario_id = ? ORDER BY timestamp DESC LIMIT 10", (session['usuario_id'],)).fetchall()
    conn.close()
    registros_convertidos = []
    for r in registros_db:
        utc_dt = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
        hora_local = converter_para_fuso_local(utc_dt).strftime('%d/%m/%Y %H:%M:%S')
        registros_convertidos.append((r['tipo'], hora_local))
    return render_template("funcionario.html", registros=registros_convertidos, nome_usuario=session.get('usuario_nome'))

@app.route('/registrar', methods=["POST"])
def registrar():
    if 'usuario_id' not in session: return redirect(url_for('index'))
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    conn = get_db()
    ultimo = conn.execute("SELECT tipo FROM registros WHERE usuario_id = ? ORDER BY timestamp DESC LIMIT 1", (session['usuario_id'],)).fetchone()
    novo_tipo = "Entrada" if not ultimo or ultimo['tipo'] == "Saida" else "Saida"
    conn.execute("INSERT INTO registros (usuario_id, tipo, latitude, longitude) VALUES (?, ?, ?, ?)",
                   (session['usuario_id'], novo_tipo, latitude, longitude))
    conn.commit()
    conn.close()
    flash(f"'{novo_tipo}' registrada com sucesso!", "success")
    return redirect(url_for('funcionario'))

# --- ROTAS DO ADMINISTRADOR ---

@app.route('/painel')
def painel():
    if not session.get('is_admin'): return redirect(url_for('index'))
    filtro_usuario = request.args.get('filtro_usuario')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    query = "SELECT r.*, u.usuario FROM registros r JOIN usuarios u ON r.usuario_id = u.id WHERE 1=1"
    params = []
    if filtro_usuario:
        query += " AND r.usuario_id = ?"
        params.append(filtro_usuario)
    if data_inicio:
        query += " AND date(r.timestamp) >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND date(r.timestamp) <= ?"
        params.append(data_fim)
    query += " ORDER BY r.timestamp DESC"
    conn = get_db()
    registros_db = conn.execute(query, params).fetchall()
    usuarios_para_filtro = conn.execute("SELECT id, usuario FROM usuarios WHERE is_admin = 0 ORDER BY usuario").fetchall()
    conn.close()
    registros_agrupados = calcular_horas_e_agrupar(registros_db)
    return render_template("painel.html",
                           registros_agrupados=registros_agrupados,
                           usuarios_para_filtro=usuarios_para_filtro,
                           nome_usuario=session.get('usuario_nome'))

@app.route('/gerenciar_usuarios')
def gerenciar_usuarios():
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    usuarios = conn.execute("SELECT id, usuario FROM usuarios WHERE is_admin = 0 ORDER BY usuario").fetchall()
    conn.close()
    return render_template("gerenciar_usuarios.html", usuarios=usuarios)

@app.route('/adicionar_usuario', methods=["POST"])
def adicionar_usuario():
    if not session.get('is_admin'): return redirect(url_for('index'))
    usuario = request.form['usuario']
    senha = request.form['senha']
    senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')
    conn = get_db()
    try:
        conn.execute("INSERT INTO usuarios (usuario, senha, is_admin) VALUES (?, ?, ?)", (usuario, senha_hash, 0))
        conn.commit()
        flash(f"Usuário '{usuario}' adicionado com sucesso!", "success")
    except sqlite3.IntegrityError:
        flash(f"Erro: Usuário '{usuario}' já existe.", "danger")
    finally:
        conn.close()
    return redirect(url_for('gerenciar_usuarios'))

@app.route('/editar_usuario/<int:usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    if request.method == 'POST':
        novo_nome = request.form['usuario']
        nova_senha = request.form['senha']
        if nova_senha:
            senha_hash = bcrypt.generate_password_hash(nova_senha).decode('utf-8')
            conn.execute("UPDATE usuarios SET usuario = ?, senha = ? WHERE id = ?", (novo_nome, senha_hash, usuario_id))
        else:
            conn.execute("UPDATE usuarios SET usuario = ? WHERE id = ?", (novo_nome, usuario_id))
        conn.commit()
        conn.close()
        flash(f"Usuário '{novo_nome}' atualizado com sucesso!", "success")
        return redirect(url_for('gerenciar_usuarios'))
    usuario = conn.execute("SELECT id, usuario FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    conn.close()
    if not usuario: return redirect(url_for('gerenciar_usuarios'))
    return render_template("editar_usuario.html", usuario=usuario)

@app.route('/excluir_usuario/<int:usuario_id>', methods=['POST'])
def excluir_usuario(usuario_id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    conn = get_db()
    conn.execute("DELETE FROM registros WHERE usuario_id = ?", (usuario_id,))
    conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    flash("Usuário e todos os seus registros foram excluídos com sucesso.", "success")
    return redirect(url_for('gerenciar_usuarios'))
    
@app.route('/exportar')
def exportar():
    if not session.get('is_admin'): return redirect(url_for('index'))
    # Reutiliza a lógica de filtros da rota do painel
    filtro_usuario = request.args.get('filtro_usuario')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    query = "SELECT u.usuario, strftime('%Y-%m-%d %H:%M:%S', r.timestamp) as timestamp, r.tipo, r.latitude, r.longitude FROM registros r JOIN usuarios u ON r.usuario_id = u.id WHERE 1=1"
    params = []
    if filtro_usuario:
        query += " AND r.usuario_id = ?"
        params.append(filtro_usuario)
    if data_inicio:
        query += " AND date(r.timestamp) >= ?"
        params.append(data_inicio)
    if data_fim:
        query += " AND date(r.timestamp) <= ?"
        params.append(data_fim)
    query += " ORDER BY u.usuario, r.timestamp"
    conn = get_db()
    registros_db = conn.execute(query, params).fetchall()
    conn.close()
    registros_local = []
    for r in registros_db:
        utc_dt = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
        hora_local = converter_para_fuso_local(utc_dt).strftime('%d/%m/%Y %H:%M:%S')
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
    app.run(host='0.0.0.0', debug=True)