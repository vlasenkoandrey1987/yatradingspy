import enum
import logging
import os
import sys
import threading
import time

import requests
from ccxt import binance
from dotenv import load_dotenv


class State(enum.Enum):
    INITIAL = 0
    RUNNING = 1
    STOPPED = 2


state = State.INITIAL
state_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv()

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_PRIVATE_KEY = os.getenv('BINANCE_PRIVATE_KEY')
BINANCE_MARKET_TYPE = os.getenv('BINANCE_MARKET_TYPE')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

MARKET_ID = 'BTCUSDT'

RETRY_TIME = 10
ENDPOINT = 'https://api.telegram.org/bot{token}/sendMessage'

MESSAGE = 'symbol: {symbol}, amount: {amount}, entry price: {entry_price}'


def main():
    exchange = binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_PRIVATE_KEY,
        'timeout': 10000,  # number in milliseconds
        'enableRateLimit': True,
        'options': {
            # 'spot', 'future', 'margin', 'delivery'
            'defaultType': BINANCE_MARKET_TYPE,
        }
    })

    global state
    with state_lock:
        state = State.RUNNING

    current_report = None
    prev_report = current_report

    while True:
        with state_lock:
            if state == State.STOPPED:
                break

        logging.info('Запрашиваем позицию по инструменту %s', MARKET_ID)
        # 'https://api.binance.com/fapi/v1/positionRisk'
        response = exchange.fapiPrivate_get_positionrisk(
            params={'symbol': MARKET_ID}
        )
        position = response[0]
        current_report = MESSAGE.format(
            symbol=MARKET_ID,
            amount=position['positionAmt'],
            entry_price=position['entryPrice'],
        )
        if current_report == prev_report:
            logging.debug(
                'Нет обновлений позиции по инструменту %s', MARKET_ID
            )

        if current_report != prev_report:
            logging.info(
                'Отправляем сообщение в телеграм: %s', current_report
            )
            requests.post(
                url=ENDPOINT.format(token=TELEGRAM_TOKEN),
                data={
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': current_report,
                    'parse_mode': 'markdown',
                },
            )
            logging.info('Сообщение в телеграм успешно отправлено')
            prev_report = current_report

        time.sleep(RETRY_TIME)


def repl():  # read eval print loop
    global state
    while True:
        command = input('Please, press "s" to stop')
        if command == 's':
            with state_lock:
                state = State.STOPPED
            break


if __name__ == '__main__':
    log_format = (
        '%(asctime)s [%(levelname)s] - '
        '(%(filename)s).%(funcName)s:%(lineno)d - %(message)s'
    )
    log_file = os.path.join(BASE_DIR, 'output.log')
    log_stream = sys.stdout
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(log_stream)
        ]
    )

    repl_thread = threading.Thread(target=repl)
    repl_thread.start()
    main()
