import sys


def offline_guard(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.bind', 'socket.getaddrinfo', 'urllib.Request'):
        raise PermissionError('Сетевые операции приложения отключены.')


def install():
    sys.addaudithook(offline_guard)
