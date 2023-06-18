#  ПЛАН БЛИЖАЙШИХ КОРРЕКТИРОВОК
#  возможно имеет смысл перейти на формат чисел decimal
#  сделать таблицу сделок ttable
#  изменить алгоритм на работу с лимитными заявками, чтобы захватывать пробои
''' Считаем доходность разными способами:
0. Считаем цену всего портфеля в рублях при открытии сессии и при закрытии, сравниваем.
1. Получаем от брокера доходность по инструменту при открытии сессии и при закрытии, сравниваем.
2. Считаем результат всех сделок по инструменту за сессию: сделано - ttable_profit
3. Считаем результат всех сделок по инструменту за сессию, добавляем разницу между стоимостью позиции инструмента
между открытием и закрытием сессии.
5. Контролировать текущую и предыдущую цены через свечи (там можно видеть локальные экстремумы)
6. Decimal вместо Float
7. Написать проверку, сколько прошло времени с последнего запуска и не было ли за это время конца сессии.
8. Заменить figi на instrument_uid или что-то подобное
'''

from pprint import pprint
from decimal import Decimal
from tinkoff.invest import (
    CandleInstrument,
    Client,
    InfoInstrument,
    SubscriptionInterval,
)
from tinkoff.invest.grpc.marketdata_pb2 import CANDLE_INTERVAL_1_MIN, CANDLE_INTERVAL_5_MIN
from tinkoff.invest.market_data_stream.market_data_stream_manager import MarketDataStreamManager
from tinkoff.invest.utils import now
import datetime, math, pytz
from datetime import timedelta
from datetime import datetime
from time import sleep
from array import *
from tinkoff.invest import Client, InstrumentIdType, GenerateBrokerReportRequest, PortfolioResponse, RequestError, \
    OrderDirection, OrderType, Quotation, OperationState, OperationType, OrderExecutionReportStatus, CandleInterval
from tinkoff.invest.constants import INVEST_GRPC_API
from tinkoff.invest import GetOperationsByCursorRequest, PortfolioPosition
import os
import sys
import pickle

from tinkoff.invest.grpc.instruments_pb2 import INSTRUMENT_ID_TYPE_FIGI

from math import *
from funcs import *

from tinkoff.invest.grpc.operations_pb2 import OPERATION_STATE_CANCELED, OPERATION_TYPE_BUY, OPERATION_TYPE_SELL, \
    OPERATION_STATE_EXECUTED
from tinkoff.invest.grpc.orders_pb2 import EXECUTION_REPORT_STATUS_CANCELLED, EXECUTION_REPORT_STATUS_NEW, \
    EXECUTION_REPORT_STATUS_PARTIALLYFILL, EXECUTION_REPORT_STATUS_FILL, EXECUTION_REPORT_STATUS_REJECTED
import telebot
from notifiers import get_notifier
import time
import os.path


def merge_buysells(client, account, asec):
    # если таблица сделок не пуста и время сессии подошло к концу
    if len(asec.bstable) > 0 and (not cantrade(client, asec)) and asec.session == 'opened':
        BS = Buysell()  # создаём новую строку в таблице и инициализируем поля
        BS.lot = asec.lot
        BS.sellprice = 0
        BS.buyprice = 0
        BS.buytime = togmt()
        BS.original = False
        num = 0
        for i, a in enumerate(asec.bstable):  # пробегаем по таблице сделок
            if (not a.status):  # если сделка не закрыта, добавляем её в новую сделку, а старую удаляем
                if a.sellorderid != None:
                    asec = api_cancel_order(client, account, asec, a.sellorderid)
                    asec.bstable[i].replaced = True
                num += a.lot
                BS.sellprice = BS.sellprice + a.lot * a.sellprice
                BS.buyprice = BS.buyprice + a.lot * a.buyprice
        if num > 0:  # если старые сделки были удалены в вышерасположенном цикле, то создаем новую сделку взамен
            BS.sellprice = roundab(BS.sellprice / num + 2 * asec.delta, asec.delta)
            BS.buyprice = roundab(BS.buyprice / num, asec.delta)
            if BS.lot > 1:
                BS.lot = num // 2
            BS.status = False
            #  2 строки кода ниже нужны если объединение сделок происходит не в конце сессии и нужно их послать на сервер
            # sellorder, asec = api_send_order(client, account, asec, lots=BS.lot,
            #                                  direction=OrderDirection.ORDER_DIRECTION_SELL, price=BS.sellprice)
            # BS.orders.append(sellorder)
            asec.bstable.append(BS)
    return asec


