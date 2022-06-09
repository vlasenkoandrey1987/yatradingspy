import enum
import logging
import os
import sys
import threading
import time


class State(enum.Enum):
    INITIAL = 0
    RUNNING = 1
    STOPPED = 2


state = State.INITIAL
state_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    while True:
        logging.info('event')
        state_lock.acquire()
        if state == State.STOPPED:
            state_lock.release()
            break
        state_lock.release()

        time.sleep(10)


def repl():  # read eval print loop
    global state
    while True:
        command = input('Please, press "s" to stop')
        if command == 's':
            state_lock.acquire()
            state = State.STOPPED
            state_lock.release()
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
