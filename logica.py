import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import database
import random

def obter_estatisticas_usuario(usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    cursor.execute('SELECT streak, pontos FROM configuracao WHERE usuario_id = %s', (usuario_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0], resultado[1] if resultado else (0, 0)

def calcular_progresso_edital(usuario_id):
    conn = database.conectar()
    query = f'''
        SELECT d.nome, COUNT(t.id) as total, SUM(t.estudado::int) as concluidos 
        FROM disciplinas d 
        LEFT JOIN topicos t ON d.id = t.id_disciplina 
        WHERE d.usuario_id = {usuario_id}
        GROUP BY d.nome
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty: return pd.DataFrame()
    df['progresso_%'] = (df['concluidos'] / df['total'] * 100).fillna(0).round(1)
    return df

def calcular_taxa_acertos(usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(c.acertos), SUM(c.total_questoes) 
        FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE c.concluido = TRUE AND c.total_questoes > 0 AND d.usuario_id = %s
    ''', (usuario_id,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado[0] and resultado[1] and resultado[1] > 0:
        return round((resultado[0] / resultado[1]) * 100, 1)
    return 0.0

def calcular_acertos_por_materia(usuario_id):
    conn = database.conectar()
    query = f'''
        SELECT d.nome, SUM(c.acertos), SUM(c.total_questoes)
        FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE c.concluido = TRUE AND c.total_questoes > 0 AND d.usuario_id = {usuario_id}
        GROUP BY d.nome
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if not df.empty:
        df.columns = ['Disciplina', 'Acertos', 'Total']
        df['Taxa'] = (df['Acertos'] / df['Total'] * 100).round(1)
    return df

def obter_agenda_pendente(usuario_id):
    conn = database.conectar()
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()
    daqui_7_dias = hoje + timedelta(days=6)
    
    query = f'''
        SELECT c.id, d.nome as disciplina, t.nome as topico, c.tipo_atividade, c.data_agendada, c.concluido
        FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE c.data_agendada <= '{daqui_7_dias}' AND c.concluido = FALSE AND d.usuario_id = {usuario_id}
        ORDER BY c.data_agendada, d.peso DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def obter_edital_verticalizado(usuario_id):
    conn = database.conectar()
    query = f'''
        SELECT d.nome as disciplina, t.nome as topico, t.estudado
        FROM disciplinas d
        JOIN topicos t ON d.id = t.id_disciplina
        WHERE d.usuario_id = {usuario_id}
        ORDER BY d.nome, t.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def estudei_mas_nao_terminei(id_cronograma, usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()
    amanha = hoje + timedelta(days=1)
    
    cursor.execute('UPDATE cronograma SET concluido = TRUE WHERE id = %s', (id_cronograma,))
    cursor.execute('SELECT id_topico FROM cronograma WHERE id = %s', (id_cronograma,))
    resultado = cursor.fetchone()
    
    if resultado:
        id_topico = resultado[0]
        cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                       (id_topico, 'Estudo', amanha))
        
    cursor.execute('UPDATE configuracao SET pontos = pontos + 10 WHERE usuario_id = %s', (usuario_id,))
    
    # Checa o bônus de zerar o dia para esse usuário específico
    cursor.execute('''
        SELECT COUNT(*) FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE c.data_agendada <= %s AND c.concluido = FALSE AND d.usuario_id = %s
    ''', (hoje, usuario_id))
    pendentes = cursor.fetchone()[0]
    
    if pendentes == 0:
        cursor.execute('UPDATE configuracao SET pontos = pontos + 10 WHERE usuario_id = %s', (usuario_id,))
        
    conn.commit()
    conn.close()

def concluir_tarefa_e_gerar_revisoes(id_cronograma, tipo_atividade, id_topico_df, acertos, total, usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()
    
    if acertos > total:
        acertos = total
        
    cursor.execute('UPDATE cronograma SET concluido = TRUE, acertos = %s, total_questoes = %s WHERE id = %s', 
                   (acertos, total, id_cronograma))
    
    cursor.execute('SELECT id_topico FROM cronograma WHERE id = %s', (id_cronograma,))
    resultado = cursor.fetchone()
    if not resultado: return
    id_topico = resultado[0]
    
    if tipo_atividade == 'Estudo':
        cursor.execute('UPDATE topicos SET estudado = TRUE WHERE id = %s', (id_topico,))
        
        atividades_futuras = [
            ('Revisão 1d', hoje + timedelta(days=1)),
            ('Questões 3d', hoje + timedelta(days=3)),
            ('Revisão 7d', hoje + timedelta(days=7)),
            ('Questões 11d', hoje + timedelta(days=11)),
            ('Questões 28d', hoje + timedelta(days=28)),
            ('Revisão 30d', hoje + timedelta(days=30))
        ]
        
        for ativ, data in atividades_futuras:
            cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                           (id_topico, ativ, data))
            
    cursor.execute('UPDATE configuracao SET pontos = pontos + 10 WHERE usuario_id = %s', (usuario_id,))
    
    cursor.execute('''
        SELECT COUNT(*) FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE c.data_agendada <= %s AND c.concluido = FALSE AND d.usuario_id = %s
    ''', (hoje, usuario_id))
    pendentes = cursor.fetchone()[0]
    
    if pendentes == 0:
        cursor.execute('UPDATE configuracao SET pontos = pontos + 10 WHERE usuario_id = %s', (usuario_id,))
        
    # --- AQUI ESTÁ O PULO DO GATO (O STREAK) ---
    # Chamamos a função do database para carimbar a ofensiva e dar os pontos no perfil
    database.atualizar_streak_e_xp(usuario_id, 10)
    # -------------------------------------------
        
    conn.commit()
    conn.close()

def obter_disciplinas_do_usuario(usuario_id):
    conn = database.conectar()
    query = f"SELECT id, nome FROM disciplinas WHERE usuario_id = {usuario_id} ORDER BY nome"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def deletar_disciplina(id_disciplina, usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    # A segurança primeiro: Só deleta se a disciplina pertencer ao usuário logado!
    cursor.execute("DELETE FROM disciplinas WHERE id = %s AND usuario_id = %s", (id_disciplina, usuario_id))
    conn.commit()
    conn.close()

def frase_motivacional(sucesso=True):
    humilhacoes = [
        "Sua vaga acabou de sorrir pra outra pessoa. Vai deixar acumular?",
        "Descansa guerreiro(a), a fila de desempregados precisa de você.",
        "Enquanto você enrola, seu concorrente já decorou a Constituição inteira.",
        "A dor da reprovação dói mais que a dor de sentar e estudar. Bora!",
        "Pode fechar o app. Com essa dedicação de centavos, o Diário Oficial nunca vai ver o seu nome."
    ]
    glorias = [
        "Você é uma máquina! O primeiro lugar já é seu.",
        "Selo de aprovação garantido! Meta batida com sucesso!",
        "O edital tremeu de medo de você hoje. Parabéns!",
        "O Diário Oficial já está sentindo o cheiro da sua nomeação. Tudo!",
        "Missão dada é missão cumprida! Hoje você dorme um passo mais perto da posse.",
        "Ai que delícian! Desse jeito, a aprovação é certa."
    ]
    return random.choice(glorias) if sucesso else random.choice(humilhacoes)
