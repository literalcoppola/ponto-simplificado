import sqlite3

DATABASE = 'database.db'

def update_schema():
    conn = None 
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        print("Conectado ao banco de dados.")
        try:
            cursor.execute("ALTER TABLE registros ADD COLUMN latitude REAL")
            print("Coluna 'latitude' adicionada com sucesso.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("Coluna 'latitude' já existe.")
            else:
                raise 

        try:
            cursor.execute("ALTER TABLE registros ADD COLUMN longitude REAL")
            print("Coluna 'longitude' adicionada com sucesso.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("Coluna 'longitude' já existe.")
            else:
                raise

        conn.commit()
        print("Alterações salvas no banco de dados.")

    except sqlite3.Error as e:
        print(f"Ocorreu um erro de banco de dados: {e}")
    
    finally:
        if conn:
            conn.close()
            print("Conexão com o banco de dados fechada.")

if __name__ == '__main__':
    update_schema()