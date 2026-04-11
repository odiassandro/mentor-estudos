import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logica
import database

st.set_page_config(page_title="Mentor de Estudos", layout="wide")

# ==========================================
# SISTEMA DE LOGIN (A CATRACA DA PLATAFORMA)
# ==========================================
if 'usuario_id' not in st.session_state:
    st.session_state['usuario_id'] = None

if st.session_state['usuario_id'] is None:
    st.title("🔒 Acesso Restrito - Mentor de Estudos")
    st.write("Faça login ou crie sua conta para acessar seu planejamento.")
    
    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar Conta"])
    
    with aba_login:
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")
            if submit:
                id_logado = database.fazer_login(usuario, senha)
                if id_logado:
                    st.session_state['usuario_id'] = id_logado
                    st.rerun() 
                else:
                    st.error("Usuário ou senha incorretos.")
                    
    with aba_cadastro:
        with st.form("form_cadastro"):
            novo_usuario = st.text_input("Novo Usuário")
            novo_email = st.text_input("E-mail")
            nova_senha = st.text_input("Crie uma Senha", type="password")
            submit_cad = st.form_submit_button("Cadastrar")
            if submit_cad:
                if novo_usuario and novo_email and nova_senha:
                    sucesso, msg = database.cadastrar_usuario(novo_usuario, novo_email, nova_senha)
                    if sucesso:
                        st.success("Conta criada com sucesso! Volte na aba 'Entrar' para acessar.")
                    else:
                        st.error(msg)
                else:
                    st.warning("Preencha todos os campos.")
    
    st.stop() # Para o código aqui se a pessoa não estiver logada!

# ==========================================
# APLICATIVO PRINCIPAL (O USUÁRIO ESTÁ LOGADO)
# ==========================================
usuario_id = st.session_state['usuario_id']

col_titulo, col_sair = st.columns([8, 1])
col_titulo.title("☠️ Mentor de Estudos - Modo Hard - TESTE")
if col_sair.button("🚪 Sair", use_container_width=True):
    st.session_state['usuario_id'] = None
    st.rerun()

aba_dashboard, aba_calendario, aba_edital, aba_config = st.tabs(["📊 Dashboard", "📅 Cronograma", "📑 Edital", "⚙️ Configuração"])