#  снимает все заявки у брокера и параллельно в BSTABLE
#  а потом создает одну усредненную заявку с увеличеннной на 1 пункт ценой и сохраняет её в BSTABLE
def off_orders(client, account, asec):
    print('off_orders:')
    # if len(asec.bstable) > 0:  # если таблица сделок не пуста
    #     BS = Buysell()  # создаём новую строку в таблице и инициализируем поля
    #     BS.lot = asec.lot
    #     BS.sellprice = 0
    #     BS.buyprice = 0
    #     BS.buytime = togmt()
    #     BS.original = False
    #     num = 0
    #     for i in asec.bstable:  # пробегаем по таблице сделок
    #         if (not i.status):  # если сделка не закрыта, добавляем её в новую сделку, а старую удаляем
    #             if i.sellorderid != None:
    #                 asec = api_cancel_order(client, account, asec, i.sellorderid)
    #             num += i.lot
    #             BS.sellprice = BS.sellprice + i.lot * i.sellprice
    #             BS.buyprice = BS.buyprice + i.lot * i.buyprice
    #     if num > 0:  # если старые сделки были удалены в вышерасположенном цикле, то создаем новую сделку взамен
    #         BS.sellprice = roundab(BS.sellprice / num + 2 * asec.delta, asec.delta)
    #         BS.buyprice = roundab(BS.buyprice / num, asec.delta)
    #         if BS.lot > 1:
    #             BS.lot = num // 2
    #         BS.status = False
    #         asec.bstable = []
    #         asec.bstable.append(BS)
    # else:
    #     asec.bstable = []
    return asec


def on_orders(client, account, asec):  # загружает заявки из таблицы BSTABLE на сервер брокеру
    """функция восстанавливает отмененные из-за закрытия сессии заявки из массива байселлов.
     Она ищет не закрытые и не замененные байселлы и активизирует их заявки."""
    print('on_orders BSTABLE:')
    for i, bs in enumerate(asec.bstable):  # пробегаем по таблице
        #  pprint(vars(i))
        if (not bs.status) and (not bs.replaced):
            if bs.sellprice > asec.maxprice:  # если цена для выставления в корзину слишком высока
                asec.bstable[i].overpriced = True  # пометим это флагом
            else:
                asec.bstable[i].overpriced = False  # иначе снимем флаг и выставим заявку
                sellorder, asec = api_send_order(client, account, asec, lots=bs.lot, direction=OrderDirection.ORDER_DIRECTION_SELL,
                                        price=bs.sellprice)
                asec.bstable[i].sellorderid = sellorder.order_id
                asec.bstable[i].buytime = togmt()  # и сменим время покупки на текущее
                asec.bstable[i].orders.append(sellorder)
    return asec


#  открывает торговую сессию (нужно научиться считывать время открытия-закрытия с сервера)
def open_session(client, account, asec):
    asec.changeprice = 0
    asec.openedtrades = 0
    asec.closedtrades = 0
    asec.hangorders = 0
    asec.maxhangorders = 1
    asec.session = 'opened'
    S = Session()
    S.open_datetime = togmt()
    S.api_yield_open = asec.expected_yield
    S.open_price = asec.curprice
    S.lot = asec.lot
    asec.stable.append(S)
    print('\n', asec.stable[-1].open_datetime, 'OPEN SESSION, BSTABLE:')
    asec = on_orders(client, account, asec)
    return asec


