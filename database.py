import psycopg2
from datetime import datetime, timedelta

# Substitua o texto abaixo pelo seu link do Supabase (mantenha as aspas)
URL_DO_BANCO = "postgresql://postgres:Q1hgclztp44@db.jqpamxfmtbuyjxybhwsf.supabase.co:5432/postgres"

def conectar():
    return psycopg2.connect(URL_DO_BANCO)

def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()
    
    # 1. Tabela de Usuários (Agora com e-mail)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')
    
    # 2. Configuração agora exige o crachá do usuário (usuario_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracao (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            horas_semanais INTEGER DEFAULT 20,
            streak INTEGER DEFAULT 0,
            pontos INTEGER DEFAULT 0,
            ultimo_acesso DATE,
            UNIQUE(usuario_id)
        )
    ''')
    
    # 3. Disciplinas também levam o crachá de quem cadastrou
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS disciplinas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            nome TEXT NOT NULL,
            dificuldade INTEGER NOT NULL,
            peso INTEGER NOT NULL
        )
    ''')
    
    # Tópicos e Cronograma (Eles já sabem de quem são porque estão ligados na Disciplina)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topicos (
            id SERIAL PRIMARY KEY,
            id_disciplina INTEGER REFERENCES disciplinas(id) ON DELETE CASCADE,
            nome TEXT NOT NULL,
            estudado BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cronograma (
            id SERIAL PRIMARY KEY,
            id_topico INTEGER REFERENCES topicos(id) ON DELETE CASCADE,
            tipo_atividade TEXT,
            data_agendada DATE,
            concluido BOOLEAN DEFAULT FALSE,
            acertos INTEGER DEFAULT 0,
            total_questoes INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

# --- NOVAS FUNÇÕES DA PORTARIA (LOGIN) ---
def cadastrar_usuario(username, email, senha):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO usuarios (username, email, senha) VALUES (%s, %s, %s) RETURNING id', (username, email, senha))
        novo_id = cursor.fetchone()[0]
        # Já cria o placar de pontos zerado para esse usuário novo
        cursor.execute('INSERT INTO configuracao (usuario_id, streak, pontos) VALUES (%s, 0, 0)', (novo_id,))
        conn.commit()
        return True, "Sucesso"
    except psycopg2.errors.UniqueViolation as e:
        conn.rollback()
        erro_msg = str(e)
        if "usuarios_email_key" in erro_msg:
            return False, "Este e-mail já está cadastrado."
        return False, "Este nome de usuário já existe."
    finally:
        conn.close()

def fazer_login(username, senha):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM usuarios WHERE username = %s AND senha = %s', (username, senha))
    resultado = cursor.fetchone()
    conn.close()
    if resultado:
        return resultado[0] # Retorna o ID (o crachá) do usuário
    return None

# --- FUNÇÃO ATUALIZADA (Agora recebe o crachá na hora de salvar) ---
def salvar_disciplina_completa(usuario_id, nome, dificuldade, peso, lista_topicos):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO disciplinas (usuario_id, nome, dificuldade, peso) VALUES (%s, %s, %s, %s) RETURNING id', 
                       (usuario_id, nome, dificuldade, peso))
        id_disciplina = cursor.fetchone()[0]
        
        prioridade = dificuldade * peso
        
        if prioridade >= 9:
            intervalo_dias = 2
        elif prioridade >= 4:
            intervalo_dias = 3
        else:
            intervalo_dias = 7
            
        hoje = datetime.now().date()
        
        for i, topico in enumerate(lista_topicos):
            topico_limpo = topico.strip()
            if topico_limpo:
                cursor.execute('INSERT INTO topicos (id_disciplina, nome) VALUES (%s, %s) RETURNING id', (id_disciplina, topico_limpo))
                id_topico = cursor.fetchone()[0]
                
                dias_para_frente = i * intervalo_dias
                data_estudo = hoje + timedelta(days=dias_para_frente)
                
                cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                               (id_topico, 'Estudo', data_estudo))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro: {e}")
        return False
    finally:
        conn.close()

criar_tabelas()