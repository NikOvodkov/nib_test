import telebot
import time
from telebot import types
bot = telebot.TeleBot('6035640905:AAG_qigGMBvcqJF1wspG3-3rXSoiwvHYLuQ')



@bot.message_handler(content_types=['text'])
def get_text_messages(message):
    if message.text[0] == 'q':
        with open(f'command.txt', 'w') as f:
            f.write(message.text[1:])
        bot.send_message(message.from_user.id, "Принято в command.txt")
    else:
        bot.send_message(message.from_user.id, "Принято к сведению")


bot.polling(none_stop=True, interval=0)