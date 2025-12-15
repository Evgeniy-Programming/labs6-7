"""
ГРАФИЧЕСКОЕ ПРИЛОЖЕНИЕ ДЛЯ УПРАВЛЕНИЯ ПЕРЕДАЧЕЙ ФАЙЛОВ
Поддерживает TCP и UDP протоколы
Исправленная версия с улучшенной архитектурой
"""

import sys
import os
import threading
import subprocess
import time
import socket
import json
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class LogSignals(QObject):
    """Сигналы для безопасного логгирования из потоков"""
    log_signal = pyqtSignal(str, str)

class ReceivedFilesModel(QAbstractTableModel):
    """Модель для отображения полученных файлов"""
    def __init__(self, download_dir_tcp, download_dir_udp):
        super().__init__()
        self.download_dir_tcp = Path(download_dir_tcp)
        self.download_dir_udp = Path(download_dir_udp)
        self.headers = ["Имя файла", "Размер", "Дата изменения", "Протокол", "Путь"]
        self.files = []
        self.update_files()
        
    def update_files(self):
        """Обновить список файлов"""
        self.beginResetModel()
        self.files = []
        
        # TCP файлы
        if self.download_dir_tcp.exists():
            for file_path in self.download_dir_tcp.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    size = self.format_size(stat.st_size)
                    mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))
                    
                    filename = file_path.name
                    protocol = "TCP"
                    clean_name = filename
                    
                    self.files.append({
                        'path': file_path,
                        'name': clean_name,
                        'size': size,
                        'mtime': mtime,
                        'protocol': protocol,
                        'full_path': str(file_path)
                    })
        
        # UDP файлы
        if self.download_dir_udp.exists():
            for file_path in self.download_dir_udp.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    size = self.format_size(stat.st_size)
                    mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime))
                    
                    filename = file_path.name
                    protocol = "UDP"
                    clean_name = filename
                    
                    self.files.append({
                        'path': file_path,
                        'name': clean_name,
                        'size': size,
                        'mtime': mtime,
                        'protocol': protocol,
                        'full_path': str(file_path)
                    })
        
        # Сортируем по дате (новые сверху)
        self.files.sort(key=lambda x: x['path'].stat().st_mtime, reverse=True)
        self.endResetModel()
    
    def format_size(self, size_bytes):
        """Форматирование размера файла"""
        if size_bytes == 0:
            return "0 Б"
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ТБ"
    
    def rowCount(self, parent=None):
        return len(self.files)
    
    def columnCount(self, parent=None):
        return len(self.headers)
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.files):
            return None
        
        row = index.row()
        col = index.column()
        file_info = self.files[row]
        
        if role == Qt.DisplayRole:
            if col == 0:
                return file_info['name']
            elif col == 1:
                return file_info['size']
            elif col == 2:
                return file_info['mtime']
            elif col == 3:
                return file_info['protocol']
            elif col == 4:
                return str(file_info['path'].parent.name) + "/"
        
        elif role == Qt.ToolTipRole:
            return f"Полный путь: {file_info['full_path']}\nПротокол: {file_info['protocol']}"
        
        elif role == Qt.ForegroundRole and col == 3:
            # Цветовая маркировка протокола
            if file_info['protocol'] == "TCP":
                return QColor("#4CAF50")  # Зеленый для TCP
            else:
                return QColor("#2196F3")  # Синий для UDP
        
        elif role == Qt.UserRole:  # Возвращаем полный путь
            return file_info['full_path']
        
        return None
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

class TCPServerThread(QThread):
    """Рабочий поток для TCP сервера"""
    log_signal = pyqtSignal(str, str)
    server_started = pyqtSignal()
    server_stopped = pyqtSignal()
    
    def __init__(self, host, port, download_dir):
        super().__init__()
        self.host = host
        self.port = port
        self.download_dir = download_dir
        self.is_running = False
        self.server = None
        
    def run(self):
        """Запуск TCP сервера"""
        try:
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from tcp_server import TCPServerFixed
            
            self.server = TCPServerFixed(host=self.host, port=self.port)
            self.is_running = True
            self.server_started.emit()
            self.log_signal.emit(f"TCP сервер запущен на {self.host}:{self.port}", "success")
            
            # Запускаем сервер в блокирующем режиме
            self.server.start()
            
        except ImportError as e:
            self.log_signal.emit(f"Не удалось импортировать TCP сервер: {e}", "error")
        except Exception as e:
            self.log_signal.emit(f"Ошибка TCP сервера: {str(e)}", "error")
        finally:
            self.is_running = False
            self.server_stopped.emit()
    
    def stop(self):
        """Остановка TCP сервера"""
        if self.is_running and self.server:
            self.server.stop()
            self.log_signal.emit("TCP сервер остановлен", "warning")

