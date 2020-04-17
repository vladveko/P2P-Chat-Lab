import socket
import select
import sys
import threading
import time
from _datetime import datetime

REG_MSG = 0
SEND_HISTORY = 1
RECV_HISTORY = 2
QUIT_MSG = 3

HEADER_LEN = 8

# Список соединений, в котором хранятся сокеты
connections = []

# Cписок, в котором хранится информация о активных пользователях
users_list = {}

def getlocaladdr():
    # Эта часть кода нужна для того, чтобы определить использующийся
    # сетевой интерфейс, на случай если у машины несколько сетевых интерфейсов.
    # Подключаемся к любому IP (в этом случае DNS-сервер google)
    # и определяем с какого интерфейса подключаемся.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_addr = s.getsockname()[0]
    s.close()

    return local_addr

"""
Функция, которая преобразует локальный адрес машины в широковещательный
для локальной сети.
А именно, в IP значение последнего байта меняет на 255
Пример: 1.1.1.1 --> 1.1.1.255
"""
def getbroadcastaddr():
    local_addr = getlocaladdr()
    
    i = -1
    while local_addr[i] != '.':
        i -= 1 

    return local_addr[:i+1]+'255'

"""
Отправление широковещательного UDP пакета с именем пользователя
для оповещения уже активных пользователей о подключении к чату  
"""
def sendbroadcast(my_username, broadcast_addr):
    try:
        # Кодируем имя пользователя
        username = my_username.encode('utf-8')
        # Кодируем залоговок, в котором будет длина имени пользователя;
        # :< нужно для того, чтобы длина была в начале заголовка, т.е
        # пример: '10        ' вместо '        10', потому что после длины имени
        # будет записано само имя. пример: '10        myusername'
        username_header = f"{len(username):<{HEADER_LEN}}".encode('utf-8')

        # Сокет, отправляющий UDP пакет #
        broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Включение широковещательного режима
        broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        broadcast_sock.sendto(username_header+username,(broadcast_addr, 5555))

        # Попользовались -> закрыли
        broadcast_sock.close()

        return True
    except:
        # Если возникли какие-либо ошибки
        return False

"""
Функция получения входящих сообщений.
Принимает сокет, с которого нужно прочитать сообщение.
Возвращает залоговок сообщения и само сообщение, 
Либо False, если произошла какая-либо ошибка.
"""
def receive_message(client_socket):
    try:
        # Receive our "header" containing message length, it's size is defined and constant
        message_header = client_socket.recv(HEADER_LEN)

        # If we received no data, client gracefully closed a connection, for example using socket.close() or socket.shutdown(socket.SHUT_RDWR)
        if not len(message_header):
            return False

        # Convert header to int value
        message_length = int(message_header[:int(HEADER_LEN/2)].decode('utf-8').strip())

        # Return an object of message header and message data
        return {'header': message_header, 'data': client_socket.recv(message_length)}

    except:
        # If we are here, client closed connection violently, for example by pressing ctrl+c on his script
        # or just lost his connection
        # socket.close() also invokes socket.shutdown(socket.SHUT_RDWR) what sends information about closing the socket (shutdown read/write)
        # and that's also a cause when we receive an empty message
        return False


"""
Функция, ожидающая UDP пакеты
"""
def listenbroadcast(broadcast_listener):
    try:

        ready = select.select([broadcast_listener],[],[], 3)

        if ready[0] != []:
            data, addr = broadcast_listener.recvfrom(1024)

            message_header = data[:HEADER_LEN]
            
            if not len(message_header):
                return False

            message_len = int(message_header.decode('utf-8').strip())    
            message = data[HEADER_LEN:HEADER_LEN + message_len]

            return {'addr': addr[0], 'header': message_header, 'data': message}
    except:

        return False

"""
Функция отправки истории пользователю
"""
def send_history(sock):
    print("Sending chat history...")
    f = open("text.txt", "r")

    print("Sending chat history...")
    text = f.read(2048)
    text = text.encode('utf-8')
    header = f"{len(text) :<{int(HEADER_LEN/2)}}{RECV_HISTORY :<{int(HEADER_LEN/2)}}".encode('utf-8')
    sock.send(header+text)
        
    print("Done sending.\n")

    f.close()

