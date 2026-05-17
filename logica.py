import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import database
import random

def obter_estatisticas_usuario(usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    try:
        # Buscamos a data da última atividade também!
        cursor.execute('''
            SELECT u.streak, u.ultima_atividade, c.pontos 
            FROM usuarios u
            JOIN configuracao c ON u.id = c.usuario_id
            WHERE u.id = %s
        ''', (usuario_id,))
        
        resultado = cursor.fetchone()
        if resultado:
            streak_db = resultado[0] if resultado[0] else 0
            ultima_ativ = resultado[1]
            pontos = resultado[2] if resultado[2] else 0
            
            hoje = datetime.now(ZoneInfo('America/Bahia')).date()
            ontem = hoje - timedelta(days=1)
            
            # O cérebro do Streak: Se você estudou hoje ou ontem, mantém. Se não, ZERA!
            if ultima_ativ and ultima_ativ >= ontem:
                streak_real = streak_db
            else:
                streak_real = 0
                
            return streak_real, pontos
        return 0, 0
    except Exception as e:
        print(f"Erro ao obter estatísticas: {e}")
        return 0, 0
    finally:
        conn.close()
        
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
    try:
        # Pega a soma de TODOS os acertos e TODAS as questões que você já fez
        cursor.execute('''
            SELECT SUM(c.acertos), SUM(c.total_questoes)
            FROM cronograma c
            JOIN topicos t ON c.id_topico = t.id
            JOIN disciplinas d ON t.id_disciplina = d.id
            WHERE d.usuario_id = %s AND c.concluido = TRUE AND c.total_questoes > 0
        ''', (usuario_id,))
        
        resultado = cursor.fetchone()
        
        if resultado and resultado[1]: # Se existir total de questões > 0
            total_acertos = resultado[0]
            total_questoes = resultado[1]
            return round((total_acertos / total_questoes) * 100, 1)
        return 0.0
    except Exception as e:
        print(f"Erro ao calcular taxa: {e}")
        return 0.0
    finally:
        conn.close()

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
    try:
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        amanha = hoje + timedelta(days=1)
        
        cursor.execute('UPDATE cronograma SET concluido = TRUE, data_agendada = %s WHERE id = %s', (hoje, id_cronograma,))
        cursor.execute('SELECT id_topico FROM cronograma WHERE id = %s', (id_cronograma,))
        resultado = cursor.fetchone()
        
        if resultado:
            id_topico = resultado[0]
            # Coloca o tópico pra amanhã (ele vai entrar na fila do recalculo)
            cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                           (id_topico, 'Estudo', amanha))
            
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
            
        # O fogo da ofensiva continua aqui
        database.atualizar_streak_e_xp(usuario_id, 0)
            
        conn.commit()
    except Exception as e:
        print(f"Erro ao adiar tarefa: {e}")
    finally:
        conn.close()
        
    # --- A MÁGICA DA AUTOMAÇÃO AQUI! ---
    # Depois de fechar o banco, mandamos o robô arrumar a bagunça do futuro!
    database.recalcular_cronograma_futuro(usuario_id)


def concluir_tarefa_e_gerar_revisoes(id_cronograma, tipo_atividade, id_topico_df, acertos, total, usuario_id):
    conn = database.conectar()
    cursor = conn.cursor()
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()
    
    if acertos > total:
        acertos = total
        
    cursor.execute('UPDATE cronograma SET concluido = TRUE, acertos = %s, total_questoes = %s, data_agendada = %s WHERE id = %s', 
                   (acertos, total, hoje, id_cronograma))
    
    cursor.execute('SELECT id_topico FROM cronograma WHERE id = %s', (id_cronograma,))
    resultado = cursor.fetchone()
    if not resultado: return
    id_topico = resultado[0]
    
    # === A MÁGICA DO EFEITO DOMINÓ ===
    proxima_ativ = None
    dias_add = 0
    
    if tipo_atividade == 'Estudo':
        cursor.execute('UPDATE topicos SET estudado = TRUE WHERE id = %s', (id_topico,))
        proxima_ativ = 'Revisão 1d'
        dias_add = 1
    elif tipo_atividade == 'Revisão 1d':
        proxima_ativ = 'Questões 3d'
        dias_add = 2  # 1 dia + 2 dias = fecha os 3 dias certinho
    elif tipo_atividade == 'Questões 3d':
        proxima_ativ = 'Revisão 7d'
        dias_add = 4
    elif tipo_atividade == 'Revisão 7d':
        proxima_ativ = 'Questões 11d'
        dias_add = 4
    elif tipo_atividade == 'Questões 11d':
        proxima_ativ = 'Questões 28d'
        dias_add = 17
    elif tipo_atividade == 'Questões 28d':
        proxima_ativ = 'Revisão 30d'
        dias_add = 2

    # Se a tarefa gerar uma continuação, ele cria a próxima peça do dominó!
    if proxima_ativ:
        # Escudo: Apaga qualquer sujeira antiga dessa mesma etapa
        cursor.execute('DELETE FROM cronograma WHERE id_topico = %s AND tipo_atividade = %s AND concluido = FALSE', 
                       (id_topico, proxima_ativ))
        # Agenda o próximo passo perfeitamente espaçado
        cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                       (id_topico, proxima_ativ, hoje + timedelta(days=dias_add)))
    # ==================================
            
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
        
    database.atualizar_streak_e_xp(usuario_id, 10)
        
    conn.commit()
    conn.close()
    
    database.recalcular_cronograma_futuro(usuario_id)

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

def calcular_acertos_por_topico(usuario_id):
    import pandas as pd
    import database
    conn = database.conectar()
    
    # Busca a soma de acertos e o total de questões para cada tópico
    query = '''
        SELECT d.nome as disciplina, t.nome as topico, 
               SUM(c.acertos) as total_acertos, 
               SUM(c.total_questoes) as total_feito
        FROM cronograma c
        JOIN topicos t ON c.id_topico = t.id
        JOIN disciplinas d ON t.id_disciplina = d.id
        WHERE d.usuario_id = %s 
          AND c.acertos IS NOT NULL 
          AND c.total_questoes > 0
        GROUP BY d.nome, t.nome
    '''
    df = pd.read_sql(query, conn, params=(usuario_id,))
    conn.close()
    
    if df.empty:
        return df
        
    # Calcula a porcentagem
    df['taxa_acertos'] = (df['total_acertos'] / df['total_feito']) * 100
    
    # Aplica a classificação
    def classificar_desempenho(taxa):
        if taxa < 70:
            return "🔴 Ruim"
        elif taxa <= 85:
            return "🟡 Bom"
        else:
            return "🟢 Excelente"
            
    df['status'] = df['taxa_acertos'].apply(classificar_desempenho)
    
    # Arredonda a taxa para ficar bonito na tela
    df['taxa_acertos'] = df['taxa_acertos'].round(1).astype(str) + '%'
    
    # Ordena para os piores (os que precisam de atenção) aparecerem primeiro
    return df.sort_values(by='taxa_acertos')
    
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
