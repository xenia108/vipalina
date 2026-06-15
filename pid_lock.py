"""PID-lock для гарантии единственного экземпляра бота"""
import os
import signal
import time


PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vipalina.pid')


def acquire_pid_lock():
    """
    Проверяет и убивает предыдущий экземпляр бота если он работает.
    Записывает свой PID в lockfile.
    """
    my_pid = os.getpid()
    
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Проверяем жив ли старый процесс
            os.kill(old_pid, 0)  # signal 0 = проверка существования
            
            if old_pid != my_pid:
                print(f"⚠️ Обнаружен запущенный экземпляр (PID {old_pid}), убиваю...")
                os.kill(old_pid, signal.SIGKILL)
                time.sleep(1)
        except (ProcessLookupError, ValueError, PermissionError, OSError):
            pass  # Процесс мёртв или PID невалиден — продолжаем
    
    with open(PID_FILE, 'w') as f:
        f.write(str(my_pid))
    
    return my_pid


def release_pid_lock():
    """Удаляет PID-файл при корректном завершении"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except OSError:
        pass
