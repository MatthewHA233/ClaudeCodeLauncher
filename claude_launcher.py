import os
import json
import subprocess
import psutil
from datetime import datetime
from pathlib import Path
import sys
import time
import random
from colorama import init, Fore, Back, Style
from git_commit_organizer import GitCommitOrganizer
from conversation_viewer import ConversationViewer

# 跨平台键盘输入支持
if os.name == 'nt':  # Windows
    import msvcrt
else:  # Unix/Linux/macOS
    import termios
    import tty

init(autoreset=True)

class ClaudeLauncher:
    def __init__(self):
        self.config_file = Path.home() / ".claude_launcher_config.json"
        self.config = self.load_config()
        self.proxy_url = "http://127.0.0.1:7890"
        self.animation_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.frame_index = 0
        self.current_page = 0
        self.paths_per_page = 5
        self.git_organizer = GitCommitOrganizer(self)
        self.conversation_viewer = ConversationViewer(self)
    
    def get_display_width(self, text):
        """计算字符串的实际显示宽度"""
        width = 0
        for char in text:
            char_code = ord(char)
            if char_code > 127:  # 非ASCII字符
                # 特殊处理箭头符号，它们通常显示为1个字符宽度
                if char in '↑↓←→⚡📋🚀📁🚪':
                    width += 1
                else:  # 中文字符等宽字符
                    width += 2
            else:  # ASCII字符
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
        """加载配置文件"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        # 根据操作系统设置默认代理路径
        if os.name == 'nt':  # Windows
            default_proxy_path = r"D:\Program Files\Clash Verge\clash-verge.exe"
        else:  # macOS/Linux
            # macOS 常见代理软件路径（Clash Verge 优先）
            default_proxy_path = "/Applications/Clash Verge.app/Contents/MacOS/clash-verge"

        return {
            "recent_paths": [],
            "all_paths": [],
            "use_proxy": True,  # 默认开启代理
            "clash_path": default_proxy_path,
            "resume_mode": "cli"  # 历史会话选择模式: "cli" 或 "web"
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

        if os.name == 'nt':  # Windows
            clash_path = self.config.get("clash_path", r"D:\Program Files\Clash Verge\clash-verge.exe")
        else:  # macOS/Linux
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
    
    def show_loading(self, text, duration=1.0):
        """显示加载动画"""
        start_time = time.time()
        while time.time() - start_time < duration:
            for frame in self.animation_frames:
                print(f"\r{Fore.CYAN}{frame} {text}{Style.RESET_ALL}", end="", flush=True)
                time.sleep(0.1)
                if time.time() - start_time >= duration:
                    break
        print("\r" + " " * (len(text) + 3) + "\r", end="")
    
    def show_welcome_animation(self):
        """显示欢迎动画"""
        self.clear_screen()
        logo = [
            "  ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗",
            " ██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝",
            " ██║     ██║     ███████║██║   ██║██║  ██║█████╗  ",
            " ██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝  ",
            " ╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗",
            "  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝"
        ]
        
        for line in logo:
            self.print_gradient_text(line)
        
        self.animated_print("\n         Code with Claude, Build with Speed ⚡", Fore.CYAN, 0.01)
    
    def print_menu(self, options, selected_index, title=""):
        """打印菜单"""
        self.clear_screen()
        
        # 打印标题
        if title:
            self.print_gradient_text("\n╔" + "═" * 60 + "╗")
            centered_title = "║" + self.center_text(title, 60) + "║"
            self.print_gradient_text(centered_title)
            self.print_gradient_text("╚" + "═" * 60 + "╝\n")
        
        # 打印选项
        for i, option in enumerate(options):
            if i == selected_index:
                # 选中项带动画箭头
                arrow = self.animation_frames[self.frame_index % len(self.animation_frames)]
                
                # 特殊处理选中的项目路径显示
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
                else:
                    print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE} {option} {Style.RESET_ALL}")
                self.frame_index += 1
            else:
                # 根据选项类型显示不同颜色
                if "退出" in option:
                    color = Fore.RED
                    icon = "🚪"
                elif "claude -c" in option:
                    color = Fore.CYAN
                    icon = "⚡"
                elif "claude --resume" in option or "Web图形化" in option:
                    color = Fore.BLUE
                    icon = "📋"
                elif "(claude)" in option:
                    color = Fore.GREEN
                    icon = "🚀"
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
                elif "查看对话历史记录" in option:
                    color = Fore.CYAN
                    icon = "📜"
                elif "取消" in option:
                    color = Fore.RED
                    icon = "❌"
                elif "删除" in option:
                    color = Fore.RED
                    icon = "🗑️"
                else:
                    color = Fore.GREEN
                    icon = "📁"
                
                # 特殊处理项目路径显示
                if "PROJECT:" in option and "PATH:" in option:
                    # 解析项目名和路径
                    parts = option.split("|")
                    project_name = parts[0].replace("PROJECT:", "")
                    path = parts[1].replace("PATH:", "")
                    
                    # 项目名使用大字体效果和醒目颜色
                    print(f"  {icon} {Fore.CYAN}{Style.BRIGHT}▌{project_name}{Style.RESET_ALL}")
                    print(f"     {Fore.WHITE}{Style.DIM}{path}{Style.RESET_ALL}")
                elif "PARENT:" in option and "PATH:" in option:
                    # 解析父级目录名和路径
                    parts = option.split("|")
                    parent_name = parts[0].replace("PARENT:", "")
                    path = parts[1].replace("PATH:", "")
                    
                    # 父级目录显示
                    print(f"  📁 {Fore.MAGENTA}{Style.BRIGHT}{parent_name}{Style.RESET_ALL}")
                    print(f"     {Fore.WHITE}{Style.DIM}{path}{Style.RESET_ALL}")
                else:
                    print(f"  {icon} {color}{option}{Style.RESET_ALL}")
        
        # 底部提示
        print(f"\n{Fore.CYAN}╭────────────────────────────────────────────────────────────╮{Style.RESET_ALL}")
        tip_content = "↑↓选择 Enter确认 C创建 I安装 U更新 S设置 W服务 Q切换 ←→翻页"
        aligned_tip = self.center_text(tip_content, 60)
        print(f"{Fore.CYAN}│{Fore.WHITE}{aligned_tip}{Fore.CYAN}│{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╰────────────────────────────────────────────────────────────╯{Style.RESET_ALL}")
    
    def _wait_for_key(self):
        """等待用户按任意键（跨平台支持）"""
        if os.name == 'nt':  # Windows
            msvcrt.getch()
        else:  # Unix/Linux/macOS
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def get_key(self):
        """获取按键输入（跨平台支持）"""
        if os.name == 'nt':  # Windows
            key = msvcrt.getch()
            if key == b'\xe0':  # 特殊键前缀
                key = msvcrt.getch()
                if key == b'H':  # 上箭头
                    return 'UP'
                elif key == b'P':  # 下箭头
                    return 'DOWN'
                elif key == b'K':  # 左箭头
                    return 'LEFT'
                elif key == b'M':  # 右箭头
                    return 'RIGHT'
            elif key == b'\r':  # Enter
                return 'ENTER'
            elif key == b'\x1b':  # ESC
                return 'ESC'
            elif key == b'c' or key == b'C':
                return 'CREATE'
            elif key == b'i' or key == b'I':
                return 'INSTALL'
            elif key == b'u' or key == b'U':
                return 'UPDATE'
            elif key == b's' or key == b'S':
                return 'SETTINGS'
            elif key == b'q' or key == b'Q':
                return 'SWITCH'
            elif key == b'w' or key == b'W':
                return 'SERVER'
        else:  # Unix/Linux/macOS
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)

                # 处理ESC序列（方向键等）
                if ch == '\x1b':
                    # 读取下一个字符
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':  # 上箭头
                            return 'UP'
                        elif ch3 == 'B':  # 下箭头
                            return 'DOWN'
                        elif ch3 == 'D':  # 左箭头
                            return 'LEFT'
                        elif ch3 == 'C':  # 右箭头
                            return 'RIGHT'
                    else:
                        return 'ESC'
                elif ch == '\r' or ch == '\n':  # Enter
                    return 'ENTER'
                elif ch.lower() == 'c':
                    return 'CREATE'
                elif ch.lower() == 'i':
                    return 'INSTALL'
                elif ch.lower() == 'u':
                    return 'UPDATE'
                elif ch.lower() == 's':
                    return 'SETTINGS'
                elif ch.lower() == 'q':
                    return 'SWITCH'
                elif ch.lower() == 'w':
                    return 'SERVER'
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
                return -2  # 特殊返回值表示创建
            elif key == 'INSTALL' and is_main_menu:
                return -5  # 安装Claude Code
            elif key == 'UPDATE' and is_main_menu:
                return -6  # 更新Claude Code
            elif key == 'SETTINGS' and is_main_menu:
                return -7  # 设置
            elif key == 'SWITCH' and is_main_menu:
                return -8  # 切换启动器
            elif key == 'SERVER' and is_main_menu:
                return -9  # 启动服务端
            elif key == 'LEFT' and is_main_menu:
                return -3  # 上一页
            elif key == 'RIGHT' and is_main_menu:
                return -4  # 下一页
    
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
            
            if choice == -1 or choice == 2:  # ESC或返回
                break
            elif choice == 0:  # 手动输入路径
                self.manual_add_path()
                break
            elif choice == 1:  # 从旧项目根目录创建
                self.create_from_parent_directory()
                break
    
    def manual_add_path(self):
        """手动添加路径"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("手动添加路径", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")
        
        print(f"{Fore.CYAN}📝 请输入完整路径 {Fore.YELLOW}(例如: D:\\my_pro\\GitHub\\project){Style.RESET_ALL}")
        print(f"{Fore.WHITE}💡 提示: 输入完成后按 Enter 确认，按 ESC 返回上级菜单{Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
        
        # 使用特殊输入方式支持ESC
        new_path = self.get_input_with_esc()
        if new_path is None:  # 用户按了ESC
            return
        
        new_path = new_path.strip()
        if not new_path:
            return
        
        # 验证路径
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
        if os.name == 'nt':  # Windows 版本
            import threading
            import queue

            result_queue = queue.Queue()

            def input_thread():
                try:
                    user_input = input()
                    result_queue.put(('input', user_input))
                except:
                    result_queue.put(('error', None))

            # 启动输入线程
            thread = threading.Thread(target=input_thread, daemon=True)
            thread.start()

            # 检查ESC键
            while thread.is_alive():
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char == b'\x1b':  # ESC键
                        print("\n取消输入...")
                        return None

                # 检查是否有输入完成
                try:
                    event_type, data = result_queue.get(timeout=0.1)
                    if event_type == 'input':
                        return data
                    elif event_type == 'error':
                        return None
                except queue.Empty:
                    continue

            # 如果线程结束但没有结果，返回None
            try:
                event_type, data = result_queue.get(timeout=0.1)
                if event_type == 'input':
                    return data
            except queue.Empty:
                pass

            return None
        else:  # Unix/Linux/macOS 版本（简化版，直接使用标准 input）
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
        
        # 按访问时间排序（最近使用的在前）
        sorted_parents = []
        recent_parents = []
        
        # 先添加最近使用的路径的父目录
        for recent_path in self.config["recent_paths"]:
            parent = os.path.dirname(recent_path)
            if parent in parent_dirs and parent not in recent_parents:
                recent_parents.append(parent)
        
        # 再添加其他父目录
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
            msvcrt.getch()
            return
        
        # 构建选项列表
        options = []
        for parent_dir in parent_dirs:
            dir_name = os.path.basename(parent_dir) or parent_dir
            options.append(f"PARENT:{dir_name}|PATH:{parent_dir}")
        options.append("返回")
        
        # 显示选择菜单
        choice = self.select_from_menu(options, "📁 选择父级目录")
        
        if choice == -1 or choice == len(options) - 1:  # ESC或返回
            return
        
        # 获取选中的父目录
        selected_option = options[choice]
        if "PARENT:" in selected_option and "PATH:" in selected_option:
            parts = selected_option.split("|")
            parent_path = parts[1].replace("PATH:", "")
            
            # 让用户输入新项目名称
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
            
            # 检查目录是否已存在
            if os.path.exists(new_project_path):
                print(f"\n{Fore.YELLOW}⚠️  目录已存在: {new_project_path}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}是否直接使用这个目录? (Y/n): {Style.RESET_ALL}", end="")
                confirm = input().strip().lower()
                if confirm != 'y' and confirm != '':
                    return
            else:
                # 创建新目录
                try:
                    os.makedirs(new_project_path, exist_ok=True)
                    print(f"\n{Fore.GREEN}✅ 目录创建成功: {new_project_path}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"\n{Fore.RED}❌ 创建目录失败: {e}{Style.RESET_ALL}")
                    print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
                    msvcrt.getch()
                    return
            
            # 保存路径到配置
            if new_project_path not in self.config["all_paths"]:
                self.config["all_paths"].append(new_project_path)
            self.update_recent_path(new_project_path)
            self.save_config()
            
            print(f"{Fore.GREEN}✨ 项目创建完成，即将打开 Claude Code...{Style.RESET_ALL}")
            time.sleep(1)
            
            # 直接启动 Claude Code
            self.execute_claude_command(new_project_path, "claude")
    
    def install_claude_code(self):
        """安装Claude Code"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("安装 Claude Code", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        print(f"{Fore.YELLOW}🔧 正在安装 Claude Code...{Style.RESET_ALL}")

        try:
            if os.name == 'nt':  # Windows
                print(f"{Fore.CYAN}执行命令: npm install -g @anthropic-ai/claude-code@latest{Style.RESET_ALL}\n")
                result = subprocess.run(
                    ["npm", "install", "-g", "@anthropic-ai/claude-code@latest"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
            else:  # macOS/Linux
                print(f"{Fore.CYAN}执行命令: curl -fsSL https://claude.ai/install.sh | bash{Style.RESET_ALL}\n")
                result = subprocess.run(
                    ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"],
                    capture_output=True,
                    text=True
                )

            if result.returncode == 0:
                print(f"{Fore.GREEN}✅ Claude Code 安装成功！{Style.RESET_ALL}")
                if result.stdout:
                    print(f"{Fore.WHITE}{result.stdout}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ 安装失败{Style.RESET_ALL}")
                if result.stderr:
                    print(f"{Fore.RED}{result.stderr}{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}❌ 安装出错: {e}{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()
    
    def update_claude_code(self):
        """更新Claude Code"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("更新 Claude Code", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        if os.name != 'nt':  # macOS/Linux
            print(f"{Fore.GREEN}✅ 原生安装已自动后台更新，无需手动操作！{Style.RESET_ALL}")
            # 显示当前版本
            try:
                version_result = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True,
                    text=True
                )
                if version_result.returncode == 0:
                    print(f"\n{Fore.CYAN}当前版本: {version_result.stdout.strip()}{Style.RESET_ALL}")
            except Exception:
                pass
        else:  # Windows
            print(f"{Fore.YELLOW}🔄 正在更新 Claude Code...{Style.RESET_ALL}")
            print(f"{Fore.CYAN}执行命令: npm install -g @anthropic-ai/claude-code@latest{Style.RESET_ALL}\n")
            try:
                result = subprocess.run(
                    ["npm", "install", "-g", "@anthropic-ai/claude-code@latest"],
                    capture_output=True,
                    text=True,
                    shell=True
                )

                if result.returncode == 0:
                    print(f"{Fore.GREEN}✅ Claude Code 更新成功！{Style.RESET_ALL}")
                    if result.stdout:
                        print(f"{Fore.WHITE}{result.stdout}{Style.RESET_ALL}")

                    version_result = subprocess.run(
                        ["claude", "--version"],
                        capture_output=True,
                        text=True,
                        shell=True
                    )
                    if version_result.returncode == 0:
                        print(f"\n{Fore.CYAN}当前版本: {version_result.stdout.strip()}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 更新失败{Style.RESET_ALL}")
                    if result.stderr:
                        print(f"{Fore.RED}{result.stderr}{Style.RESET_ALL}")

            except Exception as e:
                print(f"{Fore.RED}❌ 更新出错: {e}{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()
    
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

            resume_mode = self.config.get("resume_mode", "cli")
            resume_mode_text = "Web图形化" if resume_mode == "web" else "命令行(CLI)"
            resume_mode_color = Fore.CYAN if resume_mode == "web" else Fore.YELLOW

            options = [
                f"代理功能: {proxy_color}{proxy_status}{Style.RESET_ALL}",
                f"代理软件: {Fore.CYAN}{proxy_name}{Style.RESET_ALL}",
                f"历史会话选择模式: {resume_mode_color}{resume_mode_text}{Style.RESET_ALL}",
                "返回主菜单"
            ]

            choice = self.select_from_menu(options, "⚙️ 设置")

            if choice == -1 or choice == 3:  # ESC或返回
                break
            elif choice == 0:  # 切换代理设置
                self.config["use_proxy"] = not self.config.get("use_proxy", True)
                self.save_config()
                new_status = "开启" if self.config["use_proxy"] else "关闭"
                new_color = Fore.GREEN if self.config["use_proxy"] else Fore.RED
                print(f"\n{Fore.CYAN}代理功能已切换为: {new_color}{new_status}{Style.RESET_ALL}")
                time.sleep(1)
            elif choice == 1:  # 设置代理软件路径
                self.set_proxy_path()
            elif choice == 2:  # 切换历史会话选择模式
                self.config["resume_mode"] = "web" if self.config.get("resume_mode", "cli") == "cli" else "cli"
                self.save_config()
                new_mode_text = "Web图形化" if self.config["resume_mode"] == "web" else "命令行(CLI)"
                new_mode_color = Fore.CYAN if self.config["resume_mode"] == "web" else Fore.YELLOW
                print(f"\n{Fore.CYAN}历史会话选择模式已切换为: {new_mode_color}{new_mode_text}{Style.RESET_ALL}")
                time.sleep(1)
    
    def set_proxy_path(self):
        """设置代理软件路径（跨平台支持）"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        self.print_gradient_text("║" + "设置代理软件路径".center(55) + "║")
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        if os.name == 'nt':  # Windows
            current_path = self.config.get("clash_path", r"D:\Program Files\Clash Verge\clash-verge.exe")
            example_path = "D:\\Program Files\\v2rayN\\v2rayN.exe"
        else:  # macOS/Linux
            current_path = self.config.get("clash_path", "/Applications/Clash Verge.app/Contents/MacOS/clash-verge")
            example_path = "/Applications/Surge.app/Contents/MacOS/Surge"

        print(f"{Fore.YELLOW}当前路径: {Fore.WHITE}{current_path}{Style.RESET_ALL}\n")

        print(f"{Fore.CYAN}📝 请输入代理软件完整路径{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}(例如: {example_path}){Style.RESET_ALL}")
        print(f"{Fore.WHITE}(直接按Enter保持当前路径不变){Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
        new_path = input().strip()

        # 如果用户直接按Enter，保持原路径
        if not new_path:
            print(f"\n{Fore.CYAN}路径保持不变{Style.RESET_ALL}")
            time.sleep(1)
            return

        # 验证路径
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

    def start_websocket_server(self):
        """启动 WebSocket 服务端供手机客户端连接"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        centered_text = "║" + self.center_text("启动 WebSocket 服务端", 57) + "║"
        self.print_gradient_text(centered_text)
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        # 获取当前脚本目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        server_path = os.path.join(current_dir, "claude_server.py")

        if not os.path.exists(server_path):
            print(f"{Fore.RED}❌ 未找到服务端文件: {server_path}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            self._wait_for_key()
            return

        # 检查 websockets 是否安装
        try:
            import websockets
        except ImportError:
            print(f"{Fore.YELLOW}⚠️  正在安装 websockets 依赖...{Style.RESET_ALL}")
            subprocess.run([sys.executable, "-m", "pip", "install", "websockets"], check=True)
            print(f"{Fore.GREEN}✅ websockets 安装完成{Style.RESET_ALL}\n")

        # 获取局域网 IP
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"

        print(f"{Fore.GREEN}📱 手机客户端连接信息:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   局域网地址: ws://{local_ip}:8765{Style.RESET_ALL}")
        print(f"{Fore.WHITE}   本地地址:   ws://127.0.0.1:8765{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}💡 提示: 按 Ctrl+C 停止服务器{Style.RESET_ALL}\n")
        print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")

        # 运行服务端
        try:
            subprocess.run([sys.executable, server_path])
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}⚠️  服务器已停止{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def switch_to_codex_launcher(self):
        """切换到Codex启动器"""
        self.clear_screen()
        print(f"{Fore.CYAN}🔄 正在切换到 Codex 启动器...{Style.RESET_ALL}")
        time.sleep(0.5)

        # 获取当前脚本目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        codex_launcher_path = os.path.join(current_dir, "codex_launcher.py")

        if os.path.exists(codex_launcher_path):
            # 运行Codex启动器
            subprocess.run([sys.executable, codex_launcher_path])
        else:
            print(f"{Fore.RED}❌ 未找到 Codex 启动器文件: {codex_launcher_path}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            msvcrt.getch()

    def update_recent_path(self, path):
        """更新最近使用的路径"""
        if path in self.config["recent_paths"]:
            self.config["recent_paths"].remove(path)
        self.config["recent_paths"].insert(0, path)
        self.config["recent_paths"] = self.config["recent_paths"][:5]
    
    def execute_claude_command(self, path, command):
        """执行Claude命令（跨平台支持）"""
        self.clear_screen()
        print(f"{Fore.CYAN}🚀 启动 Claude Code...{Style.RESET_ALL}")

        # 构建命令序列
        commands = []

        if os.name == 'nt':  # Windows
            drive = path[0] + ":"
            commands.append(drive)
            commands.append(f'cd "{path}"')

            # 只有在开启代理时才设置代理环境变量
            if self.config.get("use_proxy", True):
                commands.extend([
                    f'set https_proxy={self.proxy_url}',
                    f'set http_proxy={self.proxy_url}'
                ])
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}{self.proxy_url}{Style.RESET_ALL}"
            else:
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}已关闭{Style.RESET_ALL}"
        else:  # Unix/Linux/macOS
            commands.append(f'cd "{path}"')

            # 只有在开启代理时才设置代理环境变量
            if self.config.get("use_proxy", True):
                commands.extend([
                    f'export https_proxy={self.proxy_url}',
                    f'export http_proxy={self.proxy_url}'
                ])
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}{self.proxy_url}{Style.RESET_ALL}"
            else:
                proxy_info = f"{Fore.YELLOW}🌐 代理设置: {Fore.WHITE}已关闭{Style.RESET_ALL}"

        commands.append(command)

        # 显示执行信息
        print(f"\n{Fore.GREEN}📍 工作目录: {Fore.WHITE}{path}{Style.RESET_ALL}")
        print(f"{Fore.BLUE}🔧 执行命令: {Fore.WHITE}{command}{Style.RESET_ALL}")
        print(f"{proxy_info}\n")

        # 执行命令
        cmd_string = " && ".join(commands)
        subprocess.run(cmd_string, shell=True)
    
    def handle_path_selection(self, path):
        """处理路径选择后的操作"""
        while True:
            resume_mode = self.config.get("resume_mode", "cli")
            resume_mode_text = "Web图形化" if resume_mode == "web" else "claude --resume"
            options = [
                "进入最近会话 (claude -c)",
                "开始新会话 (claude)",
                f"选择历史会话 ({resume_mode_text})",
                "整理git提交作为学习材料",
                "删除此项目记录",
                "返回主菜单"
            ]

            # 获取路径的最后一部分作为项目名
            project_name = os.path.basename(path) or path
            title = f"📂 {project_name}"

            choice = self.select_from_menu(options, title)

            if choice == -1 or choice == 5:  # ESC或返回主菜单
                break
            elif choice == 0:
                self.execute_claude_command(path, "claude -c")
            elif choice == 1:
                self.execute_claude_command(path, "claude")
            elif choice == 2:
                # 根据配置选择历史会话模式
                if self.config.get("resume_mode", "cli") == "web":
                    self.conversation_viewer.show_sessions_with_resume(path)
                else:
                    self.execute_claude_command(path, "claude --resume")
            elif choice == 3:
                self.git_organizer.run_commit_organizer(path)
            elif choice == 4:
                # 删除项目记录
                if self.delete_project_record(path):
                    break  # 删除成功后返回主菜单

    def delete_project_record(self, path):
        """删除项目记录"""
        project_name = os.path.basename(path) or path

        # 显示确认菜单
        options = [
            "确认删除",
            "取消"
        ]

        choice = self.select_from_menu(options, f"🗑️ 确认删除项目「{project_name}」?")

        if choice == 0:  # 确认删除
            # 从 all_paths 中删除
            if path in self.config["all_paths"]:
                self.config["all_paths"].remove(path)

            # 从 recent_paths 中删除
            if path in self.config["recent_paths"]:
                self.config["recent_paths"].remove(path)

            # 保存配置
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
            # 获取所有路径
            all_paths = self.get_all_paths()
            total_pages = (len(all_paths) - 1) // self.paths_per_page + 1 if all_paths else 1
            
            # 确保当前页码有效
            if self.current_page >= total_pages:
                self.current_page = max(0, total_pages - 1)
            
            # 构建当前页的选项
            options = []
            start_idx = self.current_page * self.paths_per_page
            end_idx = min(start_idx + self.paths_per_page, len(all_paths))
            
            for i in range(start_idx, end_idx):
                path = all_paths[i]
                project_name = os.path.basename(path) or "根目录"
                # 使用特殊标记来区分项目名和路径
                options.append(f"PROJECT:{project_name}|PATH:{path}")
            
            options.append("退出")
            
            # 构建标题（包含页码信息）
            if total_pages > 1:
                title = f"🤖 Claude Code 启动器 - 第 {self.current_page + 1}/{total_pages} 页"
            else:
                title = "🤖 Claude Code 启动器"
            
            choice = self.select_from_menu(options, title, is_main_menu=True)
            
            if choice == -1 or choice == len(options) - 1:  # ESC或退出
                break
            elif choice == -2:  # C键创建
                self.add_new_path()
            elif choice == -3:  # 左箭头 - 上一页
                if self.current_page > 0:
                    self.current_page -= 1
            elif choice == -4:  # 右箭头 - 下一页
                if self.current_page < total_pages - 1:
                    self.current_page += 1
            elif choice == -5:  # I键安装
                self.install_claude_code()
            elif choice == -6:  # U键更新
                self.update_claude_code()
            elif choice == -7:  # S键设置
                self.show_settings()
            elif choice == -8:  # Q键切换
                self.switch_to_codex_launcher()
                break  # 切换后退出当前启动器
            elif choice == -9:  # W键启动服务端
                self.start_websocket_server()
            else:  # 选择了某个路径
                # 提取路径
                selected_option = options[choice]
                if "PROJECT:" in selected_option and "PATH:" in selected_option:
                    # 从新格式中提取路径
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
        """首次运行设置引导（跨平台支持）"""
        self.clear_screen()
        self.print_gradient_text("\n╔" + "═" * 60 + "╗")
        self.print_gradient_text("║" + "欢迎使用 Claude Code 启动器".center(54) + "║")
        self.print_gradient_text("╚" + "═" * 60 + "╝\n")

        print(f"{Fore.YELLOW}🎉 首次运行，让我们先进行一些基础设置！{Style.RESET_ALL}\n")

        proxy_path = None

        # 根据操作系统设置代理
        if os.name == 'nt':  # Windows
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

        else:  # macOS/Linux
            # 自动检测已安装的代理软件
            print(f"{Fore.CYAN}🔍 正在检测已安装的代理软件...{Style.RESET_ALL}\n")
            found_apps = self.detect_proxy_apps_macos()

            if len(found_apps) == 0:
                # 没有检测到，手动输入
                print(f"{Fore.YELLOW}⚠️  未检测到常见代理软件{Style.RESET_ALL}")
                print(f"{Fore.WHITE}请手动输入代理软件路径，或直接按 Enter 跳过{Style.RESET_ALL}")
                print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
                proxy_path = input().strip()
                if not proxy_path:
                    proxy_path = "/Applications/Clash Verge.app/Contents/MacOS/clash-verge"  # 默认值

            elif len(found_apps) == 1:
                # 只检测到一个，自动使用
                name, path = found_apps[0]
                print(f"{Fore.GREEN}✅ 检测到代理软件: {name}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}   路径: {path}{Style.RESET_ALL}")
                proxy_path = path
                time.sleep(1)

            else:
                # 检测到多个，让用户选择
                print(f"{Fore.GREEN}✅ 检测到 {len(found_apps)} 个代理软件:{Style.RESET_ALL}\n")
                options = [f"{name}" for name, _ in found_apps]
                options.append("手动输入路径")

                choice = self.select_from_menu(options, "🌐 选择代理软件")

                if choice == -1 or choice == len(options) - 1:  # ESC 或手动输入
                    print(f"\n{Fore.CYAN}请输入代理软件完整路径:{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")
                    proxy_path = input().strip()
                    if not proxy_path:
                        proxy_path = found_apps[0][1]  # 使用第一个作为默认
                else:
                    proxy_path = found_apps[choice][1]

        # 验证并保存路径
        path_valid = False
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

        # 询问是否默认开启代理
        print(f"\n{Fore.CYAN}🌐 是否默认开启代理功能？{Style.RESET_ALL}")
        print(f"{Fore.WHITE}y/Y = 开启 (推荐)  n/N = 关闭{Style.RESET_ALL}")
        print(f"{Fore.GREEN}➤ {Style.RESET_ALL}", end="")

        proxy_choice = input().strip().lower()
        self.config["use_proxy"] = proxy_choice not in ['n', 'no']

        status = "开启" if self.config["use_proxy"] else "关闭"
        print(f"\n{Fore.GREEN}✅ 代理功能: {status}{Style.RESET_ALL}")

        # 保存配置
        self.save_config()

        print(f"\n{Fore.CYAN}🎯 设置完成！现在可以开始使用了{Style.RESET_ALL}")
        print(f"{Fore.WHITE}提示: 随时可按 S 键进入设置修改配置{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        self._wait_for_key()

    def run(self):
        """运行启动器（跨平台支持）"""
        try:
            # 设置控制台标题（仅Windows）
            if os.name == 'nt':
                os.system("title Claude Code Launcher")

            # 检查是否首次运行或代理路径无效
            clash_path = self.config.get("clash_path")
            if not clash_path or not os.path.exists(clash_path):
                self.first_time_setup()

            # 检查并启动代理软件
            self.check_and_start_clash()

            # 显示主菜单
            self.main_menu()

            # 退出提示
            self.clear_screen()
            print(f"\n{Fore.CYAN}👋 感谢使用 Claude Code 启动器！{Style.RESET_ALL}")
            print(f"{Fore.GREEN}   祝您编码愉快！✨{Style.RESET_ALL}")
        except KeyboardInterrupt:
            self.clear_screen()
            print(f"\n{Fore.YELLOW}⚠️  程序已中断{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ 发生错误: {e}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键退出...{Style.RESET_ALL}")
            self._wait_for_key()

if __name__ == "__main__":
    launcher = ClaudeLauncher()
    launcher.run()