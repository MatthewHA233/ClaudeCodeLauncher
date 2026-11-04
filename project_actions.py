"""项目级操作（三个启动器共用）：复制项目路径并在系统文件管理器中打开。"""
import os
import subprocess
import sys
import time

import pyperclip
from colorama import Fore, Style

import term_input

SUCCESS_PAUSE_SECONDS = 1
EXPECTED_ERRORS = (pyperclip.PyperclipException, OSError, subprocess.SubprocessError)


def open_folder(path):
    """在系统文件管理器中打开目录；目录不存在或无法打开时抛异常。"""
    if not os.path.isdir(path):
        raise FileNotFoundError(f"文件夹不存在: {path}")
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=True)
    else:
        subprocess.run(["xdg-open", path], check=True)


def _attempt(action, path):
    """执行一步操作，成功返回 None，失败返回错误信息。"""
    try:
        action(path)
    except EXPECTED_ERRORS as error:
        return str(error)
    return None


def _print_step(label, error):
    if error:
        print(f"{Fore.RED}❌ {label}失败: {error}{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}✅ {label}成功{Style.RESET_ALL}")


def copy_path_and_open(path, wait_for_key):
    """复制路径并打开文件夹。两步互不影响；有失败时等用户按键，让用户看清原因。"""
    copy_error = _attempt(pyperclip.copy, path)
    open_error = _attempt(open_folder, path)

    term_input.clear_screen()
    print(f"\n{Fore.WHITE}{path}{Style.RESET_ALL}\n")
    _print_step("复制路径", copy_error)
    _print_step("打开文件夹", open_error)

    if copy_error or open_error:
        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        wait_for_key()
    else:
        time.sleep(SUCCESS_PAUSE_SECONDS)
