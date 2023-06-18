"""  Команды dailybuy:
stop_working - останавливает торговлю из-за чего закрывается сессия (просто делаем asec.active=False)
start_working - запускаем торговлю (просто делаем asec.active=True)
change_quantity - меняем размер лота на число в поле price
    Команды goodwin:
change_quantity - меняем размер лота на число в поле price
start_working - запускаем торговлю, выставив заявку, стоп и тэйк-профит
stop_working - останавливает торговлю, сняв все заявки


"""
import pickle
from datetime import datetime
from pprint import pprint
from time import sleep
from tinkoff.invest import Quotation, Client, InstrumentIdType, GetOperationsByCursorRequest, OrderDirection, OrderType, \
    StopOrderDirection
from tinkoff.invest.grpc.instruments_pb2 import INSTRUMENT_STATUS_BASE
from tinkoff.invest.grpc.operations_pb2 import OPERATION_TYPE_BUY, OPERATION_TYPE_SELL
from tinkoff.invest.grpc.orders_pb2 import EXECUTION_REPORT_STATUS_CANCELLED, EXECUTION_REPORT_STATUS_NEW, \
    EXECUTION_REPORT_STATUS_FILL, EXECUTION_REPORT_STATUS_PARTIALLYFILL, EXECUTION_REPORT_STATUS_REJECTED
from tinkoff.invest import Client, InstrumentIdType, GenerateBrokerReportRequest, PortfolioResponse, RequestError, \
    OrderDirection, OrderType, Quotation, OperationState, OperationType, OrderExecutionReportStatus
from math import *
from notifiers import get_notifier
from tinkoff.invest.grpc.stoporders_pb2 import STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL

TOKEN = 't.ipqfr5OxYMJNaUzEKkZDYKiEvNNovOh79_aT7FKSfkgboTFA_zhHkHY7eB4c4Uapu7cFjnSB68R6Gr92tk6tiA'
TELETOKEN = '6035640905:AAG_qigGMBvcqJF1wspG3-3rXSoiwvHYLuQ'
TELECHAT = '497725007'
ACCOUNT = {'id': '2008835809', 'curevaluation': 0, 'usedmoney': 0, 'freebrokermoney': 0,
           'curfreemymoney': 0, 'minfreemymoney': 999999999, 'maxfreemymoney': -999999999}
SECS = [{'figi': 'BBG333333333', 'ticker': 'TMOS', 'classcode': 'TQTF', 'active': True, 'lot': 2, 'name': 'dailybuy'},
        {'figi': 'BBG333333333', 'ticker': 'TMOS', 'classcode': 'TQTF', 'active': False, 'lot': 2, 'name': 'stopper'},
        {'figi': 'BBG000000001', 'ticker': 'TRUR', 'classcode': 'TQTF', 'active': False, 'lot': 2, 'name': 'goodwin'}]
ATABLE = []
ASEC = {'figi': 'BBG333333333', 'ticker': 'TMOS', 'classcode': 'TQTF', 'lot': 2, 'delta': 0, 'a': None}  # TMOS
# ASEC = {'figi': 'BBG000000001', 'ticker': 'TRUR', 'classcode': 'TQTF', 'lot': 2, 'delta': 0, 'a': None}  # TRUR


STOPHANGINGORDERS = 10000
COMMAND = None


# переменные Тинькофф Апи
# PORTFOLIO = None  # состояние портфеля, - третье по скорости обновление данных (скорость 3)
# POSITIONS = None  # позиции в портфеле, - второе по скорости обновление данных (скорость 2)
# MARGIN = None  # деньги брокера, доступные для покупки
# BOOK = None  # стакан заявок
# OPERATIONS = None  # операции по портфелю, - четвёртое по скорости обновление данных (скорость 4)
# SHEDULES = None  # расписания торгов
# ORDERSTATES - самое быстрое обновление данных (скорость 1)
API = {'PORTFOLIO': None, 'POSITIONS': None, 'MARGIN': None, 'BOOKS': None, 'OPERATIONS': {},
       'SHEDULES': None, 'INSTRUMENTS': {}, 'ORDERSTATES': None, 'REPORT': None, 'CANDLES': {}}
ACTIVEORDERSTATUSES = [EXECUTION_REPORT_STATUS_NEW, EXECUTION_REPORT_STATUS_PARTIALLYFILL]
PASSIVEORDERSTATUSES = [EXECUTION_REPORT_STATUS_FILL, EXECUTION_REPORT_STATUS_REJECTED, EXECUTION_REPORT_STATUS_CANCELLED]


# объект - инструмент для торговли с текущими характеристиками алгоритма
class Asec:
    def __init__(self):
        self.figi = None
        self.ticker = None
        self.name = None  # имя экземпляра объекта алгоритма
        self.classcode = None
        self.lot = 0
        self.delta = 0  # минимальный шаг цены в стакане
        self.maxprice = 0  # максимальная допустимая цена в заявке
        self.minprice = 0  # минимальная допустимая цена в заявке
        self.highcandleprice = 0  # максимальная цена в текущей минутной свече (используется для проверки стопов)
        self.lowcandleprice = 0  # минимальная цена в текущей минутной свече (используется для проверки стопов)
        self.preprice = 0  # цена инструмента в предыдущую итерацию алгоритма
        self.curprice = 0  # текущая цена алгоритма
        self.changeprice = 0  # флаг, индицирующий изменение цены, достаточное для следующего шага алгоритма
        self.run = 0  #  номер итерации цикла алгоритма
        self.day = 0
        self.session = 'closed'  #  текущее состояние сессии торговли по алгоритму (не биржевая сессия!)
        self.ttable_profit = 0
        self.broker_open_profit = 0
        self.broker_cur_profit = 0
        self.moneyused = 0
        self.bought = 0
        self.bstable = []
        self.stable = []
        self.yld = 0
        self.expected_yield_fifo = 0
        self.expected_yield = 0
        self.normal_closed = False
        self.openedtrades = 0
        self.closedtrades = 0
        self.hangorders = 0
        self.maxhangorders = 1
        self.opened_profit = 0  # данное поле должно быть у асека и сессии
        self.closed_profit = 0  # данное поле должно быть у асека и сессии
        self.active = False  # торгуется ли сейчас данный алгоритм