"""
Функция получения истории
"""
def receive_history(data):

    print("Receiving chat history...")
    f = open("text.txt", "a")

    f.write(data.decode('utf-8'))

    f.close()  
    print("Done receiving.")  

def print_history():
    print_lock = threading.Lock()
    print_lock.acquire()

    f = open("text.txt", "r")
    text = f.read(1024)
    
    while text:
        print(text)
        text = f.read(1024)

    print_lock.release()
    f.close()

"""
Функция для обнаружения новых подключений, создания соединения
с ними и получения сообщений с уже существуещих соединений.
"""
def all_receiving(my_username, server_sock):
    global connections
    global users_list

    # Сокет, принимающий UDP пакеты #
    broadcast_listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Включение широковещательного режима
    broadcast_listener.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    broadcast_listener.bind(('', 5555))

    connections.append(server_sock)

    # Кодируем имя пользователя
    username = my_username.encode('utf-8')

    while True:
        new_connection = listenbroadcast(broadcast_listener=broadcast_listener)
        # Если есть новое подключение, то устанавливаем соединение
        # с новым пользователем, отправляем ему свое имя пользователя
        if new_connection:
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            new_sock.connect((new_connection['addr'], 8000))

            # Кодируем залоговок, в котором будет длина имени пользователя;
            # :< нужно для того, чтобы длина была в начале заголовка, т.е
            # пример: '10        ' вместо '        10', потому что после длины имени
            # будет записано само имя. пример: '10        myusername'
            user_header = f"{len(username) :<{int(HEADER_LEN/2)}}{REG_MSG :<{int(HEADER_LEN/2)}}".encode('utf-8')
            new_sock.send(user_header+username)    

            # Добавляем в список соединений новое соединение
            connections.append(new_sock)
            # И в список пользователей по индексу нового сокета
            # заносим информации о клиенте (адрес, заголовок, имя пользователя)
            users_list[new_sock] = new_connection

            print(f"\n{datetime.now()}:>> {new_connection['data'].decode('utf-8')}[{new_connection['addr']}] connected!")
            history = open("text.txt", "a")
            history.write(f"\n{datetime.now()}:>> {new_connection['data'].decode('utf-8')}[{new_connection['addr']}] connected!\n")
            history.close()

        # Проверяем есть ли сокеты, с которых можно считать данные и
        # есть ли сокеты, на которых возникли ошибки
        read_sock, _, exception_sock = select.select(connections, [], connections, 2)
        # Если таковые имеются, то
        if read_sock != [] or exception_sock != []:
            # то соотвественно считываем данные
            for notified_sock in read_sock:
                if notified_sock == server_sock:
                    # У нас новое подключение -> обрабатываем его
                    # Функция accept возвращает нам два значения:
                    # 1. сокет, через который будет проходить дальнейшая
                    #    коммуникация с клиентом;
                    # 2. адрес, с которого подключаются.
                    new_sock, new_addr = server_sock.accept()
                    
                    # Получаем имя пользователя
                    new_connection = receive_message(client_socket=new_sock)

                    # Если сообщение не пустое, значит пользователь еще активен.
                    # Иначе соединение утеряно.
                    if new_connection:
                        # Добавляем новый сокет в список подключений
                        connections.append(new_sock)
                        # И пополняем список пользователей
                        new_connection['addr'] = new_addr[0]
                        users_list[new_sock] = new_connection

                        print(f"\n{datetime.now()}:>> {new_connection['data'].decode('utf-8')}[{new_connection['addr']}] connected!")
                        history = open("text.txt", "a")
                        history.write(f"\n{datetime.now()}:>> {new_connection['data'].decode('utf-8')}[{new_connection['addr']}] connected!\n")
                        history.close()

                else:
                    # Читаем входящие сообщения
                    message = receive_message(notified_sock)

                    # Если сообщение не пустое, значит пользователь еще активен.
                    # Иначе соединение утеряно. 
                    if message:
                        # Идентифицируем автора сообщения
                        user = users_list[notified_sock]
                        # Извлекаем код сообщения из залоговка
                        message_code = int(message['header'][int(HEADER_LEN/2):].decode('utf-8'))
                        # 0 - обычное сообщение
                        # 1 - отправка истории
                        # 2 - сообщение о отключении пользователя

                        if message_code == REG_MSG:
                            # Выводим сообщение
                            print(f"{datetime.now()}:>> {user['data'].decode('utf-8')}[{user['addr']}] > {message['data'].decode('utf-8')}")
                            # Записываем сообщение в историю
                            history = open("text.txt", "a")
                            history.write(f"{datetime.now()}:>> {user['data'].decode('utf-8')}[{user['addr']}] > {message['data'].decode('utf-8')}\n")
                            history.close()

                        elif message_code == SEND_HISTORY:
                            send_history(sock=notified_sock)
                        
                        elif message_code == RECV_HISTORY:
                            receive_history(message['data'])
                            print_history()

                        elif message_code == QUIT_MSG:
                            remove_lock = threading.Lock()
                            remove_lock.acquire()

                            print(f"\n{datetime.now()}:>> {user['data'].decode('utf-8')}[{user['addr']}] disconnected!")
                            history = open("text.txt", "a")
                            history.write(f"\n{datetime.now()}:>> {user['data'].decode('utf-8')}[{user['addr']}] disconnected!\n")
                            history.close()
                            connections.remove(notified_sock)
                            del users_list[notified_sock]

                            remove_lock.release()

            for notified_sock in exception_sock:
                connections.remove(notified_sock)

                del users_list[notified_sock]


