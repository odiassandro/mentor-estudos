import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import database
import random

def obter_estatisticas_usuario(usuario_id):
    import database
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    
    conn = database.conectar()
    cursor = conn.cursor()
    
    # 1. Busca os pontos (XP) que ficam na tabela configuracao
    cursor.execute('SELECT pontos FROM configuracao WHERE usuario_id = %s', (usuario_id,))
    res_conf = cursor.fetchone()
    pontos = res_conf[0] if res_conf and res_conf[0] else 0
    
    # 2. Busca o Streak na tabela usuarios
    cursor.execute('SELECT streak, ultima_atividade FROM usuarios WHERE id = %s', (usuario_id,))
    res_user = cursor.fetchone()
    
    streak = 0
    if res_user:
        streak = res_user[0] if res_user[0] else 0
        ultima_atividade = res_user[1]
        
        if hasattr(ultima_atividade, 'date'):
            ultima_atividade = ultima_atividade.date()
            
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        ontem = hoje - timedelta(days=1)
        
        # 3. O Teste de Realidade: Se não fez nada hoje e nem ontem, a fogueira apagou!
        if ultima_atividade and ultima_atividade != hoje and ultima_atividade != ontem:
            streak = 0
            # Já atualiza no banco de forma silenciosa para o número real
            cursor.execute('UPDATE usuarios SET streak = 0 WHERE id = %s', (usuario_id,))
            conn.commit()
            
    conn.close()
    return streak, pontos
        
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
    import database
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    conn = database.conectar()
    cursor = conn.cursor()
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()
    
    cursor.execute('SELECT id_topico FROM cronograma WHERE id = %s', (id_cronograma,))
    resultado = cursor.fetchone()
    if not resultado: 
        conn.close()
        return
    id_topico = resultado[0]
    
    cursor.execute('''
        UPDATE cronograma 
        SET concluido = TRUE, tipo_atividade = 'Estudo (Incompleto)', data_agendada = %s 
        WHERE id = %s
    ''', (hoje, id_cronograma))
    
    amanha = hoje + timedelta(days=1)
    cursor.execute('''
        INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada, concluido)
        VALUES (%s, 'Estudo ⏳', %s, FALSE)
    ''', (id_topico, amanha))
    
    cursor.execute('UPDATE configuracao SET pontos = pontos + 5 WHERE usuario_id = %s', (usuario_id,))
    conn.commit()
    conn.close()
    
    # 🔄 VOLTOU PRO MODO SEGURO: Recalcula de forma síncrona
    database.recalcular_cronograma_futuro(usuario_id)

def concluir_tarefa_e_gerar_revisoes(id_cronograma, tipo_atividade, id_topico_df, acertos, total, usuario_id, recalcular=True):
    import database
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
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
    
    proxima_ativ = None
    dias_add = 0
    
    if tipo_atividade in ['Estudo', 'Estudo ⏳']:
        cursor.execute('UPDATE topicos SET estudado = TRUE WHERE id = %s', (id_topico,))
        proxima_ativ = 'Revisão 1d'
        dias_add = 1
    elif tipo_atividade == 'Revisão 1d':
        proxima_ativ = 'Questões 3d'
        dias_add = 2  
    elif tipo_atividade == 'Questões 3d':
        proxima_ativ = 'Revisão 7d'
        dias_add = 4  
    elif tipo_atividade == 'Revisão 7d':
        proxima_ativ = 'Questões 30d'
        dias_add = 23 
    elif tipo_atividade == 'Questões 30d':
        proxima_ativ = None 
        dias_add = 0

    if total > 0:
        taxa = (acertos / total) * 100
        if taxa < 70:
            proxima_ativ = 'Revisão 1d'
            dias_add = 1

    if proxima_ativ:
        cursor.execute('DELETE FROM cronograma WHERE id_topico = %s AND tipo_atividade = %s AND concluido = FALSE', 
                       (id_topico, proxima_ativ))
        cursor.execute('INSERT INTO cronograma (id_topico, tipo_atividade, data_agendada) VALUES (%s, %s, %s)', 
                       (id_topico, proxima_ativ, hoje + timedelta(days=dias_add)))
            
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
    
    # 🔄 VOLTOU PRO MODO SEGURO: Bloqueia a tela até recalcular tudo!
    if recalcular:
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
        
    df['taxa_acertos'] = (df['total_acertos'] / df['total_feito']) * 100
    
    def classificar_desempenho(taxa):
        if taxa < 70: return "🔴 Ruim"
        elif taxa <= 85: return "🟡 Bom"
        else: return "🟢 Excelente"
            
    df['status'] = df['taxa_acertos'].apply(classificar_desempenho)
    df['taxa_acertos'] = df['taxa_acertos'].round(1).astype(str) + '%'
    return df.sort_values(by='taxa_acertos')
    
# 🔄 FUNÇÃO NOVA DO RELOGINHO DA AMPULHETA
def obter_ultima_atualizacao(usuario_id):
    import database
    from zoneinfo import ZoneInfo
    conn = database.conectar()
    cursor = conn.cursor()
    cursor.execute('SELECT ultima_atualizacao FROM configuracao WHERE usuario_id = %s', (usuario_id,))
    res = cursor.fetchone()
    conn.close()
    if res and res[0]:
        return res[0].astimezone(ZoneInfo('America/Bahia')).strftime('%H:%M:%S (%d/%m)')
    return "Aguardando atualização"

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
