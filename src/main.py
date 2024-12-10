import os
import re
import logging
import sqlite3
from enum import Enum
from dotenv import load_dotenv
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from datetime import datetime, timedelta
import calendar

### VARIÁVEIS DE AMBIENTE ###
load_dotenv()
TOKEN = os.getenv('TOKEN_TELEGRAM_BOT')

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Novo enum para qualidade do sono
class SleepQuality(Enum):
    VERY_BAD = "Muito Ruim"
    BAD = "Ruim"
    NORMAL = "Normal"
    GOOD = "Bom"
    VERY_GOOD = "Muito Bom"

# Definindo estados para a conversa
DISCIPLINE, START_TIME, END_TIME, SELECT_DATE, CONFIRM_DATE, STUDY_PERFORMANCE = range(6)

# Configuração do banco de dados SQLite
def init_database():
    """Inicializa o banco de dados SQLite e cria a tabela de horários."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_hours INTEGER,
            duration_minutes INTEGER,
            discipline TEXT,
            performance INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sleep_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_hours INTEGER,
            duration_minutes INTEGER,
            quality TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_study_schedule(user_id, user_name, date, start_time, end_time, hours, minutes, discipline, performance):
    """Salva o horário no banco de dados SQLite."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO study_periods 
        (user_id, user_name, date, start_time, end_time, duration_hours, duration_minutes, discipline, performance) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, date, start_time, end_time, hours, minutes, discipline, performance))
    conn.commit()
    conn.close()
    
def save_sleep_schedule(user_id, user_name, date, start_time, end_time, hours, minutes, quality):
    """Salva o horário de sono no banco de dados SQLite."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sleep_periods 
        (user_id, user_name, date, start_time, end_time, duration_hours, duration_minutes, quality) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, date, start_time, end_time, hours, minutes, quality))
    conn.commit()
    conn.close()
    
async def listar_horas_sono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os horários de sono registrados para o usuário atual."""
    user = update.effective_user
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT date, start_time, end_time, duration_hours, duration_minutes, quality 
        FROM sleep_periods 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (user.id,))
    
    schedules = cursor.fetchall()
    conn.close()
    
    if not schedules:
        await update.message.reply_text("Você ainda não possui horários de sono registrados.")
        return
    
    response = "Seus horários de sono registrados:\n\n"
    for schedule in schedules:
        response += (
            f"Data: {schedule[0]}\n"
            f"Início: {schedule[1]}\n"
            f"Término: {schedule[2]}\n"
            f"Duração: {schedule[3]} horas e {schedule[4]} minutos\n"
            f"Qualidade: {schedule[5]}\n\n"
        )
    
    await update.message.reply_text(response)

def generate_performance_keyboard():
    """Gera um teclado inline com porcentagens de performance."""
    performance_percentages = [
        0, 10, 20, 25, 30, 40, 45, 50, 60, 65, 70, 80, 90, 100
    ]
    
    keyboard = []
    row = []
    for perc in performance_percentages:
        button = InlineKeyboardButton(
            f"{perc}%",
            callback_data=f"performance_{perc}"
        )
        row.append(button)
        
        # Criar nova linha a cada 3 botões
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    # Adicionar última linha se incompleta
    if row:
        keyboard.append(row)
    
    # Botão para cancelar
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
    
    return keyboard
    
async def start_sleep_tracking(update: Update, context):
    user = update.effective_user
    context.user_data['user_id'] = user.id
    context.user_data['user_name'] = user.first_name

    await update.message.reply_text(
        "Vamos registrar suas horas de sono. "
        "Por favor, digite o horário de início do sono (no formato HH:MM):"
    )
    return 'SLEEP_START_TIME'

async def get_sleep_start_time(update: Update, context):
    start_time = update.message.text
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', start_time):
        await update.message.reply_text(
            "Formato de horário inválido. Por favor, use o formato HH:MM:"
        )
        return 'SLEEP_START_TIME'
    
    context.user_data['sleep_start_time'] = start_time
    
    await update.message.reply_text(
        f"Horário de início do sono: {start_time}\n"
        "Agora, digite o horário de término do sono (no formato HH:MM):"
    )
    return 'SLEEP_END_TIME'

async def get_sleep_end_time(update: Update, context):
    end_time = update.message.text
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', end_time):
        await update.message.reply_text(
            "Formato de horário inválido. Por favor, use o formato HH:MM:"
        )
        return 'SLEEP_END_TIME'
    
    context.user_data['sleep_end_time'] = end_time
    
    keyboard = generate_date_keyboard()
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Selecione a data para este período de sono:",
        reply_markup=reply_markup
    )
    
    return 'SLEEP_SELECT_DATE'

