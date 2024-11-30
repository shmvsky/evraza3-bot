import asyncio
import logging
import io
import aiohttp
from decouple import config
from zipfile import ZipFile
from langchain.text_splitter import RecursiveCharacterTextSplitter
from telebot import TeleBot

# Конфигурация
TOKEN = config('TELEGRAM_TOKEN')
API_URL = "http://84.201.152.196:8020/v1/completions"
API_KEY = config('API_KEY')
bot = TeleBot(TOKEN)

logging.basicConfig(level=logging.INFO)

# Класс клиента EvrazaClient
class EvrazaClient:
  def __init__(self, base_url, token, model):
    self.base_url = base_url
    self.token = token
    self.model = model
    self.session = None

  async def init_session(self):
        self.session = aiohttp.ClientSession()
        self.session.headers.update({
            'Authorization': self.token
        })

  async def post_message(self, user_message, system_message="Отвечай на русском", max_tokens=1000, temperature=0.3):
    self.session.headers.update({
        'Content-Type': "application/json"
    })

    json_body = {
        'model': self.model,
        'messages': [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': user_message},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }

    try:
        async with self.session.post(self.base_url, json=json_body) as response:
            response.raise_for_status()
            result = await response.json()
            return result
    except aiohttp.ClientResponseError as e:
        logging.error(f"Ошибка выполнения POST-запроса: {e}")
        logging.error(f"Ответ сервера: {await e.response.text()}")
        return None

  async def close_session(self):
      if self.session:
          await self.session.close()

# Инициализация клиента EvrazaClient
evraza_client = EvrazaClient(
    'http://84.201.152.196:8020/v1/completions',
    'zoF7dZrAifcmXwNrjRom80wNeolSDnfl',
    'mistral-nemo-instruct-2407'
)

# Вспомогательные функции
def load_manual(manual_name: str) -> str:
    try:
        with open(f"{manual_name}", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        logging.error(f"Руководство {manual_name}.txt не найдено.")
        return "Руководство не загружено."

def create_report(report_path, contents):
    with open(report_path, "w", encoding="utf-8") as file:
        file.write(contents)
    return report_path

async def process_chunks(file_content: str, manual_name: str) -> str:
    """
    Разбивает содержимое файла на чанки и анализирует их с использованием LLM.
    """
    await evraza_client.init_session()

    chunk_size = 2500
    chunk_overlap = 500
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = text_splitter.split_text(file_content)

    report_contents = []
    manual_content = load_manual(manual_name)

    if manual_content == "Руководство не загружено.":
        return manual_content

    for i, chunk in enumerate(chunks):
        user_message = f"Проанализируй этот текст (чанк {i + 1}/{len(chunks)}):\n```\n{chunk}\n```"
        system_message = f"Руководство:\n```\n{manual_content}\n```"

        response = await evraza_client.post_message(user_message, system_message)
        if response and "choices" in response:
            report_contents.append(response['choices'][0]['message']['content'])
        else:
            report_contents.append(f"Чанк {i + 1}: Ошибка в обработке.")

    await evraza_client.close_session()

    final_report = "\n".join(report_contents)
    create_report("report.txt", final_report)
    return "report.txt"


async def process_file(file_content: str, file_extension: str) -> str:
    """
    Обрабатывает файл в зависимости от его расширения (.py, .ts, .cs).
    """
    manual_mapping = {
        ".py": "python.txt",
        ".ts": "typescript.txt",
        ".cs": "csharp.txt"
    }

    manual_name = manual_mapping.get(file_extension)
    if not manual_name:
        return f"Файлы с расширением {file_extension} не поддерживаются."

    return await process_chunks(file_content, manual_name)

async def process_archive(zip_file):
    """
    Обрабатывает архив, включая файлы в папках, и анализирует их содержимое.
    """
    supported_extensions = {".py", ".ts", ".cs"}  # Поддерживаемые расширения
    with ZipFile(io.BytesIO(zip_file), 'r') as archive:
        reports = []

        for file in archive.namelist():
            # Пропуск директорий
            if file.endswith('/'):
                continue

            file_extension = f".{file.split('.')[-1]}"
            try:
                with archive.open(file) as nested_file:
                    # Читаем содержимое файла
                    file_content = nested_file.read().decode("utf-8")

                    if file_extension not in supported_extensions:
                        reports.append(f"Файл: {file}\n\nОшибка: Файлы с расширением {file_extension} не поддерживаются.")
                        continue

                    # Анализируем содержимое файла
                    report_path = await process_file(file_content, file_extension)
                    # Читаем содержимое отчета
                    with open(report_path, "r", encoding="utf-8") as report_file:
                        report_contents = report_file.read()
                    reports.append(f"Файл: {file}\n\n{report_contents}")

            except UnicodeDecodeError:
                reports.append(f"Файл: {file}\n\nОшибка: Невозможно прочитать файл в формате текста.")
            except Exception as e:
                reports.append(f"Файл: {file}\n\nОшибка: {str(e)}")

    # Формируем итоговый отчет
    final_report = "\n\n".join(reports)
    return create_report("report.txt", final_report)


@bot.message_handler(content_types=['document'])
def handle_document(message):
    """
    Обрабатывает документ, переданный пользователем, и отправляет отчёт.
    """
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    file_extension = f".{message.document.file_name.split('.')[-1]}"
    if file_extension == ".zip":
        result_report = asyncio.run(process_archive(downloaded_file))
        r_type = "архив"
    else:
        file_content = downloaded_file.decode("utf-8")
        result_report = asyncio.run(process_file(file_content, file_extension))
        r_type = f"файл {file_extension}"

    bot.reply_to(message, f"Ваш {r_type} был обработан, результаты прикреплены к сообщению.")
    with open(result_report, "rb") as report_file:
        bot.send_document(chat_id=message.chat.id, document=report_file)

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message, "Привет! Я бот для проверки проектов. Отправьте мне файл или архив для обработки.")

@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    bot.reply_to(message, "Я не знаю, что делать с этим. Пожалуйста, отправьте мне файл или архив для обработки.")

if __name__ == '__main__':
    print("Bot started")
    bot.infinity_polling()

