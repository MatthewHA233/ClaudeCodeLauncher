import os
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import sys
import time
import shutil
from colorama import init, Fore, Back, Style
from git_commit_organizer import GitCommitOrganizer

# 跨平台键盘输入支持
if os.name == 'nt':  # Windows
    import msvcrt
else:  # Unix/Linux/macOS
    import termios
    import tty

init(autoreset=True)


class GrokLauncher:
    def __init__(self):
        self.config_file = Path.home() / ".claude_launcher_config.json"  # 与 Claude/Codex 共享配置
        self.config = self.load_config()
        self.proxy_url = "http://127.0.0.1:7890"
        self.animation_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.frame_index = 0
        self.current_page = 0
        self.paths_per_page = 5
        self.git_organizer = GitCommitOrganizer(self)

    def grok_bin_dir(self):
        return str(Path.home() / ".grok" / "bin")

    def grok_executable(self):
        """优先使用 ~/.grok/bin/grok，找不到再回退到 PATH 里的 grok。"""
        name = "grok.exe" if os.name == "nt" else "grok"
        local = Path.home() / ".grok" / "bin" / name
        if local.exists():
            return str(local)
        found = shutil.which("grok")
        return found or "grok"

    def get_display_width(self, text):
        """计算字符串的实际显示宽度"""
        width = 0
        for char in text:
            char_code = ord(char)
            if char_code > 127:  # 非ASCII字符
                if char in '↑↓←→⚡📋🚀📁🚪📌↩️🔗🤖❌':
                    width += 1
                else:
                    width += 2
            else:
                width += 1
        return width

    def center_text(self, text, width):
        """居中对齐文本，考虑中英文字符宽度"""
        display_width = self.get_display_width(text)
        padding = max(0, width - display_width)
        left_padding = padding // 2
        right_padding = padding - left_padding
        return " " * left_padding + text + " " * right_padding

    def load_config(self):
        """加载配置文件（与 Claude/Codex 启动器共享）"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        if os.name == 'nt':
            default_proxy_path = r"D:\Program Files\Clash Verge\clash-verge.exe"
        else:
            default_proxy_path = "/Applications/Clash Verge.app/Contents/MacOS/clash-verge"

        return {
            "recent_paths": [],
            "all_paths": [],
            "use_proxy": True,  # 默认开启代理
            "clash_path": default_proxy_path
        }

    def save_config(self):
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def check_and_start_clash(self):
        """检查并启动代理软件（仅在开启代理时，跨平台支持）"""
        if not self.config.get("use_proxy", True):
            print(f"{Fore.YELLOW}⚠️  代理功能已关闭{Style.RESET_ALL}")
            return

        if os.name == 'nt':
            clash_path = self.config.get("clash_path", r"D:\Program Files\Clash Verge\clash-verge.exe")
        else:
            clash_path = self.config.get("clash_path", "/Applications/Clash Verge.app/Contents/MacOS/clash-verge")

        if os.path.exists(clash_path):
            try:
                subprocess.Popen([clash_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.name == 'nt':
                    proxy_name = os.path.basename(clash_path).replace(".exe", "")
                else:
                    proxy_name = os.path.basename(clash_path)
                print(f"{Fore.GREEN}✅ {proxy_name} 已启动{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  启动代理软件失败: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️  未找到代理软件: {clash_path}{Style.RESET_ALL}")

    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def animated_print(self, text, color=Fore.WHITE, delay=0.01):
        """动画打印文本"""
        for char in text:
            print(f"{color}{char}{Style.RESET_ALL}", end="", flush=True)
            time.sleep(delay)
        print()

    def print_gradient_text(self, text):
        """打印渐变色文本"""
        colors = [Fore.BLUE, Fore.CYAN, Fore.GREEN, Fore.YELLOW, Fore.MAGENTA]
        color_index = 0
        for char in text:
            print(f"{colors[color_index % len(colors)]}{char}{Style.RESET_ALL}", end="")
            if char not in ' \n':
                color_index += 1
        print()

    def show_welcome_animation(self):
        """显示欢迎动画"""
        self.clear_screen()
        logo = [
            " ██████╗ ██████╗  ██████╗ ██╗  ██╗",
            "██╔════╝ ██╔══██╗██╔═══██╗██║ ██╔╝",
            "██║  ███╗██████╔╝██║   ██║█████╔╝ ",
            "██║   ██║██╔══██╗██║   ██║██╔═██╗ ",
            "╚██████╔╝██║  ██║╚██████╔╝██║  ██╗",
            " ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝"
        ]

        for line in logo:
            self.print_gradient_text(line)

        self.animated_print("\n        Grok Build · AI Coding Assistant ⚡", Fore.CYAN, 0.01)

    def print_menu(self, options, selected_index, title=""):
        """打印菜单"""
        self.clear_screen()

        if title:
            self.print_gradient_text("\n╔" + "═" * 60 + "╗")
            centered_title = "║" + self.center_text(title, 60) + "║"
            self.print_gradient_text(centered_title)
            self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        for i, option in enumerate(options):
            if i == selected_index:
                arrow = self.animation_frames[self.frame_index % len(self.animation_frames)]

                if "PROJECT:" in option and "PATH:" in option:
                    parts = option.split("|")
                    project_name = parts[0].replace("PROJECT:", "")
                    path = parts[1].replace("PATH:", "")

                    print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE}▌{project_name}{Style.RESET_ALL}")
                    print(f"     {Fore.YELLOW}{Style.DIM}{path}{Style.RESET_ALL}")
                elif "PARENT:" in option and "PATH:" in option:
                    parts = option.split("|")
                    parent_name = parts[0].replace("PARENT:", "")
                    path = parts[1].replace("PATH:", "")

                    print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE}📁 {parent_name}{Style.RESET_ALL}")
                    print(f"     {Fore.YELLOW}{Style.DIM}{path}{Style.RESET_ALL}")
                elif "SESSION:" in option and "META:" in option:
                    parts = option.split("|META:")
                    session_name = parts[0].replace("SESSION:", "")
                    meta = parts[1] if len(parts) > 1 else ""
                    print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE} {session_name} {Style.RESET_ALL}")
                    if meta:
                        print(f"     {Fore.YELLOW}{Style.DIM}{meta}{Style.RESET_ALL}")
                else:
                    print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE} {option} {Style.RESET_ALL}")
                self.frame_index += 1
            else:
                if "退出" in option:
                    color = Fore.RED
                    icon = "🚪"
                elif "进入最近会话" in option:
                    color = Fore.CYAN
                    icon = "⚡"
                elif "开始新会话" in option:
                    color = Fore.GREEN
                    icon = "🚀"
                elif "选择历史会话" in option:
                    color = Fore.BLUE
                    icon = "📋"
                elif "返回" in option:
                    color = Fore.YELLOW
                    icon = "↩️"
                elif "整理git提交" in option:
                    color = Fore.MAGENTA
                    icon = "🔗"
                elif "查看已有材料" in option:
                    color = Fore.CYAN
                    icon = "📄"
                elif "重新整理材料" in option:
                    color = Fore.YELLOW
                    icon = "🔄"
                elif "使用 Claude 分析" in option:
                    color = Fore.BLUE
                    icon = "🤖"
                elif "使用 Codex 分析" in option:
                    color = Fore.GREEN
                    icon = "🤖"
                elif "使用 Grok 分析" in option:
                    color = Fore.MAGENTA
                    icon = "🤖"
                elif "切换到" in option:
                    color = Fore.CYAN
                    icon = "🔄"
                elif "删除" in option:
                    color = Fore.RED
                    icon = "🗑️"
                elif "取消" in option:
                    color = Fore.RED
                    icon = "❌"
                else:
                    color = Fore.GREEN
                    icon = "📁"

                if "PROJECT:" in option and "PATH:" in option:
                    parts = option.split("|")
                    project_name = parts[0].replace("PROJECT:", "")
                    path = parts[1].replace("PATH:", "")
                    print(f"  {icon} {Fore.CYAN}{Style.BRIGHT}▌{project_name}{Style.RESET_ALL}")
                    print(f"     {Fore.WHITE}{Style.DIM}{path}{Style.RESET_ALL}")
                elif "PARENT:" in option and "PATH:" in option:
                    parts = option.split("|")
                    parent_name = parts[0].replace("PARENT:", "")
                    path = parts[1].replace("PATH:", "")
                    print(f"  📁 {Fore.MAGENTA}{Style.BRIGHT}{parent_name}{Style.RESET_ALL}")
                    print(f"     {Fore.WHITE}{Style.DIM}{path}{Style.RESET_ALL}")
                elif "SESSION:" in option and "META:" in option:
                    parts = option.split("|META:")
                    session_name = parts[0].replace("SESSION:", "")
                    meta = parts[1] if len(parts) > 1 else ""
                    print(f"  {Fore.CYAN}{Style.BRIGHT}{session_name}{Style.RESET_ALL}")
                    if meta:
                        print(f"     {Fore.WHITE}{Style.DIM}{meta}{Style.RESET_ALL}")
                else:
                    print(f"  {icon} {color}{option}{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}╭────────────────────────────────────────────────────────────╮{Style.RESET_ALL}")
        tip_content = "↑↓ 选择 Enter 确认 C 创建 I 安装 S 设置 Q 切换 ←→ 翻页"
        aligned_tip = self.center_text(tip_content, 60)
        print(f"{Fore.CYAN}│{Fore.WHITE}{aligned_tip}{Fore.CYAN}│{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╰────────────────────────────────────────────────────────────╯{Style.RESET_ALL}")

    def _wait_for_key(self):
        """等待用户按任意键（跨平台支持）"""
        if os.name == 'nt':
            msvcrt.getch()
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def get_key(self):
        """获取按键输入（跨平台支持）"""
        if os.name == 'nt':
            key = msvcrt.getch()
            if key == b'\xe0':
                key = msvcrt.getch()
                if key == b'H':
                    return 'UP'
                elif key == b'P':
                    return 'DOWN'
                elif key == b'K':
                    return 'LEFT'
                elif key == b'M':
                    return 'RIGHT'
            elif key == b'\r':
                return 'ENTER'
            elif key == b'\x1b':
                return 'ESC'
            elif key == b'c' or key == b'C':
                return 'CREATE'
            elif key == b'i' or key == b'I':
                return 'INSTALL'
            elif key == b's' or key == b'S':
                return 'SETTINGS'
            elif key == b'q' or key == b'Q':
                return 'SWITCH'
        else:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)

                if ch == '\x1b':
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':
                            return 'UP'
                        elif ch3 == 'B':
                            return 'DOWN'
                        elif ch3 == 'D':
                            return 'LEFT'
                        elif ch3 == 'C':
                            return 'RIGHT'
                    else:
                        return 'ESC'
                elif ch == '\r' or ch == '\n':
                    return 'ENTER'
                elif ch.lower() == 'c':
                    return 'CREATE'
                elif ch.lower() == 'i':
                    return 'INSTALL'
                elif ch.lower() == 's':
                    return 'SETTINGS'
                elif ch.lower() == 'q':
                    return 'SWITCH'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return None

    def select_from_menu(self, options, title="", is_main_menu=False):
        """从菜单中选择"""
        selected_index = 0

        while True:
            self.print_menu(options, selected_index, title)
            key = self.get_key()

            if key == 'UP':
                selected_index = (selected_index - 1) % len(options)
            elif key == 'DOWN':
                selected_index = (selected_index + 1) % len(options)
            elif key == 'ENTER':
                return selected_index
            elif key == 'ESC':
                return -1
            elif key == 'CREATE' and is_main_menu:
                return -2
            elif key == 'INSTALL' and is_main_menu:
                return -5
            elif key == 'SETTINGS' and is_main_menu:
                return -6
            elif key == 'SWITCH' and is_main_menu:
                return -7
            elif key == 'LEFT' and is_main_menu:
                return -3
            elif key == 'RIGHT' and is_main_menu:
                return -4

    def add_new_path(self):
        """添加新路径"""
        while True:
            self.clear_screen()
            self.print_gradient_text("\n╔" + "═" * 60 + "╗")
            centered_text = "║" + self.center_text("创建新会话", 57) + "║"
            self.print_gradient_text(centered_text)
            self.print_gradient_text("╚" + "═" * 60 + "╝\n")

            options = [
                "手动输入完整路径",
                "从旧项目获取根目录创建新会话",
                "返回主菜单"
            ]

            choice = self.select_from_menu(options, "🎯 选择创建方式")

            if choice == -1 or choice == 2:
                break
            elif choice == 0:
                self.manual_add_path()
                break
            elif choice == 1:
                self.create_from_parent_directory()
                break

    def manual_add_path(self):
        """手动添加路径"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("手动添加路径", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        print(f"{Fore.CYAN}📝 请输入完整路径 {Fore.YELLOW}(例如: /Users/me/Projects/app){Style.RESET_ALL}")
        print(f"{Fore.WHITE}💡 提示: 输入完成后按 Enter 确认，按 ESC 返回上级菜单{Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")

        new_path = self.get_input_with_esc()
        if new_path is None:
            return

        new_path = new_path.strip()
        if not new_path:
            return

        print(f"{Fore.CYAN}⚡ 验证路径...{Style.RESET_ALL}")

        if os.path.exists(new_path):
            if new_path not in self.config["all_paths"]:
                self.config["all_paths"].append(new_path)
                self.update_recent_path(new_path)
                self.save_config()
                self.animated_print(f"\n✅ 路径已成功添加: {new_path}", Fore.GREEN)
            else:
                self.animated_print(f"\n⚠️  路径已存在: {new_path}", Fore.YELLOW)
        else:
            self.animated_print(f"\n❌ 错误: 路径不存在: {new_path}", Fore.RED)

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def get_input_with_esc(self):
        """支持ESC键和中文输入的函数（跨平台支持）"""
        if os.name == 'nt':
            import threading
            import queue

            result_queue = queue.Queue()

            def input_thread():
                try:
                    user_input = input()
                    result_queue.put(('input', user_input))
                except Exception:
                    result_queue.put(('error', None))

            thread = threading.Thread(target=input_thread, daemon=True)
            thread.start()

            while thread.is_alive():
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char == b'\x1b':
                        print("\n取消输入...")
                        return None

                try:
                    event_type, data = result_queue.get(timeout=0.1)
                    if event_type == 'input':
                        return data
                    elif event_type == 'error':
                        return None
                except queue.Empty:
                    continue

            try:
                event_type, data = result_queue.get(timeout=0.1)
                if event_type == 'input':
                    return data
            except queue.Empty:
                pass

            return None
        else:
            try:
                return input()
            except (KeyboardInterrupt, EOFError):
                print("\n取消输入...")
                return None

    def get_parent_directories(self):
        """获取所有会话的父级目录并去重"""
        all_paths = self.get_all_paths()
        parent_dirs = set()

        for path in all_paths:
            parent_dir = os.path.dirname(path)
            if parent_dir and os.path.exists(parent_dir):
                parent_dirs.add(parent_dir)

        recent_parents = []
        for recent_path in self.config["recent_paths"]:
            parent = os.path.dirname(recent_path)
            if parent in parent_dirs and parent not in recent_parents:
                recent_parents.append(parent)

        sorted_parents = []
        for parent in parent_dirs:
            if parent not in recent_parents:
                sorted_parents.append(parent)

        return recent_parents + sorted_parents

    def create_from_parent_directory(self):
        """从父级目录创建新会话"""
        parent_dirs = self.get_parent_directories()

        if not parent_dirs:
            self.clear_screen()
            print(f"{Fore.YELLOW}⚠️  没有找到已存储的会话父目录{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            self._wait_for_key()
            return

        options = []
        for parent_dir in parent_dirs:
            dir_name = os.path.basename(parent_dir) or parent_dir
            options.append(f"PARENT:{dir_name}|PATH:{parent_dir}")
        options.append("返回")

        choice = self.select_from_menu(options, "📁 选择父级目录")

        if choice == -1 or choice == len(options) - 1:
            return

        selected_option = options[choice]
        if "PARENT:" in selected_option and "PATH:" in selected_option:
            parts = selected_option.split("|")
            parent_path = parts[1].replace("PATH:", "")

            self.clear_screen()
            self.print_gradient_text("\n╔" + "═" * 60 + "╗")
            centered_text = "║" + self.center_text("创建新项目", 57) + "║"
            self.print_gradient_text(centered_text)
            self.print_gradient_text("╚" + "═" * 60 + "╝\n")

            print(f"{Fore.CYAN}📁 父目录: {Fore.WHITE}{parent_path}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}📝 请输入新项目名称 {Fore.YELLOW}(支持中文){Style.RESET_ALL}")
            print(f"{Fore.WHITE}💡 提示: 输入完成后按 Enter 确认，按 ESC 取消{Style.RESET_ALL}")
            print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")

            project_name = self.get_input_with_esc()
            if project_name is None or not project_name.strip():
                return

            project_name = project_name.strip()
            new_project_path = os.path.join(parent_path, project_name)

            if os.path.exists(new_project_path):
                print(f"\n{Fore.YELLOW}⚠️  目录已存在: {new_project_path}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}是否直接使用这个目录? (Y/n): {Style.RESET_ALL}", end="")
                confirm = input().strip().lower()
                if confirm != 'y' and confirm != '':
                    return
            else:
                try:
                    os.makedirs(new_project_path, exist_ok=True)
                    print(f"\n{Fore.GREEN}✅ 目录创建成功: {new_project_path}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"\n{Fore.RED}❌ 创建目录失败: {e}{Style.RESET_ALL}")
                    print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
                    self._wait_for_key()
                    return

            if new_project_path not in self.config["all_paths"]:
                self.config["all_paths"].append(new_project_path)
            self.update_recent_path(new_project_path)
            self.save_config()

            print(f"{Fore.GREEN}✨ 项目创建完成，即将打开 Grok...{Style.RESET_ALL}")
            time.sleep(1)
            self.execute_grok_command(new_project_path, f'"{self.grok_executable()}"')

    def proxy_env(self):
        env = {**os.environ}
        if self.config.get("use_proxy", True):
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
                env[key] = self.proxy_url
        grok_bin = self.grok_bin_dir()
        path_sep = ";" if os.name == "nt" else ":"
        env["PATH"] = grok_bin + path_sep + env.get("PATH", "")
        return env

    def install_grok(self):
        """安装/更新 Grok Build CLI"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("安装/更新 Grok Build CLI", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        grok_exe = self.grok_executable()
        already_installed = grok_exe != "grok" or shutil.which("grok")
        env = self.proxy_env()

        if self.config.get("use_proxy", True):
            print(f"{Fore.MAGENTA}🌐 使用代理: {self.proxy_url}{Style.RESET_ALL}")

        try:
            if already_installed:
                print(f"{Fore.YELLOW}🔧 正在更新 Grok Build CLI...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}执行命令: grok update{Style.RESET_ALL}\n")
                result = subprocess.run(
                    [grok_exe, "update"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env
                )
            elif os.name == 'nt':
                print(f"{Fore.YELLOW}🔧 正在安装 Grok Build CLI...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}执行命令: irm https://x.ai/cli/install.ps1 | iex{Style.RESET_ALL}\n")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "irm https://x.ai/cli/install.ps1 | iex"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env
                )
            else:
                print(f"{Fore.YELLOW}🔧 正在安装 Grok Build CLI...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}执行命令: curl -fsSL https://x.ai/cli/install.sh | bash{Style.RESET_ALL}\n")
                curl = "curl -fsSL https://x.ai/cli/install.sh"
                if self.config.get("use_proxy", True):
                    curl = f'curl -fsSL -x {self.proxy_url} https://x.ai/cli/install.sh'
                result = subprocess.run(
                    ["bash", "-c", f"{curl} | bash"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env
                )

            if result.returncode == 0:
                print(f"{Fore.GREEN}✅ Grok Build CLI 安装/更新成功！{Style.RESET_ALL}")
                if result.stdout:
                    print(f"{Fore.WHITE}{result.stdout}{Style.RESET_ALL}")

                version_result = subprocess.run(
                    [self.grok_executable(), "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self.proxy_env()
                )
                if version_result.returncode == 0:
                    print(f"\n{Fore.CYAN}当前版本: {version_result.stdout.strip()}{Style.RESET_ALL}")

                print(f"\n{Fore.CYAN}📋 使用说明:{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}1. 首次运行会打开浏览器登录 grok.com{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}2. 或设置 API Key: export XAI_API_KEY='your-key'{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}3. 在项目目录运行: grok{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ 安装/更新失败{Style.RESET_ALL}")
                if result.stderr:
                    print(f"{Fore.RED}{result.stderr}{Style.RESET_ALL}")
                if result.stdout:
                    print(f"{Fore.WHITE}{result.stdout}{Style.RESET_ALL}")
                print(f"\n{Fore.YELLOW}💡 手动安装:{Style.RESET_ALL}")
                print(f"{Fore.WHITE}   curl -fsSL https://x.ai/cli/install.sh | bash{Style.RESET_ALL}")
                print(f"{Fore.WHITE}   grok update{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}❌ 操作出错: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.YELLOW}💡 手动安装:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}   curl -fsSL https://x.ai/cli/install.sh | bash{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def switch_launcher(self):
        """切换到 Claude / Codex 启动器。选中后返回 True，取消返回 False。"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        catalog = [
            ("Claude Code 启动器", "claude_launcher.py"),
            ("Codex 启动器", "codex_launcher.py"),
        ]
        options = []
        files = []
        for name, filename in catalog:
            path = os.path.join(current_dir, filename)
            if os.path.exists(path):
                options.append(f"切换到 {name}")
                files.append(path)

        if not options:
            self.clear_screen()
            print(f"{Fore.RED}❌ 未找到可切换的启动器{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            self._wait_for_key()
            return False

        options.append("返回")
        choice = self.select_from_menu(options, "🔄 切换启动器")
        if choice == -1 or choice == len(options) - 1:
            return False

        self.clear_screen()
        print(f"{Fore.CYAN}🔄 正在切换到 {options[choice].replace('切换到 ', '')}...{Style.RESET_ALL}")
        time.sleep(0.5)
        subprocess.run([sys.executable, files[choice]])
        return True

    def show_settings(self):
        """显示设置菜单"""
        while True:
            self.clear_screen()
            self.print_gradient_text("\n╔" + "═" * 60 + "╗")
            self.print_gradient_text("║" + "设置".center(57) + "║")
            self.print_gradient_text("╚" + "═" * 60 + "╝\n")

            proxy_status = "开启" if self.config.get("use_proxy", True) else "关闭"
            proxy_color = Fore.GREEN if self.config.get("use_proxy", True) else Fore.RED

            clash_path = self.config.get("clash_path", r"D:\Program Files\Clash Verge\clash-verge.exe")
            proxy_name = os.path.basename(clash_path).replace(".exe", "")

            options = [
                f"代理功能: {proxy_color}{proxy_status}{Style.RESET_ALL}",
                f"代理软件: {Fore.CYAN}{proxy_name}{Style.RESET_ALL}",
                "返回主菜单"
            ]

            choice = self.select_from_menu(options, "⚙️ 设置")

            if choice == -1 or choice == 2:
                break
            elif choice == 0:
                self.config["use_proxy"] = not self.config.get("use_proxy", True)
                self.save_config()
                new_status = "开启" if self.config["use_proxy"] else "关闭"
                new_color = Fore.GREEN if self.config["use_proxy"] else Fore.RED
                print(f"\n{Fore.CYAN}代理功能已切换为: {new_color}{new_status}{Style.RESET_ALL}")
                time.sleep(1)
            elif choice == 1:
                self.set_proxy_path()

    def set_proxy_path(self):
        """设置代理软件路径（跨平台支持）"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        self.print_gradient_text("║" + "设置代理软件路径".center(55) + "║")
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        if os.name == 'nt':
            current_path = self.config.get("clash_path", r"D:\Program Files\Clash Verge\clash-verge.exe")
            example_path = "D:\\Program Files\\v2rayN\\v2rayN.exe"
        else:
            current_path = self.config.get("clash_path", "/Applications/Clash Verge.app/Contents/MacOS/clash-verge")
            example_path = "/Applications/Surge.app/Contents/MacOS/Surge"

        print(f"{Fore.YELLOW}当前路径: {Fore.WHITE}{current_path}{Style.RESET_ALL}\n")
        print(f"{Fore.CYAN}📝 请输入代理软件完整路径{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}(例如: {example_path}){Style.RESET_ALL}")
        print(f"{Fore.WHITE}(直接按Enter保持当前路径不变){Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
        new_path = input().strip()

        if not new_path:
            print(f"\n{Fore.CYAN}路径保持不变{Style.RESET_ALL}")
            time.sleep(1)
            return

        print(f"{Fore.CYAN}⚡ 验证路径...{Style.RESET_ALL}")

        if os.path.exists(new_path):
            if os.name == 'nt' and not new_path.lower().endswith('.exe'):
                print(f"\n{Fore.RED}❌ 错误: Windows下请选择.exe文件{Style.RESET_ALL}")
            else:
                self.config["clash_path"] = new_path
                self.save_config()
                if os.name == 'nt':
                    proxy_name = os.path.basename(new_path).replace(".exe", "")
                else:
                    proxy_name = os.path.basename(new_path)
                print(f"\n{Fore.GREEN}✅ 代理软件路径已更新为: {proxy_name}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}{new_path}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}❌ 错误: 文件不存在{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def update_recent_path(self, path):
        """更新最近使用的路径"""
        if path in self.config["recent_paths"]:
            self.config["recent_paths"].remove(path)
        self.config["recent_paths"].insert(0, path)
        self.config["recent_paths"] = self.config["recent_paths"][:5]

    def execute_grok_command(self, path, command):
        """执行 Grok 命令（跨平台，默认走 7890 代理）"""
        self.clear_screen()
        print(f"{Fore.CYAN}🚀 启动 Grok Build...{Style.RESET_ALL}")

        commands = []
        grok_bin = self.grok_bin_dir()

        if os.name == 'nt':
            drive = path[0] + ":"
            commands.append(drive)
            commands.append(f'cd "{path}"')
            commands.append(f'set PATH={grok_bin};%PATH%')
            if self.config.get("use_proxy", True):
                commands.extend([
                    f'set https_proxy={self.proxy_url}',
                    f'set http_proxy={self.proxy_url}',
                    f'set HTTPS_PROXY={self.proxy_url}',
                    f'set HTTP_PROXY={self.proxy_url}',
                    f'set ALL_PROXY={self.proxy_url}',
                ])
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}{self.proxy_url}{Style.RESET_ALL}"
            else:
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}已关闭{Style.RESET_ALL}"
        else:
            commands.append(f'cd "{path}"')
            commands.append(f'export PATH="{grok_bin}:$PATH"')
            if self.config.get("use_proxy", True):
                commands.extend([
                    f'export https_proxy={self.proxy_url}',
                    f'export http_proxy={self.proxy_url}',
                    f'export HTTPS_PROXY={self.proxy_url}',
                    f'export HTTP_PROXY={self.proxy_url}',
                    f'export ALL_PROXY={self.proxy_url}',
                    f'export all_proxy={self.proxy_url}',
                ])
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}{self.proxy_url}{Style.RESET_ALL}"
            else:
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}已关闭{Style.RESET_ALL}"

        commands.append(command)

        print(f"\n{Fore.GREEN}📍 工作目录: {Fore.WHITE}{path}{Style.RESET_ALL}")
        print(f"{Fore.BLUE}🔧 执行命令: {Fore.WHITE}{command}{Style.RESET_ALL}")
        print(f"{proxy_info}\n")

        cmd_string = " && ".join(commands)
        subprocess.run(cmd_string, shell=True)

    def format_relative_time(self, iso_str):
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc if dt.tzinfo else None)
            if dt.tzinfo and now.tzinfo is None:
                now = datetime.now(dt.tzinfo)
            secs = int((now - dt).total_seconds())
            if secs < 60:
                return "刚刚"
            if secs < 3600:
                return f"{secs // 60}分钟前"
            if secs < 86400:
                return f"{secs // 3600}小时前"
            if secs < 86400 * 7:
                return f"{secs // 86400}天前"
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return str(iso_str)[:10]

    def get_grok_sessions(self, path):
        """读取 ~/.grok/sessions/<urlencoded-cwd>/ 下的会话摘要。"""
        grok_home = os.environ.get("GROK_HOME") or str(Path.home() / ".grok")
        encoded = quote(os.path.abspath(path), safe="")
        session_root = Path(grok_home) / "sessions" / encoded
        if not session_root.exists():
            return []

        sessions = []
        for child in session_root.iterdir():
            if not child.is_dir():
                continue
            summary_file = child / "summary.json"
            if not summary_file.exists():
                continue
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            title = data.get("generated_title") or data.get("session_summary") or child.name
            sessions.append({
                "id": (data.get("info") or {}).get("id") or child.name,
                "title": title,
                "updated_at": data.get("last_active_at") or data.get("updated_at") or "",
                "model": data.get("current_model_id") or "",
            })
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions

    def show_history_sessions(self, path):
        """列出当前项目的 Grok 历史会话并 resume。"""
        sessions = self.get_grok_sessions(path)
        grok = f'"{self.grok_executable()}"'
        if not sessions:
            self.clear_screen()
            print(f"\n{Fore.YELLOW}⚠️  该项目暂无 Grok 会话记录{Style.RESET_ALL}")
            print(f"{Fore.WHITE}💡 将打开 Grok 欢迎页，可在其中选择或新建会话{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            self._wait_for_key()
            self.execute_grok_command(path, grok)
            return

        options = []
        for session in sessions[:30]:
            title = session["title"]
            if len(title) > 46:
                title = title[:45] + "…"
            meta_parts = [self.format_relative_time(session["updated_at"])]
            if session["model"]:
                meta_parts.append(session["model"])
            options.append(f"SESSION:{title}|META:{' · '.join(meta_parts)}")
        options.append("返回")

        project_name = os.path.basename(path) or path
        choice = self.select_from_menu(options, f"📋 {project_name} 的历史会话")
        if choice == -1 or choice == len(options) - 1:
            return

        session = sessions[choice]
        self.execute_grok_command(path, f'{grok} --resume {session["id"]}')

    def handle_path_selection(self, path):
        """处理路径选择后的操作"""
        grok = f'"{self.grok_executable()}"'
        while True:
            latest = None
            sessions = self.get_grok_sessions(path)
            if sessions:
                latest = sessions[0]
                title = latest["title"]
                if len(title) > 42:
                    title = title[:41] + "…"
                recent_option = (
                    f"SESSION:⚡ 进入最近会话 (grok --resume)|META:"
                    f"{title} · {self.format_relative_time(latest['updated_at'])}"
                )
            else:
                recent_option = "进入最近会话 (grok --resume)"

            options = [
                recent_option,
                "开始新会话 (grok)",
                "选择历史会话",
                "整理git提交作为学习材料",
                "删除此项目记录",
                "返回主菜单"
            ]

            project_name = os.path.basename(path) or path
            title = f"📂 {project_name}"
            choice = self.select_from_menu(options, title)

            if choice == -1 or choice == 5:
                break
            elif choice == 0:
                self.execute_grok_command(path, f'{grok} --resume')
            elif choice == 1:
                self.execute_grok_command(path, grok)
            elif choice == 2:
                self.show_history_sessions(path)
            elif choice == 3:
                self.git_organizer.run_commit_organizer(path)
            elif choice == 4:
                if self.delete_project_record(path):
                    break

    def delete_project_record(self, path):
        """删除项目记录"""
        project_name = os.path.basename(path) or path
        options = ["确认删除", "取消"]
        choice = self.select_from_menu(options, f"🗑️ 确认删除项目「{project_name}」?")

        if choice == 0:
            if path in self.config["all_paths"]:
                self.config["all_paths"].remove(path)
            if path in self.config["recent_paths"]:
                self.config["recent_paths"].remove(path)
            self.save_config()

            self.clear_screen()
            print(f"\n{Fore.GREEN}✅ 项目「{project_name}」已从记录中删除{Style.RESET_ALL}")
            print(f"{Fore.WHITE}💡 注意: 这只删除了记录，项目文件仍保留在原位置{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            self._wait_for_key()
            return True
        return False

    def get_all_paths(self):
        """获取所有路径，最近使用的在前"""
        all_paths = self.config["recent_paths"][:]
        for path in self.config["all_paths"]:
            if path not in all_paths:
                all_paths.append(path)
        return all_paths

    def main_menu(self):
        """主菜单"""
        self.show_welcome_animation()

        while True:
            all_paths = self.get_all_paths()
            total_pages = (len(all_paths) - 1) // self.paths_per_page + 1 if all_paths else 1

            if self.current_page >= total_pages:
                self.current_page = max(0, total_pages - 1)

            options = []
            start_idx = self.current_page * self.paths_per_page
            end_idx = min(start_idx + self.paths_per_page, len(all_paths))

            for i in range(start_idx, end_idx):
                path = all_paths[i]
                project_name = os.path.basename(path) or "根目录"
                options.append(f"PROJECT:{project_name}|PATH:{path}")

            options.append("退出")

            if total_pages > 1:
                title = f"🤖 Grok 启动器 - 第 {self.current_page + 1}/{total_pages} 页"
            else:
                title = "🤖 Grok 启动器"

            choice = self.select_from_menu(options, title, is_main_menu=True)

            if choice == -1 or choice == len(options) - 1:
                break
            elif choice == -2:
                self.add_new_path()
            elif choice == -3:
                if self.current_page > 0:
                    self.current_page -= 1
            elif choice == -4:
                if self.current_page < total_pages - 1:
                    self.current_page += 1
            elif choice == -5:
                self.install_grok()
            elif choice == -6:
                self.show_settings()
            elif choice == -7:
                if self.switch_launcher():
                    break
            else:
                selected_option = options[choice]
                if "PROJECT:" in selected_option and "PATH:" in selected_option:
                    parts = selected_option.split("|")
                    path = parts[1].replace("PATH:", "")
                    self.update_recent_path(path)
                    self.save_config()
                    self.handle_path_selection(path)

    def detect_proxy_apps_macos(self):
        """自动检测 macOS 下已安装的代理软件"""
        proxy_apps = {
            "Clash Verge": "/Applications/Clash Verge.app/Contents/MacOS/clash-verge",
            "ClashX": "/Applications/ClashX.app/Contents/MacOS/ClashX",
            "ClashX Pro": "/Applications/ClashX Pro.app/Contents/MacOS/ClashX Pro",
            "Surge": "/Applications/Surge.app/Contents/MacOS/Surge",
            "Surge 5": "/Applications/Surge 5.app/Contents/MacOS/Surge 5",
            "V2rayU": "/Applications/V2rayU.app/Contents/MacOS/V2rayU",
            "Shadowrocket": "/Applications/Shadowrocket.app/Contents/MacOS/Shadowrocket",
            "Qv2ray": "/Applications/Qv2ray.app/Contents/MacOS/qv2ray",
            "NekoRay": "/Applications/nekoray.app/Contents/MacOS/nekoray",
        }

        found_apps = []
        for name, path in proxy_apps.items():
            if os.path.exists(path):
                found_apps.append((name, path))
        return found_apps

    def first_time_setup(self):
        """首次运行设置引导（跨平台支持，macOS 自动检测代理软件）"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        self.print_gradient_text("║" + "欢迎使用 Grok 启动器".center(54) + "║")
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        print(f"{Fore.YELLOW}🎉 首次运行，让我们先进行一些基础设置！{Style.RESET_ALL}\n")

        proxy_path = None

        if os.name == 'nt':
            default_path = r"D:\Program Files\Clash Verge\clash-verge.exe"
            proxy_examples = "Clash、v2rayN、Shadowsocks"

            print(f"{Fore.CYAN}📡 代理软件设置{Style.RESET_ALL}")
            print(f"{Fore.WHITE}请输入你的代理软件路径（支持 {proxy_examples} 等）{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}默认: {default_path}{Style.RESET_ALL}")
            print(f"{Fore.WHITE}(直接按Enter使用默认路径){Style.RESET_ALL}")
            print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")

            proxy_path = input().strip()
            if not proxy_path:
                proxy_path = default_path
        else:
            print(f"{Fore.CYAN}🔍 正在检测已安装的代理软件...{Style.RESET_ALL}\n")
            found_apps = self.detect_proxy_apps_macos()

            if len(found_apps) == 0:
                print(f"{Fore.YELLOW}⚠️  未检测到常见代理软件{Style.RESET_ALL}")
                print(f"{Fore.WHITE}请手动输入代理软件路径，或直接按 Enter 跳过{Style.RESET_ALL}")
                print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
                proxy_path = input().strip()
                if not proxy_path:
                    proxy_path = "/Applications/Clash Verge.app/Contents/MacOS/clash-verge"
            elif len(found_apps) == 1:
                name, path = found_apps[0]
                print(f"{Fore.GREEN}✅ 检测到代理软件: {name}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}   路径: {path}{Style.RESET_ALL}")
                proxy_path = path
                time.sleep(1)
            else:
                print(f"{Fore.GREEN}✅ 检测到 {len(found_apps)} 个代理软件:{Style.RESET_ALL}\n")
                options = [f"{name}" for name, _ in found_apps]
                options.append("手动输入路径")

                choice = self.select_from_menu(options, "🌐 选择代理软件")

                if choice == -1 or choice == len(options) - 1:
                    print(f"\n{Fore.CYAN}请输入代理软件完整路径:{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
                    proxy_path = input().strip()
                    if not proxy_path:
                        proxy_path = found_apps[0][1]
                else:
                    proxy_path = found_apps[choice][1]

        if os.name == 'nt':
            path_valid = os.path.exists(proxy_path) and proxy_path.lower().endswith('.exe')
        else:
            path_valid = os.path.exists(proxy_path)

        if path_valid:
            self.config["clash_path"] = proxy_path
            if os.name == 'nt':
                proxy_name = os.path.basename(proxy_path).replace(".exe", "")
            else:
                proxy_name = os.path.basename(proxy_path)
            print(f"\n{Fore.GREEN}✅ 代理软件设置成功: {proxy_name}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}⚠️  路径无效，将在需要时手动配置{Style.RESET_ALL}")
            self.config["clash_path"] = proxy_path

        print(f"\n{Fore.CYAN}🌐 是否默认开启代理功能？{Style.RESET_ALL}")
        print(f"{Fore.WHITE}y/Y = 开启 (推荐)  n/N = 关闭{Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")

        proxy_choice = input().strip().lower()
        self.config["use_proxy"] = proxy_choice not in ['n', 'no']

        status = "开启" if self.config["use_proxy"] else "关闭"
        print(f"\n{Fore.GREEN}✅ 代理功能: {status}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}   代理地址: {self.proxy_url}{Style.RESET_ALL}")

        self.save_config()

        print(f"\n{Fore.CYAN}🎯 设置完成！现在可以开始使用了{Style.RESET_ALL}")
        print(f"{Fore.WHITE}提示: 随时可按 S 键进入设置修改配置{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def run(self):
        """运行启动器"""
        try:
            if os.name == 'nt':
                os.system("title Grok Launcher")

            clash_path = self.config.get("clash_path")
            if not clash_path or not os.path.exists(clash_path):
                self.first_time_setup()

            self.check_and_start_clash()

            try:
                from session_api_autostart import ensure_running
                ensure_running()
            except Exception:
                pass

            self.main_menu()

            self.clear_screen()
            print(f"\n{Fore.CYAN}👋 感谢使用 Grok 启动器！{Style.RESET_ALL}")
            print(f"{Fore.GREEN}   祝您编码愉快！✨{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self.clear_screen()
            print(f"\n{Fore.YELLOW}⚠️  程序已中断{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ 发生错误: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键退出...{Style.RESET_ALL}")
            self._wait_for_key()


if __name__ == "__main__":
    launcher = GrokLauncher()
    launcher.run()
