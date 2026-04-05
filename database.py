import psycopg2
from datetime import datetime, timedelta
import streamlit as st

# Puxando a senha do cofre do Streamlit Cloud
URL_DO_BANCO = st.secrets["URL_DO_BANCO"]

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

def salvar_disciplina_completa(usuario_id, nome, dificuldade, peso, lista_topicos):
    conn = conectar()
    cursor = conn.cursor()
    try:
        # 1. Busca suas configurações
        cursor.execute('SELECT horas_semanais, dias_bloqueados FROM configuracao WHERE usuario_id = %s', (usuario_id,))
        config = cursor.fetchone()
        horas_semanais = config[0] if config else 24
        dias_bloqueados = [int(d) for d in config[1].split(',')] if config[1] else [2, 4]
        
        # 2. Calcula limite diário global
        dias_disponiveis_na_semana = 7 - len(dias_bloqueados)
        if dias_disponiveis_na_semana == 0: dias_disponiveis_na_semana = 1
        limite_horas_dia = horas_semanais / dias_disponiveis_na_semana

        # 3. Cadastra a disciplina
        cursor.execute('INSERT INTO disciplinas (usuario_id, nome, dificuldade, peso) VALUES (%s, %s, %s, %s) RETURNING id', 
                       (usuario_id, nome, dificuldade, peso))
        id_disciplina = cursor.fetchone()[0]
        
        hoje = datetime.now().date()
        data_atual = hoje
        
        for topico in lista_topicos:
            topico_limpo = topico.strip()
            if not topico_limpo: continue
            
            # --- O NOVO CÉREBRO DO ROBÔ ---
            dia_encontrado = False
            while not dia_encontrado:
                # Se for dia de plantão, já pula direto
                if data_atual.weekday() in dias_bloqueados:
                    data_atual += timedelta(days=1)
                    continue
                
                # Olha no calendário GLOBAL do usuário para ver quantas horas já estão ocupadas nesse dia
                cursor.execute('''
                    SELECT COUNT(*) FROM cronograma c
                    JOIN topicos t ON c.id_topico = t.id
                    JOIN disciplinas d ON t.id_disciplina = d.id
                    WHERE d.usuario_id = %s AND c.data_agendada = %s
                ''', (usuario_id, data_atual))
                
                qtd_tarefas_no_dia = cursor.fetchone()[0]
                horas_ja_ocupadas_no_dia = qtd_tarefas_no_dia * 1.5 # (Avaliando 1.5h por tópico)
                
                # Se ainda tiver espaço no dia, achou o dia certo! Se não, pula pro próximo.
                if (horas_ja_ocupadas_no_dia + 1.5) <= limite_horas_dia:
                    dia_encontrado = True
                else:
                    data_atual += timedelta(days=1)
            # ------------------------------

            # Insere no banco
            cursor.execute('INSERT INTO topicos (id_disciplina, nome) VALUES (%s, %s) RETURNING id', (id_disciplina, topico_limpo))
            id_topico = cursor.fetchone()[0]
            
            cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                           (id_topico, 'Estudo', data_atual))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao salvar: {e}")
        return False
    finally:
        conn.close()
        
criar_tabelas()
