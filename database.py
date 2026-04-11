import psycopg2
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
        cursor.execute('SELECT horas_semanais, dias_bloqueados FROM configuracao WHERE usuario_id = %s', (usuario_id,))
        config = cursor.fetchone()
        horas_semanais = config[0] if config else 24
        dias_bloqueados = [int(d) for d in config[1].split(',')] if config[1] else [2, 4]
        
        dias_disponiveis_na_semana = max(1, 7 - len(dias_bloqueados))
        limite_horas_dia = horas_semanais / dias_disponiveis_na_semana

        cursor.execute('INSERT INTO disciplinas (usuario_id, nome, dificuldade, peso) VALUES (%s, %s, %s, %s) RETURNING id', 
                       (usuario_id, nome, dificuldade, peso))
        id_disciplina = cursor.fetchone()[0]
        
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        data_atual = hoje
        
        for topico in lista_topicos:
            topico_limpo = topico.strip()
            if not topico_limpo: continue
            
            dia_encontrado = False
            while not dia_encontrado:
                if data_atual.weekday() in dias_bloqueados:
                    data_atual += timedelta(days=1)
                    continue
                
                # --- A INTELIGÊNCIA DA DÍVIDA COMEÇA AQUI ---
                if data_atual == hoje:
                    # Se estamos olhando pro "Hoje", soma TUDO que tá atrasado também!
                    filtro_sql = "c.data_agendada <= %s AND c.concluido = FALSE"
                else:
                    # Se for pro futuro, olha só o próprio dia
                    filtro_sql = "c.data_agendada = %s AND c.concluido = FALSE"
                    
                cursor.execute(f'''
                    SELECT COALESCE(SUM(
                        CASE 
                            WHEN c.tipo_atividade = 'Estudo' THEN 1.0
                            ELSE 0.5
                        END
                    ), 0) FROM cronograma c
                    JOIN topicos t ON c.id_topico = t.id
                    JOIN disciplinas d ON t.id_disciplina = d.id
                    WHERE d.usuario_id = %s AND {filtro_sql}
                ''', (usuario_id, data_atual))
                # --------------------------------------------
                
                horas_ocupadas = float(cursor.fetchone()[0])
                
                if (horas_ocupadas + 1.0) <= limite_horas_dia: 
                    dia_encontrado = True
                else:
                    data_atual += timedelta(days=1)

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


def recalcular_cronograma_futuro(usuario_id):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT horas_semanais, dias_bloqueados FROM configuracao WHERE usuario_id = %s', (usuario_id,))
        config = cursor.fetchone()
        horas_semanais = config[0] if config else 24
        dias_bloqueados = [int(d) for d in config[1].split(',')] if config[1] else []
        
        limite_horas_dia = horas_semanais / max(1, 7 - len(dias_bloqueados))
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        
        # A GRANDE MUDANÇA: Tiramos o ">= hoje". O robô cata TUDO que não foi concluído!
        cursor.execute('''
            SELECT c.id_topico, c.tipo_atividade 
            FROM cronograma c
            JOIN topicos t ON c.id_topico = t.id
            JOIN disciplinas d ON t.id_disciplina = d.id
            WHERE d.usuario_id = %s AND c.concluido = FALSE
            ORDER BY c.data_agendada, ROW_NUMBER() OVER(PARTITION BY d.id ORDER BY c.id), d.id
        ''', (usuario_id,))
        
        agendamentos_futuros = cursor.fetchall()
        
        if not agendamentos_futuros:
            return True
            
        # O aspirador apaga o passado, o presente e o futuro de tudo que tá pendente
        cursor.execute('''
            DELETE FROM cronograma c
            USING topicos t, disciplinas d
            WHERE c.id_topico = t.id AND t.id_disciplina = d.id
            AND d.usuario_id = %s AND c.concluido = FALSE
        ''', (usuario_id,))
        
        data_atual = hoje
        
        for agendamento in agendamentos_futuros:
            id_topico = agendamento[0]
            tipo_atividade = agendamento[1]
            tempo_desta_atividade = 1.0 if tipo_atividade == 'Estudo' else 0.5
            
            dia_encontrado = False
            
            while not dia_encontrado:
                if data_atual.weekday() in dias_bloqueados:
                    data_atual += timedelta(days=1)
                    continue
                
                # Como nós limpamos o passado, não tem mais dívida antiga.
                # O robô só soma as horas do dia atual que ele está tentando preencher.
                cursor.execute('''
                    SELECT COALESCE(SUM(
                        CASE 
                            WHEN c.tipo_atividade = 'Estudo' THEN 1.0
                            ELSE 0.5
                        END
                    ), 0) FROM cronograma c
                    JOIN topicos t ON c.id_topico = t.id
                    JOIN disciplinas d ON t.id_disciplina = d.id
                    WHERE d.usuario_id = %s AND c.data_agendada = %s AND c.concluido = FALSE
                ''', (usuario_id, data_atual))
                
                horas_ocupadas = float(cursor.fetchone()[0])
                
                if (horas_ocupadas + tempo_desta_atividade) <= limite_horas_dia: 
                    dia_encontrado = True
                else:
                    data_atual += timedelta(days=1)
                    
            cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                           (id_topico, tipo_atividade, data_atual))
                           
        conn.commit()
        return True
    except Exception as e:
        print(f"Erro ao recalcular: {e}")
        return False
    finally:
        conn.close()
        
def atualizar_streak_e_xp(usuario_id, xp_ganho=0):
    # Mantive o xp_ganho ali só pra não quebrar a função que você já colou no logica.py
    conn = conectar()
    cursor = conn.cursor()
    try:
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        ontem = hoje - timedelta(days=1)
        
        cursor.execute('SELECT streak, ultima_atividade FROM usuarios WHERE id = %s', (usuario_id,))
        resultado = cursor.fetchone()
        
        if resultado:
            streak_atual = resultado[0] if resultado[0] else 0
            ultima_atividade = resultado[1]
            
            if ultima_atividade == hoje:
                novo_streak = streak_atual
            elif ultima_atividade == ontem:
                novo_streak = streak_atual + 1
            else:
                novo_streak = 1
                
            # AGORA SIM! Atualizando SÓ O QUE EXISTE na tabela usuarios!
            cursor.execute('''
                UPDATE usuarios 
                SET streak = %s, ultima_atividade = %s 
                WHERE id = %s
            ''', (novo_streak, hoje, usuario_id))
            
            conn.commit()
    except Exception as e:
        print(f"Erro ao atualizar streak: {e}")
    finally:
        conn.close()
        
criar_tabelas()