async def select_sleep_date(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operação cancelada.")
        return ConversationHandler.END
    
    selected_date = query.data.split('_')[1]
    context.user_data['selected_date'] = selected_date
    
    start_time = context.user_data.get('sleep_start_time')
    end_time = context.user_data.get('sleep_end_time')
    
    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%Y-%m-%d %H:%M')
    end_datetime = datetime.strptime(f"{selected_date} {end_time}", '%Y-%m-%d %H:%M')
    
    time_difference = end_datetime - start_datetime
    
    hours, remainder = divmod(time_difference.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    # Adicionar teclado inline para qualidade do sono
    keyboard = [
        [
            InlineKeyboardButton("Muito Ruim", callback_data="quality_VERY_BAD"),
            InlineKeyboardButton("Ruim", callback_data="quality_BAD")
        ],
        [
            InlineKeyboardButton("Normal", callback_data="quality_NORMAL"),
            InlineKeyboardButton("Bom", callback_data="quality_GOOD")
        ],
        [
            InlineKeyboardButton("Muito Bom", callback_data="quality_VERY_GOOD")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Período de sono:\n"
        f"Data: {selected_date}\n"
        f"Início: {start_time}\n"
        f"Término: {end_time}\n"
        f"Duração: {hours} horas e {minutes} minutos\n\n"
        "Como foi a qualidade do seu sono?",
        reply_markup=reply_markup
    )
    
    return 'SLEEP_QUALITY'

async def set_commands(application: Application):
    """Configura os comandos do bot no menu."""
    commands = [
        BotCommand("start", "Início do bot"),
        BotCommand("help", "Mostra ajuda"),
        BotCommand("adicionar_estudo", "Registra horário de estudo"),
        BotCommand("cancelar", "Cancela a operação atual"),
        BotCommand("listar_horas_estudo", "Lista horários de estudo registrados"),
        BotCommand("adicionar_sono", "Registra horário de sono"),
        BotCommand("listar_horas_sono", "Lista horários de sono registrados")
    ]
    
    # Define os comandos para todos os chats
    await application.bot.set_my_commands(commands)
    
async def select_sleep_quality(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    quality_data = query.data.lstrip("quality_")
    quality = SleepQuality[quality_data].value
    
    user_id = context.user_data.get('user_id')
    user_name = context.user_data.get('user_name')
    selected_date = context.user_data.get('selected_date')
    start_time = context.user_data.get('sleep_start_time')
    end_time = context.user_data.get('sleep_end_time')
    
    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%Y-%m-%d %H:%M')
    end_datetime = datetime.strptime(f"{selected_date} {end_time}", '%Y-%m-%d %H:%M')
    
    time_difference = end_datetime - start_datetime
    
    hours, remainder = divmod(time_difference.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    save_sleep_schedule(user_id, user_name, selected_date, start_time, end_time, hours, minutes, quality)
    
    await query.edit_message_text(
        f"Sono registrado:\n"
        f"Usuário: {user_name}\n"
        f"Data: {selected_date}\n"
        f"Início: {start_time}\n"
        f"Término: {end_time}\n"
        f"Duração: {hours} horas e {minutes} minutos\n"
        f"Qualidade: {quality}"
    )
    
    # Limpar dados do contexto
    del context.user_data['sleep_start_time']
    del context.user_data['sleep_end_time']
    del context.user_data['selected_date']
    del context.user_data['user_id']
    del context.user_data['user_name']
    
    return ConversationHandler.END

async def bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Bem-vindo, {user.first_name}! Use os comandos no menu para interagir comigo.\n"
        "Use /adicionar_estudo para começar."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Comandos disponíveis:\n"
        "/start - Iniciar o bot\n"
        "/help - Mostra esta mensagem de ajuda\n"
        "/adicionar_estudo - Adiciona um novo horário de estudo\n"
        "/listar_horas_estudo - Lista horários de estudo registrados\n"
        "/adicionar_sono - Registra horário de sono\n"
        "/listar_horas_sono - Lista horários de sono registrados\n"
        "/cancelar - Cancela a operação atual"
    )
    await update.message.reply_text(help_text)

async def listar_horas_estudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os horários registrados para o usuário atual."""
    user = update.effective_user
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Busca horários do usuário atual, ordenados pela data mais recente
    cursor.execute('''
        SELECT date, start_time, end_time, duration_hours, duration_minutes 
        FROM study_periods 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (user.id,))
    
    schedules = cursor.fetchall()
    conn.close()
    
    if not schedules:
        await update.message.reply_text("Você ainda não possui horários registrados.")
        return
    
    # Formatar resposta
    response = "Seus horários registrados:\n\n"
    for schedule in schedules:
        response += (
            f"Data: {schedule[0]}\n"
            f"Início: {schedule[1]}\n"
            f"Término: {schedule[2]}\n"
            f"Duração: {schedule[3]} horas e {schedule[4]} minutos\n\n"
        )
    
    await update.message.reply_text(response)

async def start(update: Update, context):
    # Salvar informações do usuário
    user = update.effective_user
    context.user_data['user_id'] = user.id
    context.user_data['user_name'] = user.first_name

    # Recuperar disciplinas anteriores
    previous_disciplines = get_previous_disciplines(user.id)

    if previous_disciplines:
        # Criar teclado inline com disciplinas anteriores
        keyboard = []
        row = []
        for discipline in previous_disciplines:
            button = InlineKeyboardButton(
                discipline, 
                callback_data=f"discipline_{discipline}"
            )
            row.append(button)
            
            # Criar nova linha a cada 2 botões
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        # Adicionar última linha se incompleta
        if row:
            keyboard.append(row)
        
        # Adicionar opção para digitar nova disciplina
        keyboard.append([InlineKeyboardButton("Digitar Outra", callback_data="discipline_custom")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Escolha uma disciplina das suas últimas estudadas ou selecione 'Digitar Outra':",
            reply_markup=reply_markup
        )
        return "DISCIPLINE_SELECTION"
    
    # Se não houver disciplinas anteriores, solicitar input manual
    await update.message.reply_text(
        "Qual disciplina você estudou?"
    )
    return DISCIPLINE

def get_previous_disciplines(user_id):
    """
    Recupera as disciplinas previamente estudadas pelo usuário.
    
    Args:
        user_id (int): ID do usuário
    
    Returns:
        list: Lista de disciplinas únicas estudadas anteriormente
    """
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Busca disciplinas únicas do usuário, ordenadas por frequência
    cursor.execute('''
        SELECT DISTINCT discipline, COUNT(*) as frequency 
        FROM study_periods 
        WHERE user_id = ? 
        GROUP BY discipline 
        ORDER BY frequency DESC 
        LIMIT 5
    ''', (user_id,))
    
    disciplines = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return disciplines

async def handle_discipline_selection(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "discipline_custom":
        # Se escolher digitar outro, solicitar input manual
        await query.edit_message_text("Digite o nome da disciplina:")
        return DISCIPLINE
    
    # Selecionar disciplina do teclado inline
    discipline_selected = query.data.split('_')[1]
    context.user_data['discipline'] = discipline_selected
    
    await query.edit_message_text(
        f"Disciplina selecionada: {discipline_selected}\n"
        "Agora, digite o horário de início (no formato HH:MM):"
    )
    return START_TIME

async def discipline(update: Update, context):
    # Método para quando o usuário digitar manualmente a disciplina
    discipline_input = update.message.text
    context.user_data['discipline'] = discipline_input
    
    await update.message.reply_text(
        "Vamos adicionar um novo horário. "
        "Por favor, digite o horário de início (no formato HH:MM):"
    )
    return START_TIME

async def get_custom_discipline(update: Update, context):
    discipline_input = update.message.text
    context.user_data['discipline'] = discipline_input
    
    await update.message.reply_text(
        "Vamos adicionar um novo horário. "
        "Por favor, digite o horário de início (no formato HH:MM):"
    )
    return START_TIME

async def get_start_time(update: Update, context):
    # Validar o formato do horário
    start_time = update.message.text
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', start_time):
        await update.message.reply_text(
            "Formato de horário inválido. Por favor, use o formato HH:MM:"
        )
        return START_TIME
    
    # Salvar o horário de início no contexto da conversa
    context.user_data['start_time'] = start_time
    
    await update.message.reply_text(
        f"Horário de início: {start_time}\n"
        "Agora, digite o horário de término (no formato HH:MM):"
    )
    return END_TIME

async def get_end_time(update: Update, context):
    # Validar o formato do horário
    end_time = update.message.text
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', end_time):
        await update.message.reply_text(
            "Formato de horário inválido. Por favor, use o formato HH:MM:"
        )
        return END_TIME
    
    # Salvar o horário de término
    context.user_data['end_time'] = end_time
    
    # Gerar teclado inline com datas
    keyboard = generate_date_keyboard()
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Selecione a data para este horário:",
        reply_markup=reply_markup
    )
    
    return SELECT_DATE

def generate_performance_keyboard():
    """Gera um teclado inline com porcentagens de performance."""
    performance_percentages = [
        0, 10, 20, 25, 30, 40, 45, 50, 60, 65, 70, 80, 90, 100
    ]
    
    keyboard = []
    row = []
    for perc in performance_percentages:
        button = InlineKeyboardButton(
            f"{perc}%",
            callback_data=f"performance_{perc}"
        )
        row.append(button)
        
        # Criar nova linha a cada 3 botões
        if len(row) == 3:
            keyboard.append(row)
            row = []
    
    # Adicionar última linha se incompleta
    if row:
        keyboard.append(row)
    
    # Botão para cancelar
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
    
    return keyboard

def generate_date_keyboard():
    """Gera um teclado inline com datas."""
    today = datetime.now()
    keyboard = []
    row = []
    
    # Adicionar hoje e próximos 6 dias
    for i in range(7):
        date = today - timedelta(days=i)
        button = InlineKeyboardButton(
            date.strftime("%d/%m/%Y"),
            callback_data=f"date_{date.strftime('%Y-%m-%d')}"
        )
        row.append(button)
        
        # Criar nova linha a cada 3 botões
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    
    # Adicionar última linha se incompleta
    if row:
        keyboard.append(row)
    
    # Botão para cancelar
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="cancel")])
    
    return keyboard

async def select_date(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    # Verificar se foi cancelado
    if query.data == "cancel":
        await query.edit_message_text("Operação cancelada.")
        return ConversationHandler.END
    
    # Extrair data selecionada
    selected_date = query.data.split('_')[1]
    context.user_data['selected_date'] = selected_date
    
    # Gerar teclado de performance
    keyboard = generate_performance_keyboard()
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Como foi sua performance durante o estudo?",
        reply_markup=reply_markup
    )
    
    return STUDY_PERFORMANCE

async def select_study_performance(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    # Verificar se foi cancelado
    if query.data == "cancel":
        await query.edit_message_text("Operação cancelada.")
        return ConversationHandler.END
    
    # Extrair performance
    performance = int(query.data.split('_')[1])
    
    # Recuperar Disciplina
    discipline = context.user_data.get('discipline')
    
    # Recuperar horários salvos
    start_time = context.user_data.get('start_time')
    end_time = context.user_data.get('end_time')
    selected_date = context.user_data.get('selected_date')
    
    # Converter horários para objetos datetime
    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%Y-%m-%d %H:%M')
    end_datetime = datetime.strptime(f"{selected_date} {end_time}", '%Y-%m-%d %H:%M')
        
    # Calcular a diferença
    time_difference = end_datetime - start_datetime
    
    # Converter a diferença para horas e minutos
    hours, remainder = divmod(time_difference.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    # Recuperar informações do usuário
    user_id = context.user_data.get('user_id')
    user_name = context.user_data.get('user_name')
    
    # Salvar no banco de dados SQLite
    save_study_schedule(user_id, user_name, selected_date, start_time, end_time, hours, minutes, discipline, performance)
    
    await query.edit_message_text(
        f"Horário de estudo registrado:\n"
        f"Usuário: {user_name}\n"
        f"Disciplina estudada: {discipline} \n"
        f"Data: {selected_date}\n"
        f"Início: {start_time}\n"
        f"Término: {end_time}\n"
        f"Duração: {hours} horas e {minutes} minutos\n"
        f"Performance: {performance}%"
    )
    
    # Limpar os dados do contexto
    del context.user_data['discipline']
    del context.user_data['start_time']
    del context.user_data['end_time']
    del context.user_data['selected_date']
    del context.user_data['user_id']
    del context.user_data['user_name']
    
    return ConversationHandler.END

async def cancel(update: Update, context):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

def main():
    # Inicializar o banco de dados
    init_database()
    
    # Configurar o aplicativo
    application = Application.builder().token(TOKEN).build()

    # Adicionar handlers de comandos gerais
    application.add_handler(CommandHandler('start', bot_start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('listar_horas_estudo', listar_horas_estudo))
    application.add_handler(CommandHandler('listar_horas_sono', listar_horas_sono))

    # Criar o conversation handler
    # Modificar o study_conv_handler para incluir os novos estados
    study_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('adicionar_estudo', start)],
        states={
            DISCIPLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, discipline),
                CallbackQueryHandler(handle_discipline_selection)
            ],
            "DISCIPLINE_SELECTION": [
                CallbackQueryHandler(handle_discipline_selection)
            ],
            "CUSTOM_DISCIPLINE": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_discipline)
            ],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_time)],
            END_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_time)],
            SELECT_DATE: [CallbackQueryHandler(select_date)],
            STUDY_PERFORMANCE: [CallbackQueryHandler(select_study_performance)]
        },
        fallbacks=[CommandHandler('cancelar', cancel)]
    )
    # Adicione o novo conversation handler para sono
    sleep_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('adicionar_sono', start_sleep_tracking)],
        states={
            'SLEEP_START_TIME': [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sleep_start_time)],
            'SLEEP_END_TIME': [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sleep_end_time)],
            'SLEEP_SELECT_DATE': [CallbackQueryHandler(select_sleep_date)],
            'SLEEP_QUALITY': [CallbackQueryHandler(select_sleep_quality)]
        },
        fallbacks=[CommandHandler('cancelar', cancel)]
    )

    # Adicionar o conversation handler à aplicação
    application.add_handler(study_conv_handler)
    application.add_handler(sleep_conv_handler)

    # Configurar os comandos do menu
    application.post_init = set_commands

    # Iniciar o bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()