# объект купля-продажа (сделка) - базовый элемент алгоритма
class Buysell:
    def __init__(self):
        self.id = None
        self.buytime = None
        self.selltime = None
        self.buyprice = None
        self.sellprice = None
        self.profit = 0  # в БС достаточно одного профита, который считается и пока БС открыт и когда закрыт
        self.lot = None
        self.buyorderid = None
        self.sellorderid = None
        self.status = False  # True продажа выполнена False выполнена только покупка
        self.overpriced = False  # цена продажи слишком высока, продажу не выставить в стакан
        self.quantity = None
        self.quantity_done = None
        self.quantity_rest = None
        self.cancel_date_time = None
        self.orders = []
        self.stop_orders = []
        self.original = None
        self.replaced = False  # если объединяем байселы, то старый обнуляем, присваивая сюда True
        self.internal = None  # сделка открыта и закрыта внутри одной сессии
        self.external = None  # по сделке не было операций внутри этой сессии
        self.direction = None  # long/short

class Order:
    def __init__(self):
        self.t_create = None
        self.t_cancel = None
        self.t_execute = None
        self.id = None
        self.q_done = None
        self.q_rest = None
        self.q = None
        self.direction = None  # buy, sell
        self.status = 'created'  # created (роботом) -> sent (на сервер)-> received (сервером)->
        # active -> cancelling/executing -> cancelled/executed
        self.price = None
        self.t_getorders = None
        self.t_getportfolio = None
        self.t_getoperations = None
        self.t_getoperations_trades = None
        self.trades = []
        self.executedprice = None
        self.order_id = None
        self.execution_report_status = None
        self.urgency = None  # deferred, immediate
        self.type = None  # market, limit
        self.dispatched = False  # False, True - обработана диспетчером заявок (отправлена на сервер)
        self.stop_price = None  # стоп-цена по достижении которой заявка активируется
        self.overpriced = False  # цена заявки вне разрешенного диапазона, заявку не выставить в стакан



class Trade:
    def __init__(self):
        self.order = None
        self.id = None
        self.q = None
        self.d = None
        self.p = None
        self.t = None


class Command:
    def __init__(self):
        self.name = None  # имя команды
        self.aname = None  # имя алгоритма, для которого предназначена команда (если есть)
        self.ticker = None  # имя тикера, для которого предназначена команда (если есть)
        self.price = None  # цена, если она нужна для исполнения команды (если есть)
        self.figi = None  # имя figi, для которого предназначена команда (если есть)
        self.d1 = None  # запасное поле 1 (если есть)
        self.d2 = None  # запасное поле 2 (если есть)
        self.d3 = None  # запасное поле 3 (если есть)
        self.d4 = None  # запасное поле 4 (если есть)
        self.d5 = None  # запасное поле 5 (если есть)



class Session:
    def __init__(self):
        self.open_datetime = None  # дата и время открытия сессии в utc
        self.open_datetime = None
        self.id = None
        self.hang = 0  # куплено лотов (в 1 лоте содержится lot бумаг) за сессию на текущий момент
        self.maxhung = 0  # максимум висящих лотов за сессию
        self.moneused = None  # использованные за сессию бумаги в денежном эквиваленте = maxhung*curprice
        self.bought = None  # куплено бумаг = hang * ALGOSEC['lot']
        self.profitrub = None  # прибыль за сессию в рублях
        self.profit = 0  # прибыль в процентах = profitrub/maxhung
        self.yield_ = 0  # closedtrades/maxhung*0,0005(шаг цены)*2
        self.openedtrades = 0  # открытых сделок
        self.closedtrades = 0  # закрытых сделок
        self.lot = 1  # сколько бумаг в лоте
        self.delta = None  # стоимость шага цены
        self.curprice = 0  # текущая цена
        self.revaluation = 0  # переоценка портфеля с предыдущей сессии
        self.close_price = 0  # цена закрытия текущей сессии (она же lastprice)
        self.open_price = 0  # цена открытия текущей сессии
        self.ttable_profit = 0  # результат всех сделок по инструменту за день
        self.ttable_profit_abs = 0  # результат всех сделок по инструменту за день + переоценка ранее набранного портфеля
        self.api_yield_open = 0  # доход по инструменту из апи Тинькофф при открытии
        self.api_yield_close = 0  # доход по инструменту из апи Тинькофф при закрытии (текущая)
        self.bought_all = 0  # куплено единиц за все сессии
        self.session_opened_closed_profit = 0  # доход со сделок открытых и закрытых внутри сессии
        self.session_profit = 0  # доход со сделок открытых и закрытых внутри сессии + переоценка текущих позиций