def close_session(client, account, api, asec):  # закрывает торговую сессию
    asec.session = 'closed'
    asec.stable[-1].api_yield_close = asec.expected_yield
    asec.stable[-1].close_price = asec.curprice
    asec.stable[-1].bougth_all = asec.bought
    print('\n', asec.stable[-1].open_datetime, 'CLOSE SESSION')
    with open(f'{asec.name}_sessions.txt', 'a') as f:  # записываем характеристики текущей сессии в файл
        account, pstr = count_account(account, api)
        f.write(f"ses {togmt()} {accounttostr(account)} {asectostr(asec)} \n")
    asec = merge_buysells(client, account, asec)
    asec = off_orders(client, account, asec)  # снимаем заявки
    # сохраняем все сделки за сессию в файл
    with open(f'{asec.name}_trades.txt', 'a') as f:
        for BS in asec.bstable:
            for j in BS.orders:
                for i in j.trades:
                    if i.d == 's':
                        f.write(f"{i.order} s    {str(i.p).ljust(6, ' ')} {i.id} "
                                f"{str(i.q).ljust(3, ' ')} {str(i.t).ljust(10, ' ')}\n")
                    else:
                        f.write(f"{i.order} b    {str(i.p).ljust(6, ' ')} {i.id} "
                                f"{str(i.q).ljust(3, ' ')} {str(i.t).ljust(10, ' ')}\n")
    return account, asec


def copy_broker_orders(api, asec):  # ведет учет заявок на сервере и дублирует информацию в файл
    # получаем информацию о всех заявках за текущую сессию и формируем таблицу
    # сохраняем таблицу в файл предварительно его очистив
    # можно в конце устроить проверку на сравнение информации с BSTABLE
    # api['ORDERSTATES']
    # with open(f'{asec.name}_operations.txt', 'w') as f:
    #     f.write(str(api['OPERATIONS'][asec.figi]))
    with open(f'{asec.name}_orderstates.txt', 'w') as f:
        f.write(str(api['ORDERSTATES']))
    brokerorders=[]
    bquantity, squantity, result = 0, 0, 0
    for j in api['OPERATIONS'][asec.figi]:
        border = Buysell()
        if j.type == OPERATION_TYPE_BUY:
            border.buyprice = roundab(quot_to_float(j.price), asec.delta)
            border.buytime = j.date
            border.buyorderid = j.id
            bquantity += j.quantity_done
            result -= j.quantity_done * roundab(quot_to_float(j.price), asec.delta)
        if j.type == OPERATION_TYPE_SELL:
            border.sellprice = roundab(quot_to_float(j.price), asec.delta)
            border.selltime = j.date
            border.sellorderid = j.id
            squantity += j.quantity_done
            result += j.quantity_done * roundab(quot_to_float(j.price), asec.delta)
        border.quantity = j.quantity
        border.quantity_done = j.quantity_done
        border.quantity_rest = j.quantity_rest
        border.cancel_date_time = j.cancel_date_time
        border.status = j.state
        brokerorders.append(border)
    result = roundab(result + (bquantity - squantity) * asec.curprice, asec.delta)
    with open(f'{asec.name}_orders.txt', 'w') as f:
        f.write(f"qbuy={bquantity}, qsell={squantity}, result={result}\n")
        f.write(f"time     oper price  sellorderid q   qd  qr  canceltime status\n")
        for i in brokerorders:
            if i.buyprice == None:
                f.write(f"{togmt(i.selltime, False)} s    {str(i.sellprice).ljust(6, ' ')} {i.sellorderid} "
                        f"{str(i.quantity).ljust(3, ' ')} {str(i.quantity_done).ljust(3, ' ')} "
                        f"{str(i.quantity_rest).ljust(3, ' ')} {togmt(i.cancel_date_time, False)}   {str(i.status)}\n")
            else:
                f.write(f"{togmt(i.buytime, False)} b    {str(i.buyprice).ljust(6, ' ')} {i.buyorderid} "
                        f"{str(i.quantity).ljust(3, ' ')} {str(i.quantity_done).ljust(3, ' ')} "
                        f"{str(i.quantity_rest).ljust(3, ' ')} {togmt(i.cancel_date_time, False)}   {str(i.status)}\n")
    return asec


