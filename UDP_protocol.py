import asyncio
import struct
import os
import random
import time
from enum import IntEnum

# состояние протокола
class PacketType(IntEnum):
    START = 1 #нц передачи
    DATA = 2 #передача определенного куска файла
    ACK = 3 #подтерждение на передачу
    END = 4 #нц

#формат заголовка состоит из: (сетевой порядок байт), B (тип пакета), I (ID сессии), I (номер пакета)
HEADER_FORMAT = '!BII'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

#данные в старт: ! (сетевой порядок), I (размер файла), 64s (имя файла)
METADATA_FORMAT = '!I64s'
METADATA_SIZE = struct.calcsize(METADATA_FORMAT)

CHUNK_SIZE = 1024  
WINDOW_SIZE = 1 
TIMEOUT = 2.0 


class FileTransferProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_con_lost, loop):
        self.loop = loop
        self.on_con_lost = on_con_lost
        self.transport = None
        self.active_sessions = {} #активные сессии

    def connection_made(self, transport):
        """Вызывается при установке соединения."""
        self.transport = transport
        print(f"Сокет открыт, слушаю на {transport.get_extra_info('sockname')}")

    def datagram_received(self, data, addr):
        """Вызывается при получении датаграммы."""
        try:
            #распаковка заголовка
            packet_type, session_id, seq_num = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:]

            if packet_type == PacketType.START:
                self._handle_start(payload, session_id, seq_num, addr)
            elif packet_type == PacketType.DATA:
                self._handle_data(payload, session_id, seq_num, addr)
            elif packet_type == PacketType.ACK:
                self._handle_ack(session_id, seq_num, addr)
            elif packet_type == PacketType.END:
                self._handle_end(session_id, seq_num, addr)

        except struct.error:
            print(f"Получен поврежденный пакет от {addr}")

    def _handle_start(self, payload, session_id, seq_num, addr):
        """Обработка START пакета."""
        file_size, filename_bytes = struct.unpack(METADATA_FORMAT, payload)
        filename = filename_bytes.decode('utf-8').strip('\x00')

        print(f"\n[СЕССИЯ {session_id}] Начало приёма файла '{filename}' ({file_size} байт) от {addr}")
        
        #если дирректории для файла нет - создаем вручную
        save_dir = "received_files"
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, f"udp_{filename}")

        #сессия готова к приему файла
        self.active_sessions[session_id] = {
            'type': 'receiver',
            'filepath': filepath,
            'file': open(filepath, 'wb'),
            'total_size': file_size,
            'received_size': 0,
            'expected_seq_num': 1, 
            'addr': addr
        }
        self._send_ack(session_id, seq_num, addr)

    def _handle_data(self, payload, session_id, seq_num, addr):
        """Обработка DATA пакета."""
        session = self.active_sessions.get(session_id)
        if not session or session['type'] != 'receiver':
            return 

        if seq_num == session['expected_seq_num']:
            session['file'].write(payload)
            session['received_size'] += len(payload)
            session['expected_seq_num'] += 1
            
            #прогресс скачивания файла - как раз можно что-то с вебом сделать
            progress = (session['received_size'] / session['total_size']) * 100
            print(f"\r[СЕССИЯ {session_id}] Приём: {progress:.2f}% ({session['received_size']}/{session['total_size']})", end="")

            self._send_ack(session_id, seq_num, addr)
            
            if session['received_size'] >= session['total_size']:
                #получение полного файла
                session['file'].close()
                print(f"\n[СЕССИЯ {session_id}] Файл '{os.path.basename(session['filepath'])}' успешно получен и сохранен.")
                del self.active_sessions[session_id]
        elif seq_num < session['expected_seq_num']:
            self._send_ack(session_id, seq_num, addr)

    def _handle_ack(self, session_id, seq_num, addr):
        """Обработка ACK пакета."""
        session = self.active_sessions.get(session_id)
        if not session or session['type'] != 'sender':
            return
        
        ack_event = session['ack_events'].get(seq_num)
        if ack_event:
            ack_event.set()

    def _handle_end(self, session_id, seq_num, addr):
        print(f"[СЕССИЯ {session_id}] Получен сигнал о завершении от {addr}")
        session = self.active_sessions.get(session_id)
        if session:
            #очистка
            if 'file' in session and not session['file'].closed:
                session['file'].close()
            del self.active_sessions[session_id]

    def _send_ack(self, session_id, seq_num, addr):
        """Отправка ACK пакета."""
        header = struct.pack(HEADER_FORMAT, PacketType.ACK.value, session_id, seq_num)
        self.transport.sendto(header, addr)

    def error_received(self, exc):
        """Вызывается при ошибке."""
        print('Ошибка:', exc)

    def connection_lost(self, exc):
        """Вызывается при закрытии соединения."""
        print("Соединение закрыто.")
        self.on_con_lost.set_result(True)

    async def send_file(self, filepath, remote_addr):
        """Асинхронная функция для отправки файла."""
        try:
            file_size = os.path.getsize(filepath)
            filename = os.path.basename(filepath)
        except FileNotFoundError:
            print(f"Ошибка: Файл '{filepath}' не найден.")
            return

        session_id = random.randint(10000, 65535)
        print(f"\n[СЕССИЯ {session_id}] Начало отправки файла '{filename}' на {remote_addr}")

        #сессия отправителя
        session = {
            'type': 'sender',
            'ack_events': {},
            'addr': remote_addr
        }
        self.active_sessions[session_id] = session

        filename_bytes = filename.encode('utf-8')
        metadata_payload = struct.pack(METADATA_FORMAT, file_size, filename_bytes)
        start_packet = struct.pack(HEADER_FORMAT, PacketType.START.value, session_id, 0) + metadata_payload
        
        if not await self._send_and_wait_ack(session_id, 0, start_packet, remote_addr):
            print(f"[СЕССИЯ {session_id}] Не удалось начать передачу. Получатель не ответил.")
            del self.active_sessions[session_id]
            return
        
        print(f"[СЕССИЯ {session_id}] Получатель подтвердил начало, отправляем данные...")

        seq_num = 1
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break #файл закончился

                data_packet = struct.pack(HEADER_FORMAT, PacketType.DATA.value, session_id, seq_num) + chunk
                if not await self._send_and_wait_ack(session_id, seq_num, data_packet, remote_addr):
                    print(f"\n[СЕССИЯ {session_id}] Ошибка передачи. Получатель перестал отвечать.")
                    del self.active_sessions[session_id]
                    return
                
                progress = (f.tell() / file_size) * 100
                print(f"\r[СЕССИЯ {session_id}] Отправка: {progress:.2f}%", end="")
                
                seq_num += 1
        
        print(f"\n[СЕССИЯ {session_id}] Файл '{filename}' успешно отправлен.")
        del self.active_sessions[session_id]


    async def _send_and_wait_ack(self, session_id, seq_num, packet, addr):
        """Отправляет пакет и ждет ACK, с перепопытками."""
        session = self.active_sessions.get(session_id)
        if not session: return False

        ack_event = asyncio.Event()
        session['ack_events'][seq_num] = ack_event
        
        retries = 3
        for i in range(retries):
            self.transport.sendto(packet, addr)
            try:
                await asyncio.wait_for(ack_event.wait(), timeout=TIMEOUT)
                # ACK получен!
                del session['ack_events'][seq_num]
                return True
            except asyncio.TimeoutError:
                print(f"\n[СЕССИЯ {session_id}] Таймаут ожидания ACK для пакета {seq_num}, попытка {i+2}...")
        
        del session['ack_events'][seq_num]
        return False