def cantrade(client, asec):  #  блокирует торговлю и отправляет сообщение, если в портфеле критические изменения
    ret = False
    if (asec.hangorders < STOPHANGINGORDERS) and asec.active and \
        (client.market_data.get_trading_status(instrument_id=asec.figi).api_trade_available_flag) and \
        (client.market_data.get_trading_status(instrument_id=asec.figi).trading_status == 5) and \
            (('10:01:00' < togmt(date=False) < '13:00:00') or ('13:01:00' < togmt(date=False) < '16:00:00')
            or ('16:01:00' < togmt(date=False) < '18:39:00') or ('19:06:00' < togmt(date=False) < '23:49:00')):
        ret = True
    elif asec.name == 'goodwin':
        ret = True
    else:
        if ('09:00:00' < togmt(date=False) < '09:00:10'):
            print_telegram(str(togmt(date=False)))
        ret = False
    return ret

# (('10:01:00' < togmt(date=False) < '14:00:00') or ('14:01:00' < togmt(date=False) < '18:39:00')
# or ('19:06:00' < togmt(date=False) < '23:49:00')):
# (('10:01:00' < togmt(date=False) < '13:00:00') or ('13:01:00' < togmt(date=False) < '16:00:00')
# or ('16:01:00' < togmt(date=False) < '18:39:00')):
# (('00' < togmt(date=False)[3:5] < '59')):
# (('10:00:30' < togmt(date=False) < '18:39:30') or ('19:05:30' < togmt(date=False) < '23:49:30')):
# (('10:01:00' < togmt(date=False) < '13:00:00') or ('13:01:00' < togmt(date=False) < '16:00:00')
# or ('16:01:00' < togmt(date=False) < '18:39:00') or ('19:05:30' < togmt(date=False) < '23:49:30')):


def get_figi(client, ticker):
    itypes = {'futures', 'share', 'etf'}
    figi = None
    s = []
    r = client.instruments.find_instrument(query=ticker).instruments
    r2 = []
    for ins in r:
        if ins.ticker.lower() == ticker.lower() and (ins.instrument_type in itypes) and ins.api_trade_available_flag:
            r2.append(ins)
    if len(r2) == 0:
        print_telegram(mes='Инструмент из команды не найден у брокера!')
        figi = None
    elif len(r2) > 1:
        for ins in r2:
            if (ins.ticker.lower() == ticker.lower()) and (ins.instrument_type in itypes) and ins.api_trade_available_flag:
                s.append(ins)
        if len(s) > 1:
            print_telegram(mes=f'Несколько инструментов найдено:{s}')
            figi = None
    elif len(r2) == 1:
        print(r2[0])
        figi = r2[0].figi
    return figi


def readcommand(client):
    try:  # читаем команду
        f = open(f'command.txt', 'r+', encoding="cp1251")
        filestr = f.read()
        f.close()
        # очищаем файл
        f = open('command.txt', 'w+')
        f.seek(0)
        f.close()
    except:
        print('File error!')
        filestr = ''
    if len(filestr) > 0:
        command = Command()
        #выяснить формат команды
        if filestr[:8] == 'command ':
            command.name = filestr[8:filestr.find('aname')-1]
            command.aname = filestr[filestr.find('aname ')+6:filestr.find('ticker')-1]
            command.ticker = filestr[filestr.find('ticker ') + 7:filestr.find('price') - 1]
            command.price = float(filestr[filestr.find('price ') + 6:])
            command.figi = get_figi(client, command.ticker)
            pprint(vars(command))
            if command.figi is None:
                command = None

            # command testit aname goodwin ticker gmkn price 30.76
        else:
        # найти в строке тикер и найти его в базе брокера
            start = filestr.find('#')
            ticker = filestr[start + 1:]
            end = ticker.find(' ')
            ticker = ticker[:end]
            if start == -1 or end == -1:
                ticker = ''
            # найти в команде стоплосс
            start = filestr.lower().find('стоп ')
            stop = filestr[start + 5:]
            end = min(stop.find(' '), stop.find('\n'))
            stop = stop[:end]

            if start == -1 or end == -1:
                stop = 0
            if ticker != '' and stop != 0:
                command.figi = get_figi(client, ticker)
                if command.figi is None:
                    command = None
                else:
                    command.name = 'start'
                    command.aname = 'goodwin'
                    command.ticker = ticker
                    command.price = stop
                    pprint(vars(command))
            else:
                print_telegram(mes='Недостаточно информации в команде!')
                command = None
    else:
        command = None
    return command


def algo_goodwin(asec, stop, client, ticker, atable, command):
    newasec = True
        # for i, a in enumerate(atable):
        #     #  заполнить asec на инструмент
        #     if (a.figi == r[0].figi) and (not a.active):
        #         newasec = False
        #         atable[i].name = a['goodwin']
        #         atable[i].active = True
        #         atable[i] = algo_goodwin(a, stop)
        #         break
        #         # заполняем текущий asec
        # if newasec:
        #     # создаем новый asec
        #     B = Asec()
        #     B.figi = r[0].figi
        #     B.classcode = r[0].class_code
        #     B.ticker = r[0].ticker
        #     B.run += 1
        #     B.name = a['goodwin']
        #     B.lot = 1
        #     B.active = True
        #     B = algo_goodwin(B, stop)
        #     atable.append(B)
            #  зная текущую цену и стоп - вычисляем направление сделки
            #  запускаем заявку и стоп-заявку
            # sellorder, asec = api_send_order(client, account, asec, lots=asec.q, lst.open_direction,
            #                                  price=lst.open_price)

    # sellorder, asec = api_send_order(client, account, asec, lots=asec.q, lst.open_direction, price=lst.open_price)
    # api_send_stop_order(client, account, asec, aseq.q, lst.close_direction, lst.stop_price_loss, lst.price_loss, stop_order_type=)
    # api_send_stop_order(client, account, asec, aseq.q, lst.close_direction, lst.stop_price_profit, lst.price_profit, stop_order_type=)
    return newasec