def main_func(username):
    global connections
    global users_list

    local_addr = getlocaladdr()

    # Создаем серверный сокет, к которому будут подключатся клиенты
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Привязываем сокет к порту
    server_sock.bind((local_addr, 8000))
    # И слушаем подключения
    server_sock.listen()

    receiving_thread = threading.Thread(target=all_receiving, args=(username, server_sock, ), daemon=True)
    receiving_thread.start()

    #all_receiving(username, server_sock)

    message = ""

    print("You have connected to the chat!")
    time.sleep(10)
    if users_list != {}:
        # Формируем залоговок с кодом - 1, отправить историю
        message_header = f"{0 :<{int(HEADER_LEN/2)}}{SEND_HISTORY :<{int(HEADER_LEN/2)}}".encode('utf-8')
        for user_sock in users_list:
            user_sock.send(message_header)
            break

    # Цикл для отправки сообщений. Для выхода нужно прописать quit
    while message != "quit()":

        # Если список пользователей пуст, то в чате никого нет
        if users_list == {}:
            print('  >> No active users <<')

        # Вводим сообщение 
        message = input(f"{username}[{local_addr}] > ").strip()

        if message != "quit()":
            # Записываем сообщение в историю
            history = open("text.txt", "a")
            history.write(f"{datetime.now()}:>> {username}[{local_addr}] > {message}\n")
            history.close()
            
            # Проверяем, чтобы сообщение не было пустым  
            if message:
                # Далее кодируем заголовок сообщения, в котором хранится длина сообщения,
                # и само сообщение.
                message_header = f"{len(message) :<{int(HEADER_LEN/2)}}{REG_MSG :<{int(HEADER_LEN/2)}}".encode('utf-8')
                message = message.encode('utf-8')
                # И отправляем всем активным пользователям сообщение
                for user_sock in users_list:
                    user_sock.send(message_header + message)
    
    if users_list != {}:
        # Далее кодируем заголовок сообщения, в котором хранится длина сообщения,
        # и само сообщение.
        message_header = f"{len(username) :<{int(HEADER_LEN/2)}}{QUIT_MSG :<{int(HEADER_LEN/2)}}".encode('utf-8')
        message = message.encode('utf-8')
        # И отправляем всем активным пользователям сообщение
        for user_sock in users_list:
            user_sock.send(message_header + message)

    history = open("text.txt", "w")
    history.close()

#---------------------------------------------------#
if len(sys.argv) <= 1:
    print("Current usage: script <username>")
    sys.exit(1)

username = sys.argv[1]

broadcast_addr = getbroadcastaddr()

# Отправляем UDP пакет с именем пользователя.
# Если возникли ошибки, выходим.
if not sendbroadcast(username, broadcast_addr):
    print("Unable to connect. Check your network connection.")
    sys.exit(1)

main_func(username)

print("You left the chat.") 