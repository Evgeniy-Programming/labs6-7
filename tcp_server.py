"""
TCP СЕРВЕР для приема файлов
Создает папку downloads РЯДОМ с этим скриптом
"""

import socket
import struct
import os
import threading
import time
from pathlib import Path

class TCPServerFixed:
    def __init__(self, host='0.0.0.0', port=8888):
        self.host = host
        self.port = port
        
        script_dir = Path(__file__).parent.absolute()
        self.download_dir = script_dir / "server_downloads"
        
        self.download_dir.mkdir(exist_ok=True)
        
        print("="*70)
        print("  TCP ФАЙЛОВЫЙ СЕРВЕР ")
        print("="*70)
        print(f" Файлы сохраняются в: {self.download_dir}")
        print(f" Адрес: {host}:{port}")
        print(f" Абсолютный путь: {self.download_dir.absolute()}")
        print("="*70)
        
        self.server_socket = None
        self.running = False
        self.client_counter = 0
    
    def show_downloads_content(self):
        """Показать содержимое папки downloads"""
        print("\n СОДЕРЖИМОЕ папки загрузок:")
        if not self.download_dir.exists():
            print("   Папка не существует!")
            return
        
        files = list(self.download_dir.iterdir())
        if not files:
            print("Папка пуста")
        else:
            for file in files:
                size = file.stat().st_size
                print(f"   {file.name} ({size:,} байт)")
        print()
    
    def start(self):
        """Запуск сервера"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)
        
        self.running = True
        
        print("\n Сервер запущен и готов принимать файлы!")
        print(" Ожидание подключений... (Ctrl+C для остановки)\n")
        
        # Показываем что сейчас в папке
        self.show_downloads_content()
        
        try:
            while self.running:
                try:
                    # Ждем подключения
                    client_socket, client_address = self.server_socket.accept()
                    self.client_counter += 1
                    client_id = self.client_counter
                    
                    print(f"Подключение #{client_id} от {client_address[0]}:{client_address[1]}")
                    
                    # Обрабатываем клиента в отдельном потоке
                    thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address, client_id)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except socket.timeout:
                    continue
                    
        except KeyboardInterrupt:
            print("\n Остановка сервера...")
        except Exception as e:
            print(f"\n Ошибка: {e}")
        finally:
            self.running = False
            if self.server_socket:
                self.server_socket.close()
            
            print("\n" + "="*70)
            print(" ИТОГИ РАБОТЫ СЕРВЕРА:")
            print(f" Папка с файлами: {self.download_dir}")
            self.show_downloads_content()
            print(" Сервер остановлен")
    
    def handle_client(self, client_socket, client_address, client_id):
        """Обработка клиента"""
        try:
            header_data = self.receive_all(client_socket, 68)
            if not header_data or len(header_data) < 68:
                print(f" Клиент #{client_id}: Неполный заголовок")
                return
            
            file_size = struct.unpack('I', header_data[:4])[0]
            file_name_encoded = header_data[4:68]
            file_name = file_name_encoded.split(b'\0')[0].decode('utf-8', errors='ignore')
            
            if not file_name:
                file_name = f"file_{client_id}"
            
            print(f"\n Клиент #{client_id} отправляет:")
            print(f"    Файл: {file_name}")
            print(f"    Размер: {file_size:,} байт")
            print(f"    Сохраняю в: {self.download_dir}")
            
            safe_name = self.make_safe_filename(file_name)
            save_path = self.download_dir / safe_name
            
            counter = 1
            while save_path.exists():
                name_stem = save_path.stem
                suffix = save_path.suffix
                save_path = self.download_dir / f"{name_stem}_{counter}{suffix}"
                counter += 1
            
            received = 0
            with open(save_path, 'wb') as file:
                while received < file_size:
                    chunk_size = min(4096, file_size - received)
                    chunk = self.receive_all(client_socket, chunk_size)
                    if not chunk:
                        print(f" Клиент #{client_id}: Соединение прервано")
                        break
                    
                    file.write(chunk)
                    received += len(chunk)
                    
                    if file_size > 0:
                        progress = (received / file_size) * 100
                        if int(progress) % 25 == 0 and progress > 0:
                            print(f"   ⏳ {int(progress)}%...")
            
            if received == file_size:
                print(f" Клиент #{client_id}: Файл успешно сохранен!")
                print(f"   Путь: {save_path}")
                print(f"   Размер на диске: {save_path.stat().st_size:,} байт")
                client_socket.send(b"SUCCESS")
                
                self.show_downloads_content()
            else:
                print(f" Клиент #{client_id}: Ошибка! Получено {received:,}/{file_size:,} байт")
                if save_path.exists():
                    save_path.unlink()
                client_socket.send(b"ERROR")
                
        except Exception as e:
            print(f" Клиент #{client_id}: Ошибка обработки: {e}")
            try:
                client_socket.send(b"ERROR")
            except:
                pass
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def receive_all(self, sock, n):
        """Получить точно n байт"""
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data
    
    def make_safe_filename(self, filename):
        """Создать безопасное имя файла"""
        safe = filename.replace('/', '_').replace('\\', '_')
        safe = safe.replace(':', '_').replace('*', '_')
        safe = safe.replace('?', '_').replace('"', '_')
        safe = safe.replace('<', '_').replace('>', '_')
        safe = safe.replace('|', '_')

        if not safe:
            safe = "unnamed_file"
        
        if len(safe) > 100:
            name, ext = os.path.splitext(safe)
            safe = name[:100-len(ext)] + ext
        
        return safe
    
    def stop(self):
        """Остановка сервера"""
        self.running = False

if __name__ == "__main__":
    print("\n" + "="*70)
    print(" ЗАПУСК TCP СЕРВЕРА")
    print("="*70)
    
    # Настройки
    host = input("Адрес сервера [0.0.0.0]: ").strip() or "0.0.0.0"
    port_input = input("Порт [8888]: ").strip()
    port = int(port_input) if port_input else 8888
    
    # Запускаем
    server = TCPServerFixed(host=host, port=port)
    server.start()