def api_get_allsecs(client, account, atable):
    etfs = [{'figi': item.figi, 'ticker': item.ticker, 'classcode': item.class_code, 'active': False, 'lot': 1, 'name': None}
            for item in client.instruments.etfs(instrument_status=INSTRUMENT_STATUS_BASE).instruments]
    shares = [{'figi': item.figi, 'ticker': item.ticker, 'classcode': item.class_code, 'active': False, 'lot': 1, 'name': None}
            for item in client.instruments.shares(instrument_status=INSTRUMENT_STATUS_BASE).instruments]
    futures = [{'figi': item.figi, 'ticker': item.ticker, 'classcode': item.class_code, 'active': False, 'lot': 1, 'name': None}
            for item in client.instruments.futures(instrument_status=INSTRUMENT_STATUS_BASE).instruments]
    return etfs + shares + futures


def readbstable(client, account, atable):  # считывает BSTABLE из файла и возвращаем его через return
    try:
        f = open(f'atable.pickle', 'rb')
        atable = pickle.load(f)
        f.close()
        for i, a in enumerate(atable):  # новый вариант с таблицей объектов ATABLE
            atable[i].normal_closed = False
            atable[i].run += 1
    except:
        secbase = api_get_allsecs(client, account, atable)
        for a in secbase:
            B = Asec()
            B.figi = a['figi']
            B.classcode = a['classcode']
            B.ticker = a['ticker']
            B.run += 1
            B.name = a['name']
            B.lot = a['lot']
            B.active = a['active']
            atable.append(B)
            for sss in SECS:
                if (a['figi'] == sss['figi']) and (not a['active']) and sss['active']:
                        B = Asec()
                        B.name = sss['name']
                        B.lot = sss['lot']
                        B.active = sss['active']
                        B.figi = a['figi']
                        B.classcode = a['classcode']
                        B.ticker = a['ticker']
                        B.run += 1
                        atable.append(B)
    # if command:
    #     B = Asec()
    #     B.figi = a['figi']
    #     B.name = a['name']
    #     B.classcode = a['classcode']
    #     B.ticker = a['ticker']
    #     B.lot = a['lot']
    #     if a['active']:
    #         B.active = True
    #     B.run += 1
    #     atable.append(B)
    return atable, readcommand(client)


def writebstable(atable):  # записывает BSTABLE в файл
    # print('writestable BSTABLE:')
    # for i in asec['bstable']:
    #     pprint(vars(i.orders[0]))
    # pprint(asec)

    # with open(f'asec{asec["a"].ticker}.pickle', 'wb') as f:
    #     asec['a'].normal_closed = True
    #     pickle.dump(asec, f)
    with open(f'atable.pickle', 'wb') as f:
        for i, a in enumerate(atable):  # новый вариант с таблицей объектов ATABLE
            atable[i].normal_closed = True
        pickle.dump(atable, f)




def togmt(dt=0, date=True, gmt=3):  # dt=0 - выдаём utc.now +3 часа, dt=1 -
    if date:
        if dt == 0:
            dt = datetime.utcnow().strftime("%y.%m.%d %H:%M:%S")
        else:
            dt = dt.strftime("%y.%m.%d %H:%M:%S")
        dt = dt[:9] + str(int(dt[9:11]) + gmt).rjust(2, '0') + dt[11:]
    else:
        if dt == 0:
            dt = datetime.utcnow().strftime("%H:%M:%S")
        else:
            dt = dt.strftime("%H:%M:%S")
        dt = str(int(dt[:2]) + gmt).rjust(2, '0') + dt[2:]
    return dt


def quot_to_float(q):  #  переводит цену из формата Quotion в Float
    if q.nano == 0:
        return q.units
    else:
        i = -1
        while q.nano % 10**(i+1) == 0:
            i += 1
        return q.units + round(q.nano / 1e9, 9-i)  # используем round() чтобы избавиться от "0.4500000001"


