import enum
import logging
import os
import sys
import threading
import time
from http import HTTPStatus
from typing import Dict, List, Union

import requests
from ccxt import binance, Exchange, BaseError
from dotenv import load_dotenv

from exceptions import (
    APIResponseError, APIStatusCodeError, ExchangeError, TelegramError
)


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


def check_tokens() -> bool:
    """Проверяет наличие всех переменных окружения."""
    return all((
        BINANCE_API_KEY,
        BINANCE_PRIVATE_KEY,
        BINANCE_MARKET_TYPE,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ))


def get_api_answer(
        exchange: Exchange, market_id: str
) -> List[Dict[str, Union[int, float, str]]]:
    """Делает запрос к API биржы и возвращает ответ."""
    try:
        logging.info('Запрашиваем позицию по инструменту %s', market_id)
        # 'https://api.binance.com/fapi/v1/positionRisk'
        response = exchange.fapiPrivate_get_positionrisk(
            params={'symbol': market_id}
        )
    except BaseError as exc:
        raise ExchangeError(f'Ошибка подключения к бирже: {exc}') from exc
    else:
        return response


def send_message(message: str) -> None:
    """Отправляет сообщение в телеграм."""
    data = {
        'url': ENDPOINT.format(token=TELEGRAM_TOKEN),
        'data': {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'markdown',
        },
    }
    try:
        logging.info('Отправляем сообщение в телеграм: %s', message)
        response = requests.post(**data)
        if response.status_code != HTTPStatus.OK:
            raise APIStatusCodeError(
                'Неверный ответ сервера: '
                f'http code = {response.status_code}; '
                f'reason = {response.reason}; '
                f'content = {response.text}'
            )
    except Exception as exc:
        raise TelegramError(
            f'Ошибка отправки сообщения в телеграм: {exc}'
        ) from exc
    else:
        logging.info('Сообщение в телеграм успешно отправлено')


def check_response(
        response: List[Dict[str, Union[int, float, str]]]
) -> Dict[str, Dict[str, Union[int, float]]]:
    """Проверяет наличие всех ключей в ответе API биржы."""
    logging.info('Проверка ответа от API начата')

    if not isinstance(response, list):
        raise TypeError(
            f'Ответ от API не является списком: response = {response}'
        )

    positions = {}

    for item in response:
        if not isinstance(item, dict):
            raise TypeError(
                'В ответе от API в списке пришли не словари, '
                f'response = {response}'
            )

        symbol = item.get('symbol')
        if symbol is None:
            raise APIResponseError(
                'В ответе API отсутствуют необходимый ключ "symbol", '
                f'response = {response}'
            )

        amount = item.get('positionAmt')
        if amount is None:
            raise APIResponseError(
                'В ответе API отсутствуют необходимый ключ "amount", '
                f'response = {response}'
            )

        entry_price = item.get('entryPrice')
        if entry_price is None:
            raise APIResponseError(
                'В ответе API отсутствуют необходимый ключ "entry_price", '
                f'response = {response}'
            )

        positions[symbol] = {'amount': amount, 'entry_price': entry_price}

    return positions


def main():
    if not check_tokens():
        error_message = (
            f'Отсутствуют обязательные переменные окружения: '
            'BINANCE_API_KEY, BINANCE_PRIVATE_KEY, BINANCE_MARKET_TYPE, '
            'TELEGRAM_TOKEN, TELEGRAM_CHAT_ID. '
            'Программа принудительно остановлена'
        )
        logging.critical(error_message)
        sys.exit(error_message)

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

        try:
            response = get_api_answer(exchange, MARKET_ID)
            position = check_response(response)[MARKET_ID]
            current_report = MESSAGE.format(
                symbol=MARKET_ID,
                amount=position['amount'],
                entry_price=position['entry_price'],
            )
            if current_report == prev_report:
                logging.debug(
                    'Нет обновлений позиции по инструменту %s', MARKET_ID
                )

        except Exception as exc:
            error_message = f'Сбой в работе программы: {exc}'
            current_report = error_message
            logging.exception(error_message)

        try:
            if current_report != prev_report:
                send_message(current_report)
                prev_report = current_report
        except TelegramError as exc:
            error_message = f'Сбой в работе программы: {exc}'
            logging.exception(error_message)

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