def api_set_server_data(client, account, api, atable, _state=[]):
    '''Функция пробегает локальные таблицы заявок, и последнюю серверную таблицу заявок,
     проверяет что еще не было получено сервером, и отправляет на сервер необходимые заявки.
     Если у локальной заявки есть серверный номер, значит она обработана.
     Также отменяет заявки, если они висят, но их нужно было отменить.
     Также отправляет отложенные заявки, если цена достигла нужного уровня.
     ФУНКЦИЯ НУЖДАЕТСЯ В ПРОРАБОТКЕ!!!'''
    for i, a in enumerate(atable):
        for j, bs in a.bstable:
            for k, o in bs.orders:
                # если это не стоп-заявка, и она не отправлена ранее (нет id), и цена в допустимом диапазоне
                if o.urgency == 'immediate' and o.id is None and a.minprice < o.price < a.maxprice:
                    #  отправляем на сервер и получаем обратно вместе с id
                    atable[i].bstable[j].orders[k] = api_send_order(o)
                # если это стоп-заявка и цена достигла нужного значения, отправляем
                if o.urgency == 'deferred':
                    if o.direction == 'buy' and o.stop_price <= a.curprice:
                        atable[i].bstable[j].orders[k] = api_send_order(o)
                if o.status == 'cancelled' and not o.dispatched:
                    atable[i].bstable[j].orders[k] = api_cancel_order(o)

    return


def api_get_server_data(client, account, api, atable, _state=[]):
    if not _state:  # используем _state как счётчик запусков функции
        _state.append(0)

    _state[0] += 1
    if _state[0] % 10 == 1:  # на asec['run'] пока не поменять, т.к. он плохо считывается
        # api['OPERATIONS'] = {}
        # api['INSTRUMENTS'] = {}
        for i, a in enumerate(atable):
            if a.active:
                atable[i].delta = quot_to_float(roundsec(client, a.figi))
                api['OPERATIONS'][a.figi] = client.operations.get_operations_by_cursor(
                    get_request(account['id'], a.figi)).items
                api['INSTRUMENTS'][a.figi] = client.instruments.get_instrument_by(id_type=INSTRUMENT_ID_TYPE_FIGI,
                                                                         id=a.figi).instrument
                if cantrade(client, a) and a.name != 'goodwin':
                    market_data_stream = client.create_market_data_stream()
                    market_data_stream.candles.subscribe(
                        [CandleInstrument(figi=a.figi, interval=SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_MINUTE)])
                    for marketdata in market_data_stream:
                        if marketdata.candle is not None:
                            api['CANDLES'][a.figi] = marketdata.candle
                            atable[i].highcandleprice = roundab(quot_to_float(marketdata.candle.high), atable[i].delta)
                            atable[i].lowcandleprice = roundab(quot_to_float(marketdata.candle.low), atable[i].delta)
                            break
        # api['REPORT'] = client.operations.get_broker_report(
        #     generate_broker_report_request=account_id=account['id'],
        # )
        api['POSITIONS'] = client.operations.get_positions(account_id=account['id'])
        api['PORTFOLIO'] = client.operations.get_portfolio(account_id=account['id'])
        api['MARGIN'] = client.users.get_margin_attributes(account_id=account['id'])
        api['SHEDULES'] = client.instruments.trading_schedules(
            from_=datetime(datetime.today().year, datetime.today().month, datetime.today().day,
                           datetime.today().hour, datetime.today().minute, datetime.today().second),
            to=datetime(datetime.today().year, datetime.today().month, datetime.today().day,
                           datetime.today().hour, datetime.today().minute, datetime.today().second)
        ).exchanges

        # for i in api['SHEDULES']:
        #     if i.exchange == api['INSTRUMENT'].exchange.lower():
        #         rasp = i.days
        #         print(rasp)
    # api['ORDERSTATES'] - критичная к скорости обновления таблица - её желательно обновлять как можно чаще!
    api['ORDERSTATES'] = client.orders.get_orders(account_id=account['id']).orders
    api['BOOKS'] = {}
    for i, a in enumerate(atable):
        if a.active and (client.market_data.get_trading_status(instrument_id=a.figi).trading_status == 5):
            api['BOOKS'][a.figi] = client.market_data.get_order_book(figi=a.figi, depth=1)  # получаем края стакана в global BOOK
            # asec['curprice'] = quot_to_float(api['BOOK'].asks[0].price)  # исправить бы на цену последней сделки
            atable[i].curprice = roundab(quot_to_float(client.market_data.get_last_prices(figi=[a.figi]).last_prices[0].price), a.delta)
            atable[i].minprice = roundab(quot_to_float(api['BOOKS'][a.figi].limit_down) + a.delta, a.delta)
            atable[i].maxprice = roundab(quot_to_float(api['BOOKS'][a.figi].limit_up) - a.delta, a.delta)
    return api


