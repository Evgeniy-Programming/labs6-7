import socket
import struct
import os
import sys

class TCPClientSimple:
    def __init__(self, server_host='localhost', server_port=8888):
        self.server_host = server_host
        self.server_port = server_port
    
    def connect(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_host, self.server_port))
            return True
        except Exception:
            return False
    
    def send_file(self, file_path):
        if not os.path.exists(file_path):
            print(f"Файл не найден: {file_path}")
            return False
        
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            print(f"Отправка файла: {file_name} ({file_size} байт)")
            
            header = struct.pack('I', file_size)
            name_encoded = file_name.encode('utf-8').ljust(64, b'\0')
            self.client_socket.send(header + name_encoded)
            
            with open(file_path, 'rb') as file:
                while True:
                    chunk = file.read(4096)
                    if not chunk:
                        break
                    self.client_socket.send(chunk)
            
            response = self.client_socket.recv(1024)
            if response == b"SUCCESS":
                print("Файл успешно отправлен")
                return True
            else:
                print("Ошибка при отправке")
                return False
                
        except Exception as e:
            print(f"Ошибка: {e}")
            return False
    
    def disconnect(self):
        if self.client_socket:
            self.client_socket.close()

def main():
    if len(sys.argv) == 4:
        # Использование: python tcp_client_simple.py сервер порт файл
        host = sys.argv[1]
        port = int(sys.argv[2])
        file_path = sys.argv[3]
        
        client = TCPClientSimple(server_host=host, server_port=port)
        if client.connect():
            client.send_file(file_path)
            client.disconnect()
        else:
            print("Не удалось подключиться к серверу")
    
    elif len(sys.argv) == 3:
        # Только сервер и порт
        host = sys.argv[1]
        port = int(sys.argv[2])
        
        client = TCPClientSimple(server_host=host, server_port=port)
        
        while True:
            print("\n1. Отправить файл")
            print("2. Выход")
            choice = input("Выбор: ")
            
            if choice == "1":
                file_path = input("Путь к файлу: ")
                if client.connect():
                    client.send_file(file_path)
                    client.disconnect()
                else:
                    print("Не удалось подключиться")
            
            elif choice == "2":
                break
    
    else:
        # Интерактивный режим
        host = input("Адрес сервера [localhost]: ").strip() or "localhost"
        port_input = input("Порт [8888]: ").strip()
        port = int(port_input) if port_input else 8888
        
        client = TCPClientSimple(server_host=host, server_port=port)
        
        while True:
            print("\n1. Отправить файл")
            print("2. Выход")
            choice = input("Выбор: ")
            
            if choice == "1":
                file_path = input("Путь к файлу: ")
                if client.connect():
                    client.send_file(file_path)
                    client.disconnect()
                else:
                    print("Не удалось подключиться")
            
            elif choice == "2":
                break

if __name__ == "__main__":
    main()