# --- Точка входа и UI ---

async def main():
    """Главная асинхронная функция, управляющая приложением."""
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    my_host = input("Введите ваш IP-адрес для прослушивания (или оставьте пустым для 0.0.0.0): ") or '0.0.0.0'
    my_port = int(input("Введите ваш порт для прослушивания (например, 9999): "))

    #создание протокола и транспорта к нему
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: FileTransferProtocol(on_con_lost, loop),
        local_addr=(my_host, my_port))

    print("\nПриложение готово к работе. Введите 'help' для списка команд.")
    
    stop_event = asyncio.Event()
    loop.create_task(command_handler(protocol, stop_event))

    try:
        await stop_event.wait() 
    finally:
        transport.close()
        await asyncio.sleep(0.1)


async def command_handler(protocol, stop_event):
    """Обрабатывает команды, вводимые пользователем."""
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():
        #input() блокирует
        command_line = await loop.run_in_executor(
            None, lambda: input('> ').strip()
        )
        parts = command_line.split()
        if not parts:
            continue

        command = parts[0].lower()

        if command == 'send':
            if len(parts) != 4:
                print("Использование: send <ip_адрес_получателя> <порт> <путь_к_файлу>")
                continue
            
            remote_ip, remote_port, filepath = parts[1], int(parts[2]), parts[3]
            loop.create_task(protocol.send_file(filepath, (remote_ip, remote_port)))

        elif command == 'help':
            print("\nДоступные команды:")
            print("  send <ip> <port> <filepath> - отправить файл")
            print("  exit                        - выйти из приложения")

        elif command == 'exit':
            print("Завершение работы...")
            stop_event.set()
        
        else:
            print(f"Неизвестная команда: {command}")

if __name__ == "__main__":
    if not os.path.exists("test.txt"):
        with open("test.txt", "w") as f:
            f.write("Это тестовый файл для проверки передачи данных.\n" * 100)
    if not os.path.exists("test.bin"):
        with open("test.bin", "wb") as f:
            f.write(os.urandom(1024 * 50)) #50 KB бинарных данных

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПриложение прервано пользователем.")