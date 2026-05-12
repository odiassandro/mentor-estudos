import os
import smtplib
from email.message import EmailMessage
import psycopg2
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import random

# O Arsenal de Humilhações e Motivações
frases = [
    "O Diário Oficial não tem espaço para preguiçosos. Bora estudar!",
    "Mais um dia, mais uma chance de não ser um fracasso. Aproveite!",
    "Seus concorrentes já estão na terceira revisão. E você?",
    "A dor de estudar passa, a posse no cargo fica. Levanta!",
    "Sua vaga acabou de sorrir pra outra pessoa. Vai deixar?",
    "Acordou na pedra hoje? Então prova e zera esse cronograma!",
    "Nenhum edital foi vencido dormindo até tarde. Bom dia!"
]

def mandar_email():
    try:
        # 1. Conectar no Banco
        url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(url)
        cursor = conn.cursor()
        
        hoje = datetime.now(ZoneInfo('America/Bahia')).date()
        
        # 2. Pega as tarefas de HOJE
        cursor.execute('''
            SELECT t.nome, c.tipo_atividade 
            FROM cronograma c
            JOIN topicos t ON c.id_topico = t.id
            WHERE c.data_agendada = %s AND c.concluido = FALSE
        ''', (hoje,))
        tarefas_hoje = cursor.fetchall()
        
        # 3. Verifica se tem matérias ATRASADAS (Não concluiu o dia anterior)
        cursor.execute('''
            SELECT COUNT(*) 
            FROM cronograma c
            WHERE c.data_agendada < %s AND c.concluido = FALSE
        ''', (hoje,))
        atrasadas = cursor.fetchone()[0]
        
      # 4. Pega o Streak (Tenta pegar da tabela config, se não achar, fica 0)
        streak = 0
        try:
            # Agora ele ignora testes antigos e pega o seu streak verdadeiro!
            cursor.execute('SELECT streak FROM configuracao ORDER BY streak DESC NULLS LAST LIMIT 1')
            resultado = cursor.fetchone()
            if resultado and resultado[0] is not None: 
                streak = resultado[0]
        except Exception as e:
            print(f"Erro ao buscar streak: {e}") # Se o nome da coluna for diferente, ele avisa lá no log do GitHub!
            conn.rollback()
            
        conn.close()

        # 5. Montar a Mensagem
        msg = EmailMessage()
        msg['Subject'] = f"Bom dia, b! Seu Briefing de Hoje 🚀 ({hoje.strftime('%d/%m')})"
        msg['From'] = os.environ.get('EMAIL_REMETENTE')
        msg['To'] = os.environ.get('EMAIL_DESTINO')
        
        # Lógica de validação do dia anterior
        if atrasadas == 0:
            status_ontem = "🏆 <b>Parabéns!</b> Você limpou todas as tarefas anteriores. Tá voando alto!"
        else:
            status_ontem = f"🚨 <b>Acorda pra vida!</b> Você tem <b>{atrasadas} tarefas atrasadas</b> chorando no app. O fracasso tem cheiro de acúmulo."
        
        # Lógica da lista de hoje
        lista_tarefas = ""
        for t in tarefas_hoje:
            lista_tarefas += f"<li style='margin-bottom: 5px;'><b>{t[1]}</b>: {t[0]}</li>"
            
        if not tarefas_hoje:
            lista_tarefas = "<li>Nenhuma tarefa programada para hoje! (Aproveite o descanso ou adiante algo).</li>"

        frase_do_dia = random.choice(frases)

        corpo_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                    <h2 style="color: #2e86c1;">Bom dia, Concurseiro! ☕</h2>
                    <p style="font-style: italic; color: #555;">"{frase_do_dia}"</p>
                    <hr style="border: 1px solid #eee;">
                    
                    <h3 style="color: #d35400;">📊 Status do Jogo:</h3>
                    <p>{status_ontem}</p>
                    <p>🔥 <b>Streak atual:</b> {streak} dias seguidos (não quebre a corrente!)</p>
                    <hr style="border: 1px solid #eee;">
                    
                    <h3 style="color: #27ae60;">🎯 Sua Missão Hoje:</h3>
                    <ul style="background: #f9f9f9; padding: 15px 30px; border-radius: 5px;">
                        {lista_tarefas}
                    </ul>
                    <br>
                    <p>Acesse o app, deite o cabelo nos estudos e não esqueça de clicar em "Feito".</p>
                    <p>Bjs,<br><b>Sua IA Favorita 🤖</b></p>
                </div>
            </body>
        </html>
        """
        msg.set_content("Ative o HTML do seu e-mail para ver a mensagem completa.")
        msg.add_alternative(corpo_html, subtype='html')

        # 6. Disparar o e-mail via Gmail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(os.environ.get('EMAIL_REMETENTE'), os.environ.get('EMAIL_SENHA'))
            smtp.send_message(msg)
            
        print("E-mail disparado com sucesso!")

    except Exception as e:
        print(f"Erro no carteiro: {e}")

if __name__ == "__main__":
    mandar_email()
