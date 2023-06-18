import os.path
import time
from notifiers import get_notifier
TELETOKEN = '6035640905:AAG_qigGMBvcqJF1wspG3-3rXSoiwvHYLuQ'
TELECHAT = '497725007'
def print_telegram(mes='hello'):
    get_notifier('telegram').notify(token=TELETOKEN, chat_id=TELECHAT, message=mes)


while True:
    print('\r', 'Робот на ноуте работает', end='')
    with open(f'autorun.txt', 'w') as f:
        f.write(f"Robot rabotaet")
    if abs(os.path.getmtime('atable.pickle')-time.time()) > 60:
        print_telegram('Робот на ноуте остановился')
        print('\r', 'Робот на ноуте остановился', end='')
        break
        # os.system('python main.py')
    time.sleep(60)

