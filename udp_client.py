# udp_client.py (исправленная версия)
import socket
import struct
import os
import sys
import time

class UDPClientSimple:
    def __init__(self, server_host='127.0.0.1', server_port=9999):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = None
        self.timeout = 10.0  # Увеличиваем таймаут
        
    def create_socket(self):
        """Создание нового сокета"""
        if self.sock:
            self.sock.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        
    def send_file(self, file_path, max_retries=3):
        """Отправка файла с повторными попытками"""
        if not os.path.exists(file_path):
            print(f"Ошибка: файл '{file_path}' не найден")
            return False
        
        for attempt in range(max_retries):
            print(f"\nПопытка {attempt + 1}/{max_retries}")
            if self._send_single_attempt(file_path):
                return True
            if attempt < max_retries - 1:
                print("Повторная попытка через 3 секунды...")
                time.sleep(3)
        
        print("\n✗ Не удалось отправить файл после всех попыток")
        return False
    
    def _send_single_attempt(self, file_path):
        """Одна попытка отправки файла"""
        try:
            # Создаем сокет
            self.create_socket()
            
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            
            print(f"Отправка файла: {file_name}")
            print(f"Размер: {file_size:,} байт")
            print(f"Сервер: {self.server_host}:{self.server_port}")
            print("-" * 40)
            
            # Шаг 1: Отправляем метаданные
            filename_encoded = file_name.encode('utf-8')
            metadata = struct.pack('!BI', 1, file_size) + filename_encoded
            
            print("Отправка метаданных...")
            self.sock.sendto(metadata, (self.server_host, self.server_port))
            
            # Ждем подтверждения метаданных
            try:
                data, _ = self.sock.recvfrom(1024)
                if data != b'OK':
                    print(f"Ошибка: сервер не подтвердил метаданные ({data})")
                    return False
            except socket.timeout:
                print("Ошибка: таймаут ожидания подтверждения метаданных")
                return False
            
            print("Метаданные подтверждены, отправляю файл...")
            
            # Шаг 2: Отправляем файл частями
            chunk_size = 1024
            sent = 0
            start_time = time.time()
            
            with open(file_path, 'rb') as f:
                chunk_id = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    packet = struct.pack('!BI', 2, chunk_id) + chunk
                    chunk_id += 1
                    
                    # Отправляем пакет с попытками
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            self.sock.sendto(packet, (self.server_host, self.server_port))
                            
                            # Ждем подтверждения с меньшим таймаутом для ACK
                            self.sock.settimeout(2.0)
                            data, _ = self.sock.recvfrom(1024)
                            self.sock.settimeout(self.timeout)
                            
                            if data == b'ACK':
                                sent += len(chunk)
                                break
                            elif attempt == max_retries - 1:
                                print(f"Ошибка: неверное подтверждение для блока {chunk_id}: {data}")
                                return False
                                
                        except socket.timeout:
                            if attempt == max_retries - 1:
                                print(f"Ошибка: таймаут отправки блока {chunk_id}")
                                return False
                            print(f"  Повтор блока {chunk_id}, попытка {attempt + 1}")
                            continue
                    
                    # Показываем прогресс
                    if chunk_id % 10 == 0 or sent == file_size:
                        progress = (sent / file_size) * 100
                        print(f"\rПрогресс: {progress:.1f}% ({sent:,}/{file_size:,} байт)", end="")
            
            print(f"\nФайл отправлен, жду завершения...")
            
            # Шаг 3: Отправляем сигнал завершения
            end_packet = struct.pack('!B', 3)
            self.sock.sendto(end_packet, (self.server_host, self.server_port))
            
            # Ждем финальное подтверждение
            try:
                self.sock.settimeout(5.0)
                data, _ = self.sock.recvfrom(1024)
                self.sock.settimeout(self.timeout)
                
                if data == b'DONE':
                    total_time = time.time() - start_time
                    speed = (file_size / total_time / 1024) if total_time > 0 else 0
                    
                    print(f"\n✓ Файл успешно отправлен!")
                    print(f"  Время: {total_time:.2f} сек")
                    print(f"  Скорость: {speed:.1f} КБ/с")
                    print(f"  Блоков отправлено: {chunk_id}")
                    return True
                else:
                    print(f"\nОшибка: неверный ответ от сервера: {data}")
                    return False
            except socket.timeout:
                print(f"\nОшибка: таймаут ожидания завершения")
                # Проверяем, может файл уже получен сервером
                print("  Возможно файл был получен, но подтверждение потеряно")
                return True  # Возвращаем True, так как файл мог быть отправлен
            
        except Exception as e:
            print(f"\nОшибка отправки: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if self.sock:
                self.sock.close()
                self.sock = None
    
    # Для обратной совместимости оставляем старый метод
    def send_file_with_retry(self, file_path, max_attempts=3):
        """Алиас для обратной совместимости"""
        return self.send_file(file_path, max_retries=max_attempts)

def main():
    import sys
    
    if len(sys.argv) == 4:
        # python udp_client.py сервер порт файл
        server_host = sys.argv[1]
        server_port = int(sys.argv[2])
        file_path = sys.argv[3]
        
        client = UDPClientSimple(server_host, server_port)
        success = client.send_file(file_path)
        
        if not success:
            print("Отправка не удалась")
            sys.exit(1)
        
    elif len(sys.argv) == 1:
        # Интерактивный режим
        print("=" * 50)
        print("ПРОСТОЙ UDP КЛИЕНТ")
        print("=" * 50)
        
        server_host = input("Адрес сервера [127.0.0.1]: ").strip() or "127.0.0.1"
        server_port = int(input("Порт сервера [9999]: ").strip() or "9999")
        
        while True:
            print("\n" + "-" * 40)
            print("1. Отправить файл")
            print("2. Выход")
            print("-" * 40)
            
            choice = input("Выбор: ").strip()
            
            if choice == "1":
                file_path = input("Путь к файлу: ").strip()
                if os.path.exists(file_path):
                    client = UDPClientSimple(server_host, server_port)
                    client.send_file(file_path)
                else:
                    print(f"Файл не найден: {file_path}")
            elif choice == "2":
                break
            else:
                print("Неверный выбор")
    else:
        print("Использование:")
        print("  python udp_client.py <сервер> <порт> <файл>")
        print("\nПример:")
        print("  python udp_client.py 127.0.0.1 9999 test.txt")

if __name__ == "__main__":
    # Создаем тестовый файл если его нет
    test_file = "test.txt"
    if not os.path.exists(test_file):
        with open(test_file, "w", encoding='utf-8') as f:
            f.write("Это тестовый файл для UDP трансфера.\n" * 10)
        print(f"Создан тестовый файл: {test_file}")
        print(f"Размер: {os.path.getsize(test_file):,} байт")
    
    main()