import io
from zipfile import ZipFile

from decouple import config
from telebot import TeleBot

TOKEN = config('TELEGRAM_TOKEN')


#TODO Допилить логику согдания отчета
def create_report(report_path, contents):
    with open(report_path, "w") as file:
        file.write(contents)
    return report_path

#TODO Допилить логику обработки файла
def process_file(file) -> str:
    print("Processing file:", file)
    report = create_report("report.txt", "Hello world")
    return report


#TODO Допилить логику обработки архива
def process_archive(zip_file):
    with ZipFile(io.BytesIO(zip_file), 'r') as archive:
        for file in archive.namelist():
            with archive.open(file) as nested_file:
                file_contents = nested_file.readlines()
                # Здесь должна быть логика обработки архива

    report = create_report("report.txt", "Hello world")
    return report

bot = TeleBot(TOKEN)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    if message.document.file_name.endswith('.zip'):
        result_report = process_archive(downloaded_file)
        r_type = "архив"
    else:
        result_report = process_file(downloaded_file)
        r_type = "файл"

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