def float_to_quot(f):  #  переводит цену из формата Float в Quotion
    return Quotation(int(f // 1), round((f - f // 1) * 1e9))


def get_digits(number):  # вычисляем количество знаков после запятой в числе формата float
    s = str(number)
    if '.' in s:
        return abs(s.find('.') - len(s)) - 1
    else:
        return 0


def roundab(a, b):  #  округляет число a до числа b
    if isclose(0, b):
        print('Округление до 0!')
        return a
    else:
        return round(b * round(a / b, 0), get_digits(b))


# округляет число в формате Quotation до шага цены или возвращает шаг цены
def roundsec(client, figi, q=Quotation(0, 0)):
    x = client.instruments.etf_by(id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                                  id=figi).instrument.min_price_increment
    if q == Quotation(0, 0):
        q = x
    else:
        q = float_to_quot(roundab(quot_to_float(q), quot_to_float(x)))
    return q


def asectostr(asec):  # форматирует массив ASEC для вывода
    # return f" run:{str(asec['run']).ljust(6,' ')} lot:{str(asec['lot']).ljust(3,' ')}" \
    #        f" opened:{str(asec['openedtrades']).ljust(4,' ')} closed:{str(asec['closedtrades']).ljust(4,' ')}" \
    #        f" hung:{str(asec['hangorders']).ljust(4,' ')} used:{str(int(asec['moneyused'])).ljust(5,' ')}" \
    #        f" bought:{str(asec['bought']).ljust(5,' ')} ordrsprft:{str(asec['ttable_profit']).ljust(3, ' ')}" \
    #        f" apiyld_fifo:{str(asec['expected_yield_fifo']).ljust(6, ' ')} apiyld:{str(asec['expected_yield']).ljust(6, ' ')}" \
    #        f" pre:{asec['preprice']} cur:{asec['curprice']}"
    return f" run:{str(asec.run).ljust(6, ' ')} lot:{str(asec.lot).ljust(3, ' ')}" \
           f" opened:{str(asec.openedtrades).ljust(4, ' ')} closed:{str(asec.closedtrades).ljust(4, ' ')}" \
           f" hung:{str(asec.hangorders).ljust(4, ' ')} used:{str(int(asec.moneyused)).ljust(5, ' ')}" \
           f" bought:{str(asec.bought).ljust(5, ' ')} ordrsprft:{str(asec.ttable_profit).ljust(3, ' ')}" \
           f" high:{str(asec.highcandleprice).ljust(6, ' ')} low:{str(asec.lowcandleprice).ljust(6, ' ')}" \
           f" pre:{asec.preprice} cur:{asec.curprice}"


def accounttostr(account):  # форматирует массив ACCOUNT для вывода
    return f" used:{str(account['usedmoney']).ljust(7, ' ')} myfree:{str(account['curfreemymoney']).ljust(7, ' ')}" \
           f" mymaxfree:{str(account['maxfreemymoney']).ljust(7, ' ')} myminfree:{str(account['minfreemymoney']).ljust(7, ' ')}" \
           f" brfree:{str(account['freebrokermoney']).ljust(7, ' ')} oc:{str(account['curevaluation']).ljust(7, ' ')}"


def save_ttable(asec):  # ведет учет сделок на сервере и дублирует информацию по ОТКРЫТОЙ сессии в файл
    bquantity, squantity, result = 0, 0, 0
    for BS in asec.bstable:
        for j in BS.orders:
            for i in j.trades:
                if i.d == 'b':
                    bquantity += i.q
                    result -= i.q * i.p
                if i.d == 's':
                    squantity += i.q
                    result += i.q * i.p
    result = roundab(result + (bquantity - squantity) * asec.curprice, asec.delta)
    asec.ttable_profit = result
    with open(f'{asec.name}_ttable.txt', 'w') as f:
        f.write(f"qbuy={bquantity}, qsell={squantity}, result={result}, curtime={togmt()}\n")
        f.write(f"order       oper price  tradeid    q   time\n")
        for BS in asec.bstable:
            for j in BS.orders:
                for i in j.trades:
                    if i.d == 's':
                        f.write(f"{i.order} s    {str(i.p).ljust(6, ' ')} {i.id} "
                                f"{str(i.q).ljust(3, ' ')} {str(i.t).ljust(10, ' ')}\n")
                    else:
                        f.write(f"{i.order} b    {str(i.p).ljust(6, ' ')} {i.id} "
                                f"{str(i.q).ljust(3, ' ')} {str(i.t).ljust(10, ' ')}\n")
    return asec


def save_otable(asec):  # ведет учет заявок на сервере и дублирует информацию по открытой СЕССИИ в файл
    bquantity, squantity, result = 0, 0, 0
    for BS in asec.bstable:
        for i in BS.orders:
            if i.direction == 'b':
                bquantity += i.q_done
                result -= i.q_done * i.price
            if i.direction == 's':
                squantity += i.q_done
                result += i.q_done * i.price
    result = roundab(result + (bquantity - squantity) * asec.curprice, asec.delta)
    with open(f'{asec.name}_otable.txt', 'w') as f:
        f.write(f"qbuy={bquantity}, qsell={squantity}, result={result}, curtime={togmt()}\n")
        f.write(f"time     oper price  orderid     q   qd  qr  canceltime "
                f"orders   operations   status\n")
        for BS in asec.bstable:
            for i in BS.orders:
                if i.direction == 's':
                    f.write(f"{i.t_create} s    {str(i.price).ljust(6, ' ')} {i.id} {str(i.q).ljust(3, ' ')} "
                            f"{str(i.q_done).ljust(3, ' ')} {str(i.q_rest).ljust(3, ' ')} {str(i.t_cancel).ljust(10, ' ')} "
                            f"{str(i.t_getorders).ljust(10, ' ')}   "
                            f"{str(i.t_getoperations).ljust(10, ' ')}   {i.status}\n")
                else:
                    f.write(f"{i.t_create} b    {str(i.price).ljust(6, ' ')} {i.id} {str(i.q).ljust(3, ' ')} "
                            f"{str(i.q_done).ljust(3, ' ')} {str(i.q_rest).ljust(3, ' ')} {str(i.t_cancel).ljust(10, ' ')} "
                            f"{str(i.t_getorders).ljust(10, ' ')}   "
                            f"{str(i.t_getoperations).ljust(10, ' ')}   {i.status}\n")
    return asec


def save_bstable(asec):  # ведет учет заявок на сервере и дублирует информацию в файл
    quantity, buyprice, sellprice = 0, 0, 0
    for i in asec.bstable:
        if i.status == False:
            quantity += i.lot
            buyprice += i.lot * i.buyprice
            sellprice += i.lot * i.sellprice
    if quantity > 0:
        buyprice = roundab(buyprice / quantity, asec.delta)
        sellprice = roundab(sellprice / quantity, asec.delta)
    with open(f'{asec.name}_bstable_opened.txt', 'w') as f:
        f.write(f"buyprice={buyprice}, quantity={quantity}, sellprice={sellprice}, curtime={togmt()}\n")
        f.write(f"buyorderid  bprice buytime           lot sellorderid sprice selltime           original\n")
        for i in asec.bstable:
            if i.status == False:
                f.write(f"{str(i.buyorderid).ljust(11,' ')} {str(i.buyprice).ljust(6,' ')} {str(i.buytime).ljust(18,' ')}"
                        f"{str(i.lot).ljust(3,' ')} {str(i.sellorderid).ljust(11,' ')} {str(i.sellprice).ljust(6,' ')}"
                        f" {str(i.selltime).ljust(18,' ')} {str(i.original).ljust(8,' ')} {str(i.status).ljust(5,' ')}"
                        f" {str(i.profit).ljust(6,' ')}\n")
    quantity, buyprice, sellprice = 0, 0, 0
    for i in asec.bstable:
        #if i.status == True:
            quantity += i.lot
            buyprice += i.lot * i.buyprice
            sellprice += i.lot * i.sellprice
    if quantity > 0:
        buyprice = roundab(buyprice / quantity, asec.delta)
        sellprice = roundab(sellprice / quantity, asec.delta)
    with open(f'{asec.name}_bstable_all.txt', 'w') as f:
        f.write(f"buyprice={buyprice}, quantity={quantity}, sellprice={sellprice}, curtime={togmt()}\n")
        f.write(f"buyorderid  bprice buytime           lot sellorderid sprice selltime           original status profit\n")
        for i in asec.bstable:
            f.write(f"{str(i.buyorderid).ljust(11,' ')} {str(i.buyprice).ljust(6,' ')} {str(i.buytime).ljust(18,' ')}"
                    f"{str(i.lot).ljust(3,' ')} {str(i.sellorderid).ljust(11,' ')} {str(i.sellprice).ljust(6,' ')}"
                    f" {str(i.selltime).ljust(18,' ')} {str(i.original).ljust(8,' ')} {str(i.status).ljust(5,' ')}"
                    f" {str(i.profit).ljust(6,' ')}\n")
    return asec


def shake_orders(client, account, asec):  # снимает зависшую заявку и выставляет её с увеличенной на 1 шаг ценой
    if asec.run % 1008 == 0:  # примерно раз в 5*1008 секунд 5*208
        print('\nShakeorders')
        # print_telegram(asectostr(asec))
        # for i in BSTABLE:
        #     pprint(vars(i))

        bstable2 = []
        if len(asec.bstable) > 0:  # если таблица сделок не пуста
            j = roundab(asec.curprice - asec.delta, asec.delta)
            while j < asec.maxprice:
                j += asec.delta
                BS = Buysell()  # создаём новую строку в таблице и инициализируем поля
                BS.lot = asec.lot
                BS.sellprice = 0
                BS.buyprice = 0
                BS.buytime = togmt()
                BS.original = False
                num = 0
                for i in asec.bstable:  # пробегаем по таблице сделок
                    if (not i.status) and isclose(i.sellprice, j):  # если сделка не закрыта, добавляем её в новую сделку, а старую удаляем
                        if i.sellorderid != None:
                            asec = api_cancel_order(client, account, asec, i.sellorderid)
                            # client.orders.cancel_order(order_id=i.sellorderid, account_id=account['id'])
                        num += i.lot
                        BS.sellprice = BS.sellprice + i.lot * i.sellprice
                        BS.buyprice = BS.buyprice + i.lot * i.buyprice
                if num > 0:  # если старые сделки были удалены в вышерасположенном цикле, то создаем новую сделку взамен
                    BS.sellprice = roundab(BS.sellprice / num + asec.delta, asec.delta)
                    BS.buyprice = roundab(BS.buyprice / num, asec.delta)
                    BS.lot = num
                    BS.status = False
                    if BS.sellprice > asec.maxprice:  # если цена для выставления в корзину слишком высока
                        BS.overpriced = True  # пометим это флагом
                    else:
                        BS.overpriced = False  # иначе снимем флаг и выставим заявку
                        sellorder, asec = api_send_order(client, account, asec, lots=BS.lot,
                                                direction=OrderDirection.ORDER_DIRECTION_SELL,
                                                price=BS.sellprice)
                        BS.sellorderid = sellorder.order_id
                        BS.buytime = togmt()  # и сменим время покупки на текущее
                    bstable2.append(BS)
            for i in asec.bstable:
                if i.status:
                    bstable2.append(i)
            asec.bstable = bstable2
        else:
             asec.bstable = []

        # print('Finish shakeorders, BSTABLE: ')
        # for i in BSTABLE:
        #     pprint(vars(i))
    return asec


def api_cancel_order(client, account, asec, orderid):
    # отразить изменения в таблице заявок asecorder
    state = client.orders.get_order_state(order_id=orderid, account_id=account['id'])
    # print('Состояние заявки:', state)
    if state.execution_report_status in ACTIVEORDERSTATUSES:
        # print('Отменяем заявку без отмены')
        client.orders.cancel_order(order_id=orderid, account_id=account['id'])
        sleep(1)
        state = client.orders.get_order_state(account_id=account['id'], order_id=orderid)
        for j, BS in enumerate(asec.bstable):
            for i, val in enumerate(BS.orders):
                if val.id == orderid:
                    if state.execution_report_status == EXECUTION_REPORT_STATUS_CANCELLED:
                        asec.bstable[j].orders[i].status = 'cancelled'
                        asec.bstable[j].orders[i].t_cancel = togmt(date=False)
                    else:
                        asec.bstable[j].orders[i].status = 'cancelling'

    return asec


def api_send_stop_order(client, account, asec, q, direction, stop_price, price, stop_order_type):
    price = float_to_quot(roundab(price, asec.delta))
    stop_price = float_to_quot(roundab(stop_price, asec.delta))
    postorderid = str(datetime.utcnow().timestamp())
    stop_order = client.stop_orders.post_stop_order(
        order_id=postorderid,
        figi=asec.figi,
        quantity=q,
        account_id=account['id'],
        price=price,
        stop_price=stop_price,
        direction=direction,
        expiration_type=STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
        stop_order_type=stop_order_type,
        expire_date=None,
    )


    return stop_order, asec


#  отсылает заявку и для покупки возвращает цену исполнения
def api_send_order(client, account, asec, lots, direction=OrderDirection.ORDER_DIRECTION_BUY, price=0, inorder=None):
    # делать пока не выставится: отправить заявку, получить статус заявки, убедиться что она не отменена
    # отразить изменения в таблице заявок asecorder
    if price == 0:  # если цена заявки не указана, создаём рыночную заявку (лимитную с макс/мин ценой)
        if direction == OrderDirection.ORDER_DIRECTION_BUY:
            price = float_to_quot(asec.maxprice)
        else:
            price = float_to_quot(asec.minprice)
    else:
        price = float_to_quot(roundab(price, asec.delta))
    postorderid = str(datetime.utcnow().timestamp())
    order = client.orders.post_order(
        order_id=postorderid,
        figi=asec.figi,
        quantity=lots,
        account_id=account['id'],
        price=price,
        direction=direction,
        order_type=OrderType.ORDER_TYPE_LIMIT
    )
    sleep(1)
    state = None
    state = client.orders.get_order_state(account_id=account['id'], order_id=order.order_id)
    # print(state)

    asecorder = Order()
    asecorder.status = 'sent'
    if state is not None:
        asecorder.status = 'received'
    asecorder.execution_report_status = order.execution_report_status
    asecorder.executedprice = Quotation(state.executed_order_price.units, state.executed_order_price.nano)
    asecorder.id = order.order_id
    asecorder.order_id = order.order_id
    if state.lots_executed > 0:
        asecorder.price = roundab(quot_to_float(state.executed_order_price) / state.lots_executed, asec.delta)
    else:
        asecorder.price = roundab(quot_to_float(state.initial_order_price) / state.lots_requested, asec.delta)
    asecorder.t_create = togmt(date=False)

    asecorder.q = state.lots_requested
    asecorder.q_done = state.lots_executed
    asecorder.q_rest = asecorder.q - asecorder.q_done  # ВНИМАНИЕ! Далее нужно контролировать частичное доисполнение заявки
    if direction == OrderDirection.ORDER_DIRECTION_BUY:
        asecorder.direction = 'b'
    else:
        asecorder.direction = 's'
    #  добавить сюда сделки, если они сразу произошли

    return asecorder, asec


#  загружает с сервера операции (зявки, сделки и т.д.)
def get_request(account_id, figi, cursor=""):
    return GetOperationsByCursorRequest(
        account_id=account_id,
        instrument_id=figi,
        from_=datetime(datetime.today().year, datetime.today().month, datetime.today().day),
        cursor='',
        limit=1000,
        operation_types=[OperationType.OPERATION_TYPE_SELL, OperationType.OPERATION_TYPE_BUY],
    )


def print_telegram(mes='hello'):
    get_notifier('telegram').notify(token=TELETOKEN, chat_id=TELECHAT, message=mes)




def check_executed_orders(api, asec):  # корректирует otable и заполняет ttable
    for i, BS in enumerate(asec.bstable):
        buyed = selled = False
        for j, order in enumerate(BS.orders):
            # asec.bstable[i].orders[j].trades = []
            # 1 способ получения исполненной заявки
            isinorderstates = False
            for a in api['ORDERSTATES']:  # ! самая высокая скорость обновления данных
                if order.id == a.order_id:  # если заявка есть в таблице GetOrders:
                    isinorderstates = True
                    asec.bstable[i].orders[j].status = 'active'
            if (not isinorderstates) and (asec.bstable[i].orders[j].status == 'active') and (order.t_getorders is None):
                asec.bstable[i].orders[j].status = 'executed'
                asec.bstable[i].orders[j].t_getorders = togmt(date=False)
                asec.bstable[i].orders[j].q_rest = 0
                asec.bstable[i].orders[j].q_done = asec.bstable[i].orders[j].q
                if asec.bstable[i].orders[j].direction == 'b':
                    buyed = True
                    # asec.bstable[i].buyprice = asec.bstable[i].orders[j].executedprice
                    if asec.bstable[i].buytime == None:
                        asec.bstable[i].buytime = togmt()
                if asec.bstable[i].orders[j].direction == 's':
                    selled = True
                    # asec.bstable[i].sellprice = asec.bstable[i].orders[j].executedprice
                    if asec.bstable[i].selltime == None:
                        asec.bstable[i].selltime = togmt()
            # 2 способ получения исполненной заявки
            for a in api['OPERATIONS'][asec.figi]:  # ! самая низкая скорость обновления данных
                if a.id == order.id:
                    executed_p = 0
                    executed_q = 0
                    for b in a.trades_info.trades:
                        newtrade = True
                        # print(order.trades)
                        for c in order.trades:
                            if c.id == b.num:
                                newtrade = False
                        if newtrade:
                            # print(b)
                            trade = Trade()
                            trade.p = roundab(quot_to_float(b.price), asec.delta)
                            if a.type == OPERATION_TYPE_BUY:
                                trade.d = 'b'
                            if a.type == OPERATION_TYPE_SELL:
                                trade.d = 's'
                            trade.id = b.num
                            trade.q = b.quantity
                            executed_q += trade.q
                            executed_p += trade.q * trade.p
                            trade.t = togmt(b.date, date=False)
                            trade.order = a.id
                            asec.bstable[i].orders[j].trades.append(trade)
                            if order.t_getoperations is None:
                                asec.bstable[i].orders[j].t_getoperations = togmt(date=False)
                    if executed_q:
                        asec.bstable[i].orders[j].executedprice = roundab(executed_p/executed_q, asec.delta/10)
                        asec.bstable[i].orders[j].q_done = executed_q
                        asec.bstable[i].orders[j].q_rest = asec.bstable[i].orders[j].q - asec.bstable[i].orders[j].q_done
                        if executed_q == asec.bstable[i].orders[j].q:
                            asec.bstable[i].orders[j].status = 'executed'
                        else:
                            asec.bstable[i].orders[j].status = 'executing'
                        if asec.bstable[i].orders[j].direction == 'b':
                            buyed = True
                            asec.bstable[i].buyprice = asec.bstable[i].orders[j].executedprice
                            if asec.bstable[i].buytime == None:
                                asec.bstable[i].buytime = togmt()
                        if asec.bstable[i].orders[j].direction == 's':
                            selled = True
                            asec.bstable[i].sellprice = asec.bstable[i].orders[j].executedprice
                            if asec.bstable[i].selltime == None:
                                asec.bstable[i].selltime = togmt()

        # корректировка других полей после корректировки исполненных заявок
        if buyed and selled:  # если сделка закрыта (выполнена и купля и продажа)
            if asec.bstable[i].status == False:
                asec.closedtrades += BS.lot
                asec.bstable[i].status = True
            asec.bstable[i].profit = roundab(BS.sellprice - BS.buyprice, asec.delta)
        elif buyed:
            asec.bstable[i].profit = roundab(asec.curprice - BS.buyprice, asec.delta)
        elif selled:
            asec.bstable[i].profit = roundab(BS.sellprice - asec.curprice, asec.delta)
        asec.hangorders = asec.openedtrades - asec.closedtrades
        asec.maxhangorders = max(asec.maxhangorders, asec.hangorders)
    return asec



# запрашивает свежие данные с сервера Тинькофф и пересчитывает исходя из них свежие параметры
def count_account(account, api):
    for i in api['POSITIONS'].money:
        if i.currency == 'rub':
            account['curfreemymoney'] = i.units
    account['curevaluation'] = api['PORTFOLIO'].total_amount_portfolio.units
    account['usedmoney'] = account['curevaluation'] - account['curfreemymoney']
    account['freebrokermoney'] = api['MARGIN'].starting_margin.units
    account['minfreemymoney'] = min(account['minfreemymoney'], account['curfreemymoney'])
    account['maxfreemymoney'] = max(account['maxfreemymoney'], account['curfreemymoney'])
    with open(f'countaccount.txt', 'w') as f:
        f.write(f"{togmt()} oc:{account['curevaluation']} used:{account['usedmoney']} "
                f"myfree:{account['curfreemymoney']} mymaxfree:{account['maxfreemymoney']} myminfree:{account['minfreemymoney']} "
                f"brfree:{account['freebrokermoney']}")
    return account, f" used:{str(account['usedmoney']).ljust(7, ' ')}" \
                    f" myfree:{str(account['curfreemymoney']).ljust(7, ' ')}" \
                    f" mymaxfree:{str(account['maxfreemymoney']).ljust(7, ' ')}" \
                    f" myminfree:{str(account['minfreemymoney']).ljust(7, ' ')}" \
                    f" brfree:{str(account['freebrokermoney']).ljust(7, ' ')}" \
                    f" oc:{str(account['curevaluation']).ljust(7, ' ')}"




def orderscount(api, asec): # обсчитываем текущие результаты работы
        # рассчитываем показатели потртфеля
    for i in api['POSITIONS'].securities:  # выясняемт сколько на текущий момент всего куплено штук (не лотов!)
        if i.figi == asec.figi:
            asec.bought = i.balance
    for i in api['PORTFOLIO'].positions:
        if i.figi == asec.figi:
            asec.expected_yield_fifo = int(quot_to_float(i.expected_yield_fifo))
            asec.expected_yield = int(quot_to_float(i.expected_yield))
        # считаем доходность использованного за сессию капитала
    asec.yld = asec.closedtrades / asec.maxhangorders * 0.0005
    # считаем размер использованного за сессию капитала
    asec.moneyused = asec.maxhangorders * asec.curprice
    # забираем у брокера таблицу операций по счету
    # for a, i in enumerate(asec['bstable']):
    #     for b, j in enumerate(api['OPERATIONS']):
    #         if (j.id == i.sellorderid) and (i.status is False) and (j.state != OPERATION_STATE_CANCELED):
    #             asec['bstable'][a].selltime = togmt()
    #             asec['closedtrades'] += i.lot
    #             asec['bstable'][a].status = True
    #             asec['bstable'][a].profit = roundab(i.sellprice - i.buyprice, asec['delta'])
    return asec