class UDPWorker(QThread):
    """Рабочий поток для UDP сервера"""
    log_signal = pyqtSignal(str, str)
    server_started = pyqtSignal()
    server_stopped = pyqtSignal()
    
    def __init__(self, host, port, download_dir):
        super().__init__()
        self.host = host
        self.port = port
        self.download_dir = download_dir
        self.is_running = False
        self.process = None
    
    def run(self):
        """Запуск UDP сервера в отдельном процессе"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            udp_server_path = Path(script_dir) / "udp_server.py"
            
            if not udp_server_path.exists():
                self.log_signal.emit(f"Файл udp_server.py не найден: {udp_server_path}", "error")
                return
            
            self.log_signal.emit(f"Запуск UDP сервера на {self.host}:{self.port}...", "info")
            
            # Запускаем процесс с передачей параметров через аргументы
            self.process = subprocess.Popen(
                [sys.executable, str(udp_server_path), self.host, str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            self.is_running = True
            self.server_started.emit()
            self.log_signal.emit("UDP сервер успешно запущен", "success")
            
            # Читаем вывод процесса
            while self.is_running and self.process:
                output = self.process.stdout.readline()
                if not output and self.process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    if line:
                        self.log_signal.emit(f"[UDP Сервер] {line}", "info")
            
            return_code = self.process.wait()
            if return_code != 0:
                self.log_signal.emit(f"UDP сервер завершился с кодом: {return_code}", "warning")
            
        except FileNotFoundError:
            self.log_signal.emit("Python интерпретатор не найден", "error")
        except Exception as e:
            self.log_signal.emit(f"Ошибка UDP сервера: {str(e)}", "error")
        finally:
            self.is_running = False
            self.server_stopped.emit()
    
    def stop(self):
        """Остановка UDP сервера"""
        if self.is_running and self.process:
            self.is_running = False
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.log_signal.emit("UDP сервер остановлен", "warning")

class FileTransferThread(QThread):
    """Поток для отправки файлов"""
    log_signal = pyqtSignal(str, str)
    transfer_complete = pyqtSignal(bool, str)
    
    def __init__(self, protocol, file_path, host, port):
        super().__init__()
        self.protocol = protocol
        self.file_path = file_path
        self.host = host
        self.port = port
        
    def run(self):
        """Запуск передачи файла"""
        try:
            if self.protocol == "TCP":
                self.send_tcp()
            else:
                self.send_udp()
        except Exception as e:
            self.log_signal.emit(f"Ошибка передачи: {str(e)}", "error")
            self.transfer_complete.emit(False, str(e))
    
    def send_tcp(self):
        """Отправка файла по TCP"""
        try:
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from tcp_client import TCPClientSimple
            
            client = TCPClientSimple(server_host=self.host, server_port=self.port)
            
            self.log_signal.emit(f"Подключение к TCP серверу {self.host}:{self.port}...", "info")
            
            if client.connect():
                file_name = os.path.basename(self.file_path)
                self.log_signal.emit(f"Отправка файла {file_name}...", "info")
                
                if client.send_file(self.file_path):
                    self.log_signal.emit(f"Файл успешно отправлен по TCP!", "success")
                    self.transfer_complete.emit(True, "")
                else:
                    self.log_signal.emit("Ошибка отправки файла по TCP", "error")
                    self.transfer_complete.emit(False, "Ошибка отправки")
                
                client.disconnect()
            else:
                self.log_signal.emit(f"Не удалось подключиться к TCP серверу {self.host}:{self.port}", "error")
                self.transfer_complete.emit(False, "Ошибка подключения")
                
        except ImportError as e:
            self.log_signal.emit(f"Не удалось импортировать TCP клиент: {e}", "error")
            self.transfer_complete.emit(False, f"Import error: {e}")
    
    def send_udp(self):
        """Отправка файла по UDP"""
        try:
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from udp_client import UDPClientSimple
            
            file_name = os.path.basename(self.file_path)
            file_size = os.path.getsize(self.file_path)
            size_str = self.format_size(file_size)
            
            self.log_signal.emit(f"Начинаю отправку {file_name} ({size_str}) по UDP...", "info")
            
            # Создаем клиент и отправляем файл
            client = UDPClientSimple(self.host, self.port)
            
            # Используем send_file, который теперь включает ретраи
            success = client.send_file(self.file_path)
            
            if success:
                self.log_signal.emit(
                    f"✓ Файл {file_name} ({size_str}) успешно отправлен по UDP!", 
                    "success"
                )
                self.transfer_complete.emit(True, "")
            else:
                self.log_signal.emit(f"✗ Не удалось отправить файл {file_name} по UDP", "error")
                self.transfer_complete.emit(False, "Ошибка отправки")
                
        except ImportError as e:
            self.log_signal.emit(f"Не удалось импортировать UDP клиент: {e}", "error")
            self.transfer_complete.emit(False, f"Import error: {e}")
        except Exception as e:
            self.log_signal.emit(f"Ошибка UDP отправки: {str(e)}", "error")
            self.transfer_complete.emit(False, str(e))
    
    def format_size(self, size_bytes):
        """Форматирование размера файла"""
        if size_bytes == 0:
            return "0 Б"
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ТБ"

class TransferApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tcp_server_thread = None
        self.udp_worker = None
        self.transfer_thread = None
        
        # Пути для сохранения файлов
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.tcp_download_dir = os.path.join(self.script_dir, "server_downloads")
        self.udp_download_dir = os.path.join(self.script_dir, "received_files")
        
        # Создаем папки если их нет
        os.makedirs(self.tcp_download_dir, exist_ok=True)
        os.makedirs(self.udp_download_dir, exist_ok=True)
        
        self.log_signals = LogSignals()
        self.init_ui()
            
    def init_ui(self):
        self.setWindowTitle("Файловый Трансфер • TCP + UDP")
        self.setGeometry(100, 100, 1200, 850)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной лейаут с разделением
        main_splitter = QSplitter(Qt.Vertical)
        
        # ===== ВЕРХНЯЯ ЧАСТЬ: УПРАВЛЕНИЕ =====
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # Заголовок протокола
        protocol_label = QLabel("Файловый трансфер - Поддержка TCP и UDP протоколов")
        protocol_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #2196F3; padding: 10px;")
        protocol_label.setAlignment(Qt.AlignCenter)
        
        # === ВЫБОР ПРОТОКОЛА ===
        protocol_group = QGroupBox("Выбор протокола передачи")
        protocol_group_layout = QHBoxLayout(protocol_group)
        
        self.protocol_tcp = QRadioButton("TCP (Надежный)")
        self.protocol_tcp.setChecked(True)
        self.protocol_tcp.toggled.connect(self.on_protocol_changed)
        self.protocol_tcp.setStyleSheet("""
            QRadioButton {
                color: white;
                font-size: 14px;
                padding: 8px;
                margin-right: 20px;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
            }
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 2px solid #45a049;
                border-radius: 10px;
            }
        """)
        
        self.protocol_udp = QRadioButton("UDP (Быстрый)")
        self.protocol_udp.toggled.connect(self.on_protocol_changed)
        self.protocol_udp.setStyleSheet("""
            QRadioButton {
                color: white;
                font-size: 14px;
                padding: 8px;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
            }
            QRadioButton::indicator:checked {
                background-color: #2196F3;
                border: 2px solid #1976D2;
                border-radius: 10px;
            }
        """)
        
        protocol_group_layout.addWidget(self.protocol_tcp)
        protocol_group_layout.addWidget(self.protocol_udp)
        protocol_group_layout.addStretch()
        
        # Создаем виджеты для управления серверами
        self.server_container = QWidget()
        server_stack = QStackedLayout(self.server_container)
        
        # ===== TCP ПАНЕЛЬ =====
        self.tcp_panel = QGroupBox("TCP Сервер")
        tcp_layout = QVBoxLayout()
        
        # Настройки TCP сервера
        tcp_form = QFormLayout()
        self.tcp_host = QLineEdit("127.0.0.1")
        self.tcp_port = QLineEdit("8888")
        self.tcp_server_status = QLabel("Сервер остановлен")
        self.tcp_server_status.setStyleSheet("color: #f44336; font-weight: bold;")
        
        tcp_form.addRow("Хост:", self.tcp_host)
        tcp_form.addRow("Порт:", self.tcp_port)
        tcp_form.addRow("Статус:", self.tcp_server_status)
        
        # Кнопки TCP
        tcp_buttons_layout = QHBoxLayout()
        self.btn_start_tcp_server = QPushButton("▶ Запустить TCP сервер")
        self.btn_start_tcp_server.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        self.btn_stop_tcp_server = QPushButton("■ Остановить TCP сервер")
        self.btn_stop_tcp_server.setEnabled(False)
        self.btn_stop_tcp_server.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        tcp_buttons_layout.addWidget(self.btn_start_tcp_server)
        tcp_buttons_layout.addWidget(self.btn_stop_tcp_server)
        tcp_buttons_layout.addStretch()
        
        tcp_layout.addLayout(tcp_form)
        tcp_layout.addLayout(tcp_buttons_layout)
        self.tcp_panel.setLayout(tcp_layout)
        
        # ===== UDP ПАНЕЛЬ =====
        self.udp_panel = QGroupBox("UDP Сервер")
        udp_layout = QVBoxLayout()

        # Настройки UDP сервера
        udp_form = QFormLayout()
        self.udp_host = QLineEdit("127.0.0.1")
        self.udp_port = QLineEdit("9999")
        self.udp_server_status = QLabel("Сервер остановлен")
        self.udp_server_status.setStyleSheet("color: #f44336; font-weight: bold;")

        udp_form.addRow("Хост сервера:", self.udp_host)
        udp_form.addRow("Порт сервера:", self.udp_port)
        udp_form.addRow("Статус:", self.udp_server_status)

        # Кнопки UDP
        udp_buttons_layout = QHBoxLayout()
        self.btn_start_udp_server = QPushButton("▶ Запустить UDP сервер")
        self.btn_start_udp_server.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        self.btn_stop_udp_server = QPushButton("■ Остановить UDP сервер")
        self.btn_stop_udp_server.setEnabled(False)
        self.btn_stop_udp_server.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        udp_buttons_layout.addWidget(self.btn_start_udp_server)
        udp_buttons_layout.addWidget(self.btn_stop_udp_server)
        udp_buttons_layout.addStretch()

        udp_layout.addLayout(udp_form)
        udp_layout.addLayout(udp_buttons_layout)
        self.udp_panel.setLayout(udp_layout)
        
        # Добавляем панели в стек
        server_stack.addWidget(self.tcp_panel)
        server_stack.addWidget(self.udp_panel)
        
        # === ПАНЕЛЬ ОТПРАВКИ ФАЙЛОВ ===
        send_group = QGroupBox("Отправка файла")
        send_layout = QVBoxLayout()
        
        # Выбор файла
        file_layout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Выберите файл для отправки...")
        self.btn_browse = QPushButton("📁 Обзор...")
        self.btn_browse.setStyleSheet("padding: 8px;")
        
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(self.btn_browse)
        
        # Панель настроек отправки
        self.send_settings_container = QWidget()
        send_settings_stack = QStackedLayout(self.send_settings_container)
        
        # TCP настройки отправки
        tcp_send_layout = QFormLayout()
        tcp_send_widget = QWidget()
        self.tcp_recipient_host = QLineEdit("127.0.0.1")
        self.tcp_recipient_port = QLineEdit("8888")
        tcp_send_layout.addRow("Хост получателя:", self.tcp_recipient_host)
        tcp_send_layout.addRow("Порт получателя:", self.tcp_recipient_port)
        tcp_send_widget.setLayout(tcp_send_layout)
        
        # UDP настройки отправки
        udp_send_layout = QFormLayout()
        udp_send_widget = QWidget()
        self.udp_recipient_host = QLineEdit("127.0.0.1")
        self.udp_recipient_port = QLineEdit("9999")
        udp_send_layout.addRow("Адрес сервера:", self.udp_recipient_host)
        udp_send_layout.addRow("Порт сервера:", self.udp_recipient_port)
        udp_send_widget.setLayout(udp_send_layout)
        
        send_settings_stack.addWidget(tcp_send_widget)
        send_settings_stack.addWidget(udp_send_widget)
        
        # Кнопка отправки
        self.btn_send_file = QPushButton("Отправить файл по TCP")
        self.btn_send_file.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        send_layout.addLayout(file_layout)
        send_layout.addWidget(self.send_settings_container)
        send_layout.addWidget(self.btn_send_file)
        send_group.setLayout(send_layout)
        
        # Добавляем все панели управления
        control_layout.addWidget(protocol_label)
        control_layout.addWidget(protocol_group)
        control_layout.addWidget(self.server_container)
        control_layout.addWidget(send_group)
        
        # ===== НИЖНЯЯ ЧАСТЬ: ПОЛУЧЕННЫЕ ФАЙЛЫ И ЛОГ =====
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # Создаем вкладки для файлов и лога
        tabs = QTabWidget()
        
        # Вкладка с полученными файлами
        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)
        
        # Панель управления файлами
        files_control_layout = QHBoxLayout()
        self.btn_refresh_files = QPushButton("🔄 Обновить")
        self.btn_open_tcp_folder = QPushButton("📂 TCP папка")
        self.btn_open_udp_folder = QPushButton("📂 UDP папка")
        self.btn_delete_file = QPushButton("🗑️ Удалить выбранное")
        
        # Стили для кнопок папок
        self.btn_open_tcp_folder.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 6px;
                border-radius: 3px;
            }
        """)
        self.btn_open_udp_folder.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 6px;
                border-radius: 3px;
            }
        """)
        
        files_control_layout.addWidget(self.btn_refresh_files)
        files_control_layout.addWidget(self.btn_open_tcp_folder)
        files_control_layout.addWidget(self.btn_open_udp_folder)
        files_control_layout.addWidget(self.btn_delete_file)
        files_control_layout.addStretch()
        
        # Таблица файлов
        self.files_table = QTableView()
        self.files_table.setSelectionBehavior(QTableView.SelectRows)
        self.files_table.setSelectionMode(QTableView.SingleSelection)
        self.files_table.setAlternatingRowColors(True)
        self.files_table.horizontalHeader().setStretchLastSection(True)
        self.files_table.setSortingEnabled(True)
        
        files_layout.addLayout(files_control_layout)
        files_layout.addWidget(self.files_table)
        
        # Вкладка с логом
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #353535;
                border: 1px solid #555;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                color: white;
                padding: 5px;
            }
        """)
        
        log_buttons_layout = QHBoxLayout()
        self.btn_clear_log = QPushButton("🧹 Очистить журнал")
        self.btn_save_log = QPushButton("💾 Сохранить лог")
        
        log_buttons_layout.addWidget(self.btn_clear_log)
        log_buttons_layout.addWidget(self.btn_save_log)
        log_buttons_layout.addStretch()
        
        log_layout.addWidget(self.log_text)
        log_layout.addLayout(log_buttons_layout)
        
        # Добавляем вкладки
        tabs.addTab(files_tab, "📁 Полученные файлы")
        tabs.addTab(log_tab, "📝 Журнал событий")
        
        bottom_layout.addWidget(tabs)
        
        # Собираем главный интерфейс
        main_splitter.addWidget(control_widget)
        main_splitter.addWidget(bottom_widget)
        main_splitter.setSizes([350, 450])
        
        # Главный лейаут
        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(main_splitter)
        
        # ===== ИНИЦИАЛИЗАЦИЯ МОДЕЛИ ФАЙЛОВ =====
        self.files_model = ReceivedFilesModel(self.tcp_download_dir, self.udp_download_dir)
        self.files_table.setModel(self.files_model)
        self.files_table.setColumnWidth(0, 250)  # Имя файла
        self.files_table.setColumnWidth(1, 100)  # Размер
        self.files_table.setColumnWidth(2, 150)  # Дата
        self.files_table.setColumnWidth(3, 80)   # Протокол
        self.files_table.setColumnWidth(4, 100)  # Путь
        
        # ===== ПОДКЛЮЧЕНИЕ СИГНАЛОВ =====
        # TCP сигналы
        self.btn_start_tcp_server.clicked.connect(self.start_tcp_server)
        self.btn_stop_tcp_server.clicked.connect(self.stop_tcp_server)
        
        # UDP сигналы
        self.btn_start_udp_server.clicked.connect(self.start_udp_server)
        self.btn_stop_udp_server.clicked.connect(self.stop_udp_server)
        
        # Общие сигналы
        self.btn_browse.clicked.connect(self.browse_file)
        self.btn_send_file.clicked.connect(self.send_file)
        
        self.btn_refresh_files.clicked.connect(self.refresh_files)
        self.btn_open_tcp_folder.clicked.connect(lambda: self.open_download_folder(self.tcp_download_dir))
        self.btn_open_udp_folder.clicked.connect(lambda: self.open_download_folder(self.udp_download_dir))
        self.btn_delete_file.clicked.connect(self.delete_selected_file)
        
        self.btn_clear_log.clicked.connect(self.clear_log)
        self.btn_save_log.clicked.connect(self.save_log)
        
        # Подключаем сигналы логгирования
        self.log_signals.log_signal.connect(self.log_message_safe)
        
        # Таймер для обновления списка файлов
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_files)
        self.update_timer.start(3000)  # Обновлять каждые 3 секунды
        
        # Инициализируем интерфейс
        self.on_protocol_changed()
        
    def on_protocol_changed(self):
        """Обработка изменения выбранного протокола"""
        is_tcp = self.protocol_tcp.isChecked()
        
        # Меняем стек серверов
        server_stack = self.server_container.layout()
        server_stack.setCurrentIndex(0 if is_tcp else 1)
        
        # Меняем стек настроек отправки
        send_settings_stack = self.send_settings_container.layout()
        send_settings_stack.setCurrentIndex(0 if is_tcp else 1)
        
        # Меняем текст кнопки отправки
        protocol_text = "TCP" if is_tcp else "UDP"
        color = "#4CAF50" if is_tcp else "#2196F3"
        self.btn_send_file.setText(f"Отправить файл по {protocol_text}")
        self.btn_send_file.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-weight: bold;
                padding: 12px;
                border-radius: 5px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {'#45a049' if is_tcp else '#1976D2'};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
            }}
        """)
    
    def log_message_safe(self, message, level="info"):
        """Безопасное добавление сообщения в лог (вызывается из главного потока)"""
        self._log_message(message, level)
    
    def _log_message(self, message, level="info"):
        """Внутренний метод для логгирования"""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        
        if level == "error":
            color = "#d32f2f"
            icon = "❌"
        elif level == "success":
            color = "#388e3c"
            icon = "✅"
        elif level == "warning":
            color = "#f57c00"
            icon = "⚠️"
        else:
            color = "#1976d2"
            icon = "ℹ️"
        
        html = f'<span style="color:#757575">[{timestamp}]</span> '
        html += f'<span style="color:{color}; font-weight:bold">{icon} {message}</span><br>'
        
        self.log_text.append(html)
        
        # Автопрокрутка
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def refresh_files(self):
        """Обновить список файлов"""
        self.files_model.update_files()
    
    def open_download_folder(self, folder_path):
        """Открыть папку с загрузками"""
        folder = Path(folder_path)
        if folder.exists():
            if sys.platform == 'win32':
                os.startfile(str(folder))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(folder)])
            else:
                subprocess.Popen(['xdg-open', str(folder)])
            self._log_message(f"Открыта папка: {folder}", "info")
        else:
            self._log_message(f"Папка не существует: {folder}", "warning")
            folder.mkdir(exist_ok=True)
            self._log_message(f"Создана папка: {folder}", "info")
            self.refresh_files()
    
    def delete_selected_file(self):
        """Удалить выбранный файл"""
        selected = self.files_table.selectionModel().selectedRows()
        if not selected:
            self._log_message("Выберите файл для удаления", "warning")
            return
        
        for index in selected:
            file_path = self.files_model.data(index, Qt.UserRole)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    file_name = os.path.basename(file_path)
                    self._log_message(f"Удалён файл: {file_name}", "info")
                except Exception as e:
                    self._log_message(f"Ошибка удаления: {str(e)}", "error")
        
        self.refresh_files()
    
    def save_log(self):
        """Сохранить лог в файл"""
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Сохранить лог", "", "Текстовые файлы (*.txt);;Все файлы (*)"
        )
        if file_name:
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self._log_message(f"Лог сохранён в: {file_name}", "success")
            except Exception as e:
                self._log_message(f"Ошибка сохранения: {str(e)}", "error")
    
    def browse_file(self):
        """Выбор файла для отправки"""
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл для отправки", "", "Все файлы (*)"
        )
        if file_name:
            self.file_path.setText(file_name)
            file_size = os.path.getsize(file_name)
            size_str = self.files_model.format_size(file_size)
            self._log_message(f"Выбран файл: {os.path.basename(file_name)} ({size_str})", "info")
    
    # ===== TCP МЕТОДЫ =====
    def start_tcp_server(self):
        """Запуск TCP сервера в отдельном потоке"""
        host = self.tcp_host.text().strip()
        port_text = self.tcp_port.text().strip()
        
        if not host or not port_text:
            self._log_message("Заполните хост и порт!", "error")
            return
        
        try:
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            self._log_message("Порт должен быть числом от 1 до 65535!", "error")
            return
        
        # Создаем и запускаем поток сервера
        self.tcp_server_thread = TCPServerThread(host, port, self.tcp_download_dir)
        self.tcp_server_thread.log_signal.connect(self.log_message_safe)
        self.tcp_server_thread.server_started.connect(self.on_tcp_server_started)
        self.tcp_server_thread.server_stopped.connect(self.on_tcp_server_stopped)
        self.tcp_server_thread.start()
    
    def on_tcp_server_started(self):
        """Обработка запуска TCP сервера"""
        self.btn_start_tcp_server.setEnabled(False)
        self.btn_stop_tcp_server.setEnabled(True)
        self.tcp_server_status.setText("🟢 TCP сервер запущен")
        self.tcp_server_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
    
    def on_tcp_server_stopped(self):
        """Обработка остановки TCP сервера"""
        self.btn_start_tcp_server.setEnabled(True)
        self.btn_stop_tcp_server.setEnabled(False)
        self.tcp_server_status.setText("🔴 TCP сервер остановлен")
        self.tcp_server_status.setStyleSheet("color: #f44336; font-weight: bold;")
        self.tcp_server_thread = None
    
    def stop_tcp_server(self):
        """Остановка TCP сервера"""
        if self.tcp_server_thread and self.tcp_server_thread.is_running:
            self.tcp_server_thread.stop()
            self._log_message("Остановка TCP сервера...", "info")
    
    # ===== UDP МЕТОДЫ =====
    def start_udp_server(self):
        """Запуск UDP сервера"""
        host = self.udp_host.text().strip()
        port_text = self.udp_port.text().strip()
        
        if not host or not port_text:
            self._log_message("Заполните хост и порт для UDP сервера!", "error")
            return
        
        try:
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            self._log_message("Порт должен быть числом от 1 до 65535!", "error")
            return
        
        # Создаем и запускаем UDP worker
        self.udp_worker = UDPWorker(host, port, self.udp_download_dir)
        self.udp_worker.log_signal.connect(self.log_message_safe)
        self.udp_worker.server_started.connect(self.on_udp_server_started)
        self.udp_worker.server_stopped.connect(self.on_udp_server_stopped)
        self.udp_worker.start()
    
    def on_udp_server_started(self):
        """Обработка запуска UDP сервера"""
        self.btn_start_udp_server.setEnabled(False)
        self.btn_stop_udp_server.setEnabled(True)
        self.udp_server_status.setText("🟢 UDP сервер запущен")
        self.udp_server_status.setStyleSheet("color: #2196F3; font-weight: bold;")
    
    def on_udp_server_stopped(self):
        """Обработка остановки UDP сервера"""
        self.btn_start_udp_server.setEnabled(True)
        self.btn_stop_udp_server.setEnabled(False)
        self.udp_server_status.setText("🔴 UDP сервер остановлен")
        self.udp_server_status.setStyleSheet("color: #f44336; font-weight: bold;")
        self.udp_worker = None
    
    def stop_udp_server(self):
        """Остановка UDP сервера"""
        if self.udp_worker and self.udp_worker.is_running:
            self.udp_worker.stop()
            self._log_message("Остановка UDP сервера...", "info")
    
    # ===== МЕТОДЫ ОТПРАВКИ ФАЙЛОВ =====
    def send_file(self):
        """Отправка файла"""
        file_path = self.file_path.text().strip()
        
        if not file_path or not os.path.exists(file_path):
            self._log_message("Выберите существующий файл!", "error")
            return
        
        is_tcp = self.protocol_tcp.isChecked()
        
        if is_tcp:
            host = self.tcp_recipient_host.text().strip()
            port_text = self.tcp_recipient_port.text().strip()
        else:
            host = self.udp_recipient_host.text().strip()
            port_text = self.udp_recipient_port.text().strip()
        
        if not host or not port_text:
            self._log_message("Заполните хост и порт получателя!", "error")
            return
        
        try:
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            self._log_message("Порт должен быть числом от 1 до 65535!", "error")
            return
        
        # Блокируем кнопку на время отправки
        self.btn_send_file.setEnabled(False)
        protocol = "TCP" if is_tcp else "UDP"
        self.btn_send_file.setText(f"⏳ Отправка {protocol}...")
        
        # Запускаем поток отправки
        self.transfer_thread = FileTransferThread(
            protocol, 
            file_path, 
            host, 
            port
        )
        self.transfer_thread.log_signal.connect(self.log_message_safe)
        self.transfer_thread.transfer_complete.connect(self.on_transfer_complete)
        self.transfer_thread.start()
    
    def on_transfer_complete(self, success, error_message):
        """Обработка завершения передачи"""
        # Восстанавливаем кнопку
        is_tcp = self.protocol_tcp.isChecked()
        protocol = "TCP" if is_tcp else "UDP"
        self.btn_send_file.setEnabled(True)
        self.btn_send_file.setText(f"Отправить файл по {protocol}")
        
        # Обновляем список файлов если передача успешна
        if success:
            self.refresh_files()
        
        self.transfer_thread = None
    
    def clear_log(self):
        """Очистка лога"""
        self.log_text.clear()
        self._log_message("Журнал очищен", "info")
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        # Останавливаем TCP сервер
        if self.tcp_server_thread and self.tcp_server_thread.is_running:
            self.stop_tcp_server()
            self.tcp_server_thread.wait(2000)
        
        # Останавливаем UDP сервер
        if self.udp_worker and self.udp_worker.is_running:
            self.stop_udp_server()
            self.udp_worker.wait(2000)
        
        # Останавливаем таймер
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        
        self._log_message("Приложение закрыто", "info")
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Стилизация приложения
    app.setStyle("Fusion")
    
    # Темная тема
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    app.setStyleSheet("""
        QMainWindow {
            background-color: #353535;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #555;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: #404040;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: #aaa;
        }
        QLineEdit, QTextEdit, QTableView {
            background-color: #353535;
            border: 1px solid #555;
            border-radius: 3px;
            padding: 5px;
            color: white;
        }
        QTableView {
            alternate-background-color: #404040;
        }
        QHeaderView::section {
            background-color: #404040;
            padding: 5px;
            border: 1px solid #555;
            color: white;
            font-weight: bold;
        }
        QTabWidget::pane {
            border: 1px solid #555;
            background-color: #404040;
        }
        QTabBar::tab {
            background-color: #353535;
            color: #aaa;
            padding: 8px;
            margin-right: 2px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background-color: #404040;
            color: white;
        }
        QLabel {
            color: white;
        }
        QPushButton {
            padding: 5px;
            border-radius: 3px;
        }
    """)
    
    window = TransferApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()