with aba_dashboard:
    st.header("Seu Centro de Comando")
    streak, pontos = logica.obter_estatisticas_usuario(usuario_id)
    taxa_acertos = logica.calcular_taxa_acertos(usuario_id)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Sequência (Streak)", f"{streak} dias", "Mantenha o ritmo!")
    col2.metric("🎯 Taxa de Acertos Global", f"{taxa_acertos}%", "Precisão")
    col3.metric("🏆 Pontuação XP", f"{pontos} pts", "Continue avançando")
    st.divider()
    col_tabela, col_grafico = st.columns([1, 1])
    with col_tabela:
        st.subheader("📖 Progresso do Edital")
        df_progresso = logica.calcular_progresso_edital(usuario_id)
        if not df_progresso.empty:
            st.dataframe(
                df_progresso,
                column_config={
                    "nome": "Disciplina",
                    "total": "Tópicos",
                    "concluidos": "Estudados",
                    "progresso_%": st.column_config.ProgressColumn("Progresso", format="%f%%", min_value=0, max_value=100),
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.info("Cadastre disciplinas para ver seu progresso.")
    with col_grafico:
        st.subheader("🎯 Acertos por Matéria")
        df_acertos = logica.calcular_acertos_por_materia(usuario_id)
        if not df_acertos.empty:
            st.bar_chart(data=df_acertos.set_index('Disciplina')['Taxa'], color='#8338ec')
        else:
            st.info("Resolva sua primeira bateria de questões para gerar o gráfico!")

with aba_calendario:
    st.header("Cronograma da Semana")
    df_agenda = logica.obter_agenda_pendente(usuario_id)
    hoje = datetime.now(ZoneInfo('America/Bahia')).date()

    # 1. Primeiro a gente verifica se tem matéria atrasada ou pendente hoje
    if not df_agenda.empty:
        df_pendente_hoje = df_agenda[pd.to_datetime(df_agenda['data_agendada']).dt.date <= hoje]
    else:
        df_pendente_hoje = pd.DataFrame() 

    # 2. AS FRASES DE HUMILHAÇÃO (OU GLÓRIA) ENTRAM AQUI NO TOPO!
    if df_pendente_hoje.empty:
        st.success("Sua missão de HOJE está cumprida! Descanse agora guerreiro.")
        st.markdown(f"<div style='font-size: 20px; font-weight: bold; color: #2ca02c;'>{logica.frase_motivacional(sucesso=True)}</div>", unsafe_allow_html=True)
    else:
        st.error(f"Pendente HOJE: {logica.frase_motivacional(sucesso=False)}")

    st.divider()

    # 3. Daqui pra baixo continua a montagem normal da semana...
 
    datas_semana = [hoje + timedelta(days=i) for i in range(7)]
    dias_semana_nomes = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    cols = st.columns(7)
    for i, col in enumerate(cols):
        dia_data = datas_semana[i]
        nome_dia = dias_semana_nomes[dia_data.weekday()]
        if i == 0:
            col.markdown(f"<div style='text-align: center; background-color: #333; color: white; padding: 5px; border-radius: 5px;'><b>Hoje</b><br><small>{dia_data.strftime('%d/%m')}</small></div>", unsafe_allow_html=True)
        else:
            col.markdown(f"<div style='text-align: center;'><b>{nome_dia}</b><br><small>{dia_data.strftime('%d/%m')}</small></div>", unsafe_allow_html=True)
            
    st.markdown("<br>", unsafe_allow_html=True)

    if not df_agenda.empty:
        df_pendente_hoje = df_agenda[pd.to_datetime(df_agenda['data_agendada']).dt.date <= hoje]
    else:
        df_pendente_hoje = pd.DataFrame() 

    if not df_agenda.empty:
        df_agenda['data_agendada'] = pd.to_datetime(df_agenda['data_agendada']).dt.date
        
        def concluir_tarefa(id_tarefa, tipo_ativ, topico_nome, acertos, total, u_id):
            logica.concluir_tarefa_e_gerar_revisoes(id_tarefa, tipo_ativ, topico_nome, acertos, total, u_id)

        cores = {
            'Estudo': '#00b4d8',           
            'Revisão 1d': '#ff006e',       
            'Revisão 7d': '#ff006e',
            'Revisão 30d': '#ff006e',
            'Questões 3d': '#8338ec',
            'Questões 11d': '#8338ec',
            'Questões 28d': '#8338ec'
        }

        for index, row in df_agenda.iterrows():
            data_tarefa = row['data_agendada']
            if data_tarefa <= hoje:
                idx_coluna = 0
                atrasada = (data_tarefa < hoje)
            elif data_tarefa in datas_semana:
                idx_coluna = datas_semana.index(data_tarefa)
                atrasada = False
            else:
                continue 
            
            with cols[idx_coluna]:
                cor_fundo = cores.get(row['tipo_atividade'], '#333333')
                alerta_atraso = "<div style='color: #ffcc00; font-size: 10px; font-weight: bold; margin-bottom: 3px;'>⚠️ ATRASADA</div>" if atrasada else ""
                duracao_tag = "⏱️ 60 min" if row['tipo_atividade'] == 'Estudo' else "⏱️ 30 min"
                
                card_html = f"""<div style="background-color: {cor_fundo}; padding: 10px; border-radius: 8px; color: white; margin-bottom: 5px; min-height: 110px; box-shadow: 2px 2px 5px rgba(0,0,0,0.2);">
{alerta_atraso}
<div style="display: flex; justify-content: space-between;">
    <strong style="font-size: 13px;">{row['disciplina']}</strong>
    <span style="font-size: 10px; opacity: 0.8;">{duracao_tag}</span>
</div>
<span style="font-size: 12px; line-height: 1.2;">{row['topico']}</span><br>
<div style="margin-top: 5px;">
<span style="font-size: 10px; font-weight: bold; background: rgba(0,0,0,0.2); padding: 3px 6px; border-radius: 4px;">
{row['tipo_atividade']}
</span>
</div>
</div>"""
                st.markdown(card_html, unsafe_allow_html=True)
                
                if 'Questões' in row['tipo_atividade']:
                    with st.popover("✅ Lançar Acertos", use_container_width=True):
                        st.write("Métricas da Bateria:")
                        qtd_acertos = st.number_input("Acertos", min_value=0, step=1, key=f"ac_{row['id']}")
                        qtd_total = st.number_input("Total Feito", min_value=1, step=1, key=f"tot_{row['id']}")
                        st.button("Salvar e Concluir", key=f"btn_save_{row['id']}", 
                                  on_click=concluir_tarefa, 
                                  args=(row['id'], row['tipo_atividade'], row['topico'], qtd_acertos, qtd_total, usuario_id), 
                                  use_container_width=True, type="primary")
                
                elif row['tipo_atividade'] == 'Estudo':
                    with st.popover("🎯 Ação da Meta", use_container_width=True):
                        st.write("Status do Assunto:")
                        st.button("✅ Dominei (Gerar Revisões)", key=f"btn_feito_{row['id']}", 
                                  on_click=concluir_tarefa, 
                                  args=(row['id'], row['tipo_atividade'], row['topico'], 0, 0, usuario_id), 
                                  use_container_width=True, type="primary")
                        st.button("⏳ Estudei, mas não acabei", key=f"btn_falta_{row['id']}", 
                                  on_click=logica.estudei_mas_nao_terminei, 
                                  args=(row['id'], usuario_id), 
                                  use_container_width=True)
                else:
                    st.button(f"✅ Feito", key=f"btn_{row['id']}", 
                              on_click=concluir_tarefa, 
                              args=(row['id'], row['tipo_atividade'], row['topico'], 0, 0, usuario_id), 
                              use_container_width=True)
                
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

with aba_edital:
    st.header("Seu Edital Verticalizado")
    st.write("Acompanhe o que já foi dominado e o que ainda falta desbravar.")
    df_edital = logica.obter_edital_verticalizado(usuario_id)
    if not df_edital.empty:
        disciplinas = df_edital['disciplina'].unique()
        for disc in disciplinas:
            with st.expander(f"📚 {disc}", expanded=True):
                topicos_disc = df_edital[df_edital['disciplina'] == disc]
                for _, row in topicos_disc.iterrows():
                    if row['estudado']:
                        st.markdown(f"✅ <span style='text-decoration: line-through; color: #888888;'>{row['topico']}</span>", unsafe_allow_html=True)
                    else:
                        # Removi o "color: #ffffff;" para a mágica acontecer!
                        st.markdown(f"⏳ <span>{row['topico']}</span>", unsafe_allow_html=True)
    else:
        st.info("Nenhuma disciplina cadastrada ainda. Vá na aba de Configuração Inicial!")
        
with aba_config:
    # 1. PARTE NOVA: ROTINA E PLANTÕES
    st.header("Sua Rotina e Limites")
    
    col_h, col_d = st.columns(2)
    with col_h:
        horas_semanais = st.number_input("Horas de estudo por semana:", min_value=1, value=24)
    
    with col_d:
        st.write("Dias de Plantão/Descanso (Bloqueados):")
        dias_nomes = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        selecionados = []
        col_dias = st.columns(7)
        for i, nome in enumerate(dias_nomes):
            # Deixa Terça (1) e Quinta (3) marcados por padrão pra você
            padrao = True if i in [1, 3] else False
            if col_dias[i].checkbox(nome, value=padrao, key=f"dia_{i}"):
                selecionados.append(str(i))
        
        dias_bloqueados_str = ",".join(selecionados)

    if st.button("Atualizar Minha Rotina"):
        conn = database.conectar()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE configuracao SET horas_semanais = %s, dias_bloqueados = %s 
            WHERE usuario_id = %s
        ''', (horas_semanais, dias_bloqueados_str, usuario_id))
        conn.commit()
        conn.close()
        
        # Agora o robô reorganiza o futuro automaticamente!
        st.info("Reorganizando o seu cronograma... Aguarde.")
        sucesso = database.recalcular_cronograma_futuro(usuario_id)
        
        if sucesso:
            st.success("Rotina atualizada e calendário recalculado! Suas férias estão a salvo.")
            st.rerun()
        else:
            st.error("Ops, deu um erro ao recalcular.")

    st.divider()
    
    # 2. PARTE ANTIGA: CADASTRAR MATÉRIAS
    st.header("Cadastrar Novo Edital")
    with st.form("form_disciplina", clear_on_submit=True):
        nome_disc = st.text_input("Nome da Disciplina")
        col1, col2 = st.columns(2)
        with col1:
            dificuldade = st.slider("Nível de Dificuldade", 1, 3, 2, help="1-Fácil, 2-Médio, 3-Difícil")
        with col2:
            peso = st.slider("Peso da Matéria na Prova", 1, 5, 1, help="De 1 a 5")
        topicos_texto = st.text_area("Tópicos do Edital (Digite UM tópico por linha e dê Enter)")
        
        if st.form_submit_button("Salvar Disciplina"):
            if nome_disc and topicos_texto:
                lista_de_topicos = topicos_texto.split('\n')
                sucesso = database.salvar_disciplina_completa(usuario_id, nome_disc, dificuldade, peso, lista_de_topicos)
                if sucesso:
                    st.success(f"Disciplina '{nome_disc}' salva! Vá para o Calendário.")
                else:
                    st.error("Erro ao salvar.")
            else:
                st.warning("Preencha o nome da disciplina e pelo menos um tópico.")
                
    st.divider()
     
    # --- NOVA SESSÃO DE GERENCIAMENTO (A LIXEIRA) ---
    st.header("🗑️ Gerenciar Edital")
    st.write("Cansou de um concurso? Apague a disciplina inteira aqui (Isso apagará todo o histórico e revisões dela).")
    
    df_disciplinas = logica.obter_disciplinas_do_usuario(usuario_id)
    
    if not df_disciplinas.empty:
        for index, row in df_disciplinas.iterrows():
            col_nome, col_btn = st.columns([4, 1])
            col_nome.markdown(f"**📚 {row['nome']}**")
            
            # Botão de excluir para cada matéria
            if col_btn.button("❌ Excluir", key=f"del_{row['id']}", use_container_width=True):
                logica.deletar_disciplina(row['id'], usuario_id)
                st.rerun() # Recarrega a página na hora para a matéria sumir
    else:
        st.info("Nenhuma disciplina cadastrada para excluir.")
