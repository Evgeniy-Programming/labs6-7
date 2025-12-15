# udp_server.py (исправленная версия)
import socket
import struct
import os
import sys
import time  # Добавляем этот импорт
from pathlib import Path

class UDPServerSimple:
    def __init__(self, host='127.0.0.1', port=9999):
        self.host = host
        self.port = port
        self.download_dir = Path("received_files")
        self.download_dir.mkdir(exist_ok=True)
        self.last_activity = time.time()  # Инициализируем здесь
        
        print("=" * 50)
        print("ПРОСТОЙ UDP СЕРВЕР")
        print("=" * 50)
        print(f"Папка для загрузок: {self.download_dir.absolute()}")
        print(f"Слушаю на: {host}:{port}")
        print("=" * 50)
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.settimeout(1.0)
        
    def run(self):
        print("Сервер запущен. Ожидание файлов...")
        print("Ctrl+C для остановки\n")
        
        try:
            while True:
                try:
                    # Ждем первый пакет
                    data, addr = self.sock.recvfrom(65535)
                    
                    if not data or len(data) < 1:
                        # Проверяем, не прошло ли слишком много времени без активности
                        if time.time() - self.last_activity > 60:  # 1 минута
                            print(f"Активность: ожидание...")
                            self.last_activity = time.time()
                        continue
                    
                    self.last_activity = time.time()
                    
                    # Первый байт - тип пакета
                    packet_type = data[0]
                    
                    if packet_type == 1:  # Метаданные файла
                        print(f"\n[{time.strftime('%H:%M:%S')}] Получаю новый файл от {addr[0]}:{addr[1]}")
                        
                        if len(data) < 5:
                            print("Ошибка: неверный формат метаданных")
                            continue
                        
                        # Разбираем метаданные
                        file_size = struct.unpack('!I', data[1:5])[0]
                        filename = data[5:].decode('utf-8', errors='ignore').strip('\x00')
                        
                        if not filename:
                            filename = f"file_{int(time.time())}.bin"
                        
                        print(f"  Имя файла: {filename}")
                        print(f"  Размер: {file_size:,} байт")
                        
                        # Создаем безопасное имя файла
                        safe_name = self.make_safe_filename(filename)
                        filepath = self.download_dir / safe_name
                        
                        # Проверяем, не существует ли файл
                        counter = 1
                        while filepath.exists():
                            name, ext = os.path.splitext(safe_name)
                            filepath = self.download_dir / f"{name}_{counter}{ext}"
                            counter += 1
                        
                        # Отправляем подтверждение метаданных
                        self.sock.sendto(b'OK', addr)
                        
                        # Получаем данные файла
                        received = 0
                        expected_chunk_id = 0
                        
                        with open(filepath, 'wb') as f:
                            while received < file_size:
                                try:
                                    chunk_data, chunk_addr = self.sock.recvfrom(65535)
                                    
                                    if not chunk_data or chunk_addr != addr:
                                        continue
                                    
                                    chunk_type = chunk_data[0]
                                    
                                    if chunk_type == 2:  # Данные файла
                                        if len(chunk_data) < 5:
                                            continue
                                        
                                        chunk_id = struct.unpack('!I', chunk_data[1:5])[0]
                                        chunk_content = chunk_data[5:]
                                        
                                        # Сохраняем данные
                                        f.write(chunk_content)
                                        received += len(chunk_content)
                                        expected_chunk_id += 1
                                        
                                        # Показываем прогресс
                                        if file_size > 0:
                                            progress = (received / file_size) * 100
                                            if int(progress) % 25 == 0 or received == file_size:
                                                print(f"  Прогресс: {int(progress)}% ({received:,}/{file_size:,} байт)")
                                        
                                        # Отправляем подтверждение
                                        self.sock.sendto(b'ACK', addr)
                                        
                                    elif chunk_type == 3:  # Завершение
                                        print("  Получен сигнал завершения")
                                        break
                                        
                                except socket.timeout:
                                    # Проверяем, не завершилась ли передача
                                    if received >= file_size:
                                        break
                                    continue
                        
                        # Проверяем целостность файла
                        actual_size = os.path.getsize(filepath)
                        if actual_size == file_size:
                            print(f"[{time.strftime('%H:%M:%S')}] ✓ Файл успешно сохранен: {filepath.name}")
                            print(f"  Фактический размер: {actual_size:,} байт")
                            # Отправляем финальное подтверждение
                            self.sock.sendto(b'DONE', addr)
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] ✗ Ошибка: несовпадение размеров (ожидалось: {file_size}, получено: {actual_size})")
                            self.sock.sendto(b'ERROR', addr)
                    
                    elif packet_type == 3:  # Сигнал завершения от клиента
                        print(f"[{time.strftime('%H:%M:%S')}] Клиент {addr[0]}:{addr[1]} завершил передачу")
                        
                except socket.timeout:
                    # Таймаут - нормально, просто продолжаем ждать
                    continue
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"[{time.strftime('%H:%M:%S')}] Ошибка при обработке пакета: {e}")
                    continue
                    
        except KeyboardInterrupt:
            print(f"\n[{time.strftime('%H:%M:%S')}] Сервер остановлен пользователем")
        except Exception as e:
            print(f"\n[{time.strftime('%H:%M:%S')}] Ошибка сервера: {e}")
        finally:
            self.sock.close()
            print(f"[{time.strftime('%H:%M:%S')}] Сокет закрыт")
    
    def make_safe_filename(self, filename):
        """Создание безопасного имени файла"""
        safe = filename.strip()
        for char in '/\\:*?"<>|':
            safe = safe.replace(char, '_')
        
        # Ограничиваем длину имени
        if len(safe) > 100:
            name, ext = os.path.splitext(safe)
            safe = name[:100-len(ext)] + ext
        
        # Если имя пустое
        if not safe:
            safe = f"file_{int(time.time())}.bin"
        
        return safe

def main():
    import sys
    
    host = '127.0.0.1'
    port = 9999
    
    if len(sys.argv) == 3:
        host = sys.argv[1]
        port = int(sys.argv[2])
    elif len(sys.argv) > 1:
        print("Использование: python udp_server.py [хост] [порт]")
        print(f"По умолчанию: {host}:{port}")
        return
    
    server = UDPServerSimple(host, port)
    server.run()

if __name__ == "__main__":
    main()