def algo_dailybuy(client, account, asec, command):  # стратегия dailybuy: запускаем очередную сделку
    # присваиваем цену sellprice выше текущей на (2 пункта+комиссии)

    sellprice = roundab(asec.curprice + 2 * asec.delta, asec.delta)
    # создаём реальные заявки и учетные заявки в таблице BSTABLE
    if (abs(asec.preprice - asec.curprice) >= 2*asec.delta) or (asec.openedtrades == 0):
    # if (abs(asec['preprice'] - asec['curprice']) >= 2 * asec['delta']) or (asec['openedtrades'] == 0):  # если цена в стакане изменилась
        # print('curprice, preprice:', asec['curprice'], asec['preprice'])
        # if (abs(asec['preprice'] - asec['curprice']) >= 2 * asec['delta']):
        asec.preprice = asec.curprice
         #   print('preprice:', asec['preprice'])
        #  фиксируем изменение цены
        asec.changeprice = 1
        #  создаем строку учёта сделки в таблице BSTABLE
        BS = Buysell()  # создаём конструктором объект класса Buysell и заполняем поля объекта
        BS.lot = asec.lot
        #  покупаем по рынку 1 лот
        buyorder, asec = api_send_order(client, account, asec, lots=asec.lot, direction=OrderDirection.ORDER_DIRECTION_BUY)
        buyexecutedprice = 0  # инициализируем цену покупки (присваиваем нач.значение)
        # если заявка почему-то отменяется выставляем её пока не исполнится
        while buyorder.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_CANCELLED:
            print('\n', togmt(date=False), 'CANCELLED Order!', buyexecutedprice)
            # уменьшаем цену на случай изменения лимита в процессе сделки
            asec.maxprice = roundab(asec.maxprice - asec.delta, asec.delta)
            #  посылаем новую заявку
            buyorder, asec = api_send_order(client, account, asec, lots=asec.lot, direction=OrderDirection.ORDER_DIRECTION_BUY)
        #  фиксируем цену исполнения покупки
        buyexecutedprice = quot_to_float(buyorder.executedprice)/asec.lot
        BS.orders.append(buyorder)
        if buyexecutedprice == 0:  # если цена исполнения не считалась, сигнализируем сообщением
            print('\n', togmt(date=False), 'NOT PROCESSED Order!', buyexecutedprice)
        else:  # иначе увеличиваем счётчик открытых сделок
            asec.openedtrades += asec.lot
        #  выставляем лимитную заявку на продажу на 2 пункта дороже
        sellorder, asec = api_send_order(client, account, asec, lots=asec.lot, direction=OrderDirection.ORDER_DIRECTION_SELL, price=sellprice)
        BS.orders.append(sellorder)
        BS.sellprice = sellprice
        BS.buyorderid = buyorder.order_id
        BS.sellorderid = sellorder.order_id
        BS.buyprice = asec.curprice  # buyexecutedprice
        BS.buytime = togmt()
        BS.original = True  # флаг оригинальной заявки (неперевыставленной с удорожанием)
        BS.direction = 'long'
        asec.bstable.append(BS)  # добавляем строку в учётную таблицу сделок
        # print('\n', togmt(date=False), 'New opened order: ', BS.buyprice, BS.sellprice)
    else:  # если цена в стакане не изменилась, обнуляем индикатор изменения цены
        asec.changeprice = 0
    # asec = shake_orders(client, account, asec)
    asec = merge_buysells(client, account, asec)
    return asec


def algo_stopper(client, account, asec, command):
    return asec


def execute_command(atable, command):
    ''' Command format: [command start aname dailybuy ticker TMOS price 120]'''
    if command is not None:
        for i, asec in enumerate(atable):
            if (command.figi == asec.figi) and (command.aname == asec.name):
                if command.name == 'stop':
                    atable[i].active = False
                elif command.name == 'start':
                    atable[i].active = True
    return atable


def run_trading_algo(client, account, asec, command):
    if asec.name == 'dailybuy':
        asec = algo_dailybuy(client, account, asec, command)
    elif asec.name == 'stopper':
        asec = algo_stopper(client, account, asec, command)
    elif asec.name == 'goodwin':
        asec = algo_goodwin(client, account, asec, command)
    return asec


if __name__ == "__main__":
    while True:  # запускаем программу в вечном цикле
        try:  # конструкция для защиты прекращения программы из-за ошибок
            # if abs(os.path.getmtime('autorun.txt') - time.time()) > 60:
            #     print_telegram('Авторан на ноуте остановился')
            #     sleep(30)


            with Client(TOKEN) as CLIENT:  # конструкция из апи Тинькофф для Питона, не совсем понятно что означает
                ATABLE, COMMAND = readbstable(CLIENT, ACCOUNT, ATABLE)  # считываем последнее состояние алгоритма из файла ДОЛЖНА БЫТЬ В НАЧАЛЕ
                ATABLE = execute_command(ATABLE, COMMAND)
                API = api_get_server_data(CLIENT, ACCOUNT, API, ATABLE)  # получаем данные с сервера
                for i, A in enumerate(ATABLE):
                    #if A.active:
                        if cantrade(CLIENT, A):  # если торговля допустима, торгуем
                            print('\r', togmt(date=False), asectostr(A), end='')  # выводим состояние алгоритма
                            # print(' ')
                            if A.session == 'closed':  # если СЕССИЯ закрыта, открываем
                                ATABLE[i] = open_session(CLIENT, ACCOUNT, A)
                            ATABLE[i] = run_trading_algo(CLIENT, ACCOUNT, A, COMMAND)  # запускаем торговый алгоритм
                        else:  # если торговля недопустима, выводим состояние портфеля
                            #  print('\r', togmt(date=False), accounttostr(ACCOUNT), end='')
                            if A.session == 'opened':  # если СЕССИЯ открыта, закрываем
                                ACCOUNT, ATABLE[i] = close_session(CLIENT, ACCOUNT, API, A)
            for i, A in enumerate(ATABLE):
                if A.active:
                    ATABLE[i] = orderscount(API, A)  # считаем показатели алгоритма
                    ATABLE[i] = check_executed_orders(API, A)
                    ATABLE[i] = copy_broker_orders(API, A)
                    ATABLE[i] = save_bstable(A)
                    ATABLE[i] = save_otable(A)
                    ATABLE[i] = save_ttable(A)
            all_closed = True
            for A in ATABLE:  # если все сессии закрыты, выводим состояние портфеля
                if A.active and A.session == 'opened':
                    all_closed = False
            if all_closed:
                print('\r', togmt(date=False), accounttostr(ACCOUNT), end='')
            ACCOUNT, pstr = count_account(ACCOUNT, API)
            writebstable(ATABLE)  # сохраняем состояние алгоритма в файл ДОЛЖНА БЫТЬ В КОНЦЕ
        except RequestError as e:
            print(str(e))
        sleep(5)










