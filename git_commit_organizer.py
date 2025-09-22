"""
Git提交整理模块 - 为AI沟通提供学习语境材料
支持Claude Code和Codex启动器共享使用
"""

import os
import json
import subprocess
import pyperclip
import msvcrt
import time
from datetime import datetime
from pathlib import Path
from colorama import init, Fore, Back, Style

init(autoreset=True)

class GitCommitOrganizer:
    def __init__(self, launcher_instance):
        """
        初始化Git提交整理器
        :param launcher_instance: 传入启动器实例，用于复用UI方法
        """
        self.launcher = launcher_instance
        self.context_file = Path.home() / ".git_commit_context.json"
        self.context_data = self.load_context_data()
        self.animation_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.frame_index = 0
        self.current_page = 0
        self.commits_per_page = 10

    def load_context_data(self):
        """加载git提交语境数据"""
        if self.context_file.exists():
            with open(self.context_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_context_data(self):
        """保存git提交语境数据"""
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(self.context_data, f, ensure_ascii=False, indent=2)

    def is_git_repository(self, path):
        """检查路径是否为git仓库"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=path,
                capture_output=True,
                text=True,
                shell=False,
                encoding='utf-8',
                errors='ignore'
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_git_commits(self, path, limit=20):
        """获取git提交历史"""
        try:
            # 设置git使用UTF-8编码
            env = os.environ.copy()
            env['LC_ALL'] = 'C.UTF-8'

            # 获取git提交历史，格式：commit_hash|author|date|message
            result = subprocess.run([
                'git', 'log', f'--max-count={limit}',
                '--pretty=format:%H|%an|%ad|%s',
                '--date=short'
            ], cwd=path, capture_output=True, text=True, shell=False, encoding='utf-8', errors='ignore', env=env)

            if result.returncode == 0:
                commits = []
                output = result.stdout.strip()
                if not output:
                    print(f"{Fore.YELLOW}⚠️  该仓库没有提交记录{Style.RESET_ALL}")
                    return []

                for line in output.split('\n'):
                    if line:
                        parts = line.split('|', 3)
                        if len(parts) == 4:
                            commit_hash, author, date, message = parts
                            commits.append({
                                'hash': commit_hash,
                                'short_hash': commit_hash[:8],
                                'author': author,
                                'date': date,
                                'message': message.strip()
                            })
                return commits
            else:
                return []
        except Exception as e:
            print(f"{Fore.RED}❌ 获取git历史失败: {e}{Style.RESET_ALL}")
            return []

    def get_commit_diff(self, path, commit_hash):
        """获取指定提交的diff信息"""
        try:
            result = subprocess.run([
                'git', 'show', commit_hash, '--stat'
            ], cwd=path, capture_output=True, text=True, shell=False, encoding='utf-8', errors='ignore')

            if result.returncode == 0:
                return result.stdout
            return ""
        except Exception:
            return ""

    def get_commit_details(self, path, commit_hash):
        """获取提交的详细信息，包括diff"""
        try:
            # 设置git配置来正确显示中文文件名
            env = os.environ.copy()
            env['LC_ALL'] = 'C.UTF-8'

            result = subprocess.run([
                'git', '-c', 'core.quotepath=false', 'show', commit_hash
            ], cwd=path, capture_output=True, text=True, shell=False, encoding='utf-8', errors='ignore', env=env)

            if result.returncode == 0:
                return result.stdout
            return ""
        except Exception:
            return ""

    def parse_diff_changes(self, diff_content):
        """解析git diff内容，提取文件变更信息"""
        changes = {
            'files_modified': [],
            'files_added': [],
            'files_deleted': [],
            'total_additions': 0,
            'total_deletions': 0
        }

        if not diff_content:
            return changes

        lines = diff_content.split('\n')
        current_file = None
        additions = 0
        deletions = 0

        for line in lines:
            # 检测文件头
            if line.startswith('diff --git'):
                # 处理前一个文件的统计
                if current_file:
                    changes['files_modified'].append({
                        'file': current_file,
                        'additions': additions,
                        'deletions': deletions
                    })
                    changes['total_additions'] += additions
                    changes['total_deletions'] += deletions

                # 开始新文件
                parts = line.split(' ')
                if len(parts) >= 4:
                    current_file = parts[3][2:]  # 去掉 'b/' 前缀
                    # 处理git八进制编码的中文文件名
                    current_file = self.decode_git_filename(current_file)
                    additions = 0
                    deletions = 0

            # 检测新文件
            elif line.startswith('new file mode'):
                if current_file and current_file not in [f['file'] for f in changes['files_added']]:
                    changes['files_added'].append({'file': current_file, 'additions': 0, 'deletions': 0})

            # 检测删除的文件
            elif line.startswith('deleted file mode'):
                if current_file and current_file not in [f['file'] for f in changes['files_deleted']]:
                    changes['files_deleted'].append({'file': current_file, 'additions': 0, 'deletions': 0})

            # 统计增减行
            elif line.startswith('+') and not line.startswith('+++'):
                additions += 1
            elif line.startswith('-') and not line.startswith('---'):
                deletions += 1

        # 处理最后一个文件
        if current_file:
            changes['files_modified'].append({
                'file': current_file,
                'additions': additions,
                'deletions': deletions
            })
            changes['total_additions'] += additions
            changes['total_deletions'] += deletions

        return changes

    def decode_git_filename(self, filename):
        """解码git八进制编码的文件名"""
        try:
            # 如果文件名被双引号包围，说明包含特殊字符
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]  # 去掉引号

                # 处理八进制转义序列
                import re

                # 收集所有八进制字节
                bytes_list = []
                i = 0
                while i < len(filename):
                    if filename[i:i+1] == '\\' and i + 3 < len(filename) and filename[i+1:i+4].isdigit():
                        # 八进制转义序列
                        octal_str = filename[i+1:i+4]
                        try:
                            byte_value = int(octal_str, 8)
                            bytes_list.append(byte_value)
                            i += 4
                        except:
                            bytes_list.append(ord(filename[i]))
                            i += 1
                    else:
                        # 普通字符
                        char = filename[i]
                        if char == '\\' and i + 1 < len(filename):
                            # 处理其他转义字符
                            next_char = filename[i + 1]
                            if next_char == '\\':
                                bytes_list.append(ord('\\'))
                            elif next_char == '"':
                                bytes_list.append(ord('"'))
                            elif next_char == 'n':
                                bytes_list.append(ord('\n'))
                            elif next_char == 't':
                                bytes_list.append(ord('\t'))
                            else:
                                bytes_list.append(ord(char))
                                bytes_list.append(ord(next_char))
                            i += 2
                        else:
                            bytes_list.append(ord(char))
                            i += 1

                # 尝试将字节序列解码为UTF-8
                try:
                    filename = bytes(bytes_list).decode('utf-8')
                except:
                    # 如果UTF-8解码失败，尝试其他编码
                    try:
                        filename = bytes(bytes_list).decode('gbk')
                    except:
                        # 如果都失败，返回原始字符串
                        pass

            return filename
        except Exception:
            # 如果解码失败，返回原始文件名
            return filename

    def is_commit_processed(self, path, commit_hash):
        """检查提交是否已处理"""
        path_key = str(path)
        return (path_key in self.context_data and
                commit_hash in self.context_data[path_key] and
                self.context_data[path_key][commit_hash].get('status') == 'processed')

    def get_processed_context(self, path, commit_hash, commit_info):
        """获取已处理的语境材料，动态格式化"""
        path_key = str(path)
        if (path_key in self.context_data and
            commit_hash in self.context_data[path_key]):
            stored_data = self.context_data[path_key][commit_hash]
            ai_output = stored_data.get('ai_output', '')
            commit_details = stored_data.get('commit_details', '')
            if ai_output:
                # 动态格式化
                return self.format_context_material(ai_output, commit_info, commit_details)
        return ""

    def save_commit_context(self, path, commit_hash, ai_output, commit_details):
        """保存提交的AI原始输出和diff信息"""
        path_key = str(path)
        if path_key not in self.context_data:
            self.context_data[path_key] = {}

        self.context_data[path_key][commit_hash] = {
            'status': 'processed',
            'ai_output': ai_output,
            'commit_details': commit_details,
            'timestamp': datetime.now().isoformat()
        }
        self.save_context_data()

    def generate_ai_prompt(self, commit_info, commit_details):
        """生成AI提示词"""
        prompt = f"""你现在可以访问完整的项目文件。请基于这个git diff，主动读取相关文件并分析完整代码语境。

提交信息：
- ID: {commit_info['hash']}
- 说明: {commit_info['message']}

Git Diff详情：
{commit_details}

**请执行以下操作：**
1. 主动读取diff中涉及的完整源文件内容
2. 查找并读取相关的依赖文件、配置文件、类型定义
3. 分析完整的函数/类/模块定义和调用关系
4. 理解代码在整个项目中的架构位置

**严格输出JSON格式：**
```json
{{
  "complete_code": "从实际文件中读取的完整函数/类代码",
  "related_dependencies": "从相关文件读取的依赖代码",
  "architecture": "基于真实文件分析的架构关系",
  "core_technologies": ["实际使用的技术点"]
}}
```

重要：
1. 必须读取真实文件，不要猜测或编造代码
2. 只输出JSON，不要其他文字
3. 代码中换行用\\n表示
4. 确保JSON格式正确可解析"""
        return prompt

    def call_ai_agent(self, path, prompt, commit_info, commit_details, agent_type="claude"):
        """调用AI代理生成语境材料"""
        try:
            self.launcher.clear_screen()
            print(f"{Fore.CYAN}🤖 正在调用 {agent_type} 生成学习语境材料...{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}⏳ 这可能需要几分钟时间，请稍候...{Style.RESET_ALL}\n")

            # 显示加载动画
            self.show_loading_animation("AI正在分析提交内容", 2)

            # 设置环境变量（包括代理）
            env = os.environ.copy()

            # 只有在启动器开启代理时才设置代理环境变量
            if self.launcher.config.get("use_proxy", True):
                proxy_url = self.launcher.proxy_url
                env['https_proxy'] = proxy_url
                env['http_proxy'] = proxy_url
                print(f"{Fore.YELLOW}🌐 使用代理: {proxy_url}{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}🌐 代理已关闭{Style.RESET_ALL}")

            # 直接执行AI命令，添加项目目录访问权限
            if agent_type == "claude":
                cmd = ["claude.cmd", "--add-dir", ".", "--verbose", "-p"]
            else:
                cmd = [agent_type]

            print(f"{Fore.GREEN}🤖 {agent_type} 正在思考中...{Style.RESET_ALL}\n")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

            # 使用Popen实现真正的实时输出，统一使用stdin传递prompt
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=path,
                shell=False,
                text=True,
                encoding='utf-8',
                errors='ignore',
                env=env,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            # 发送prompt
            process.stdin.write(prompt)
            process.stdin.close()

            # 实时读取输出
            output_lines = []
            while True:
                line = process.stdout.readline()
                if line:
                    print(f"{Fore.WHITE}{line.rstrip()}{Style.RESET_ALL}")
                    output_lines.append(line)
                elif process.poll() is not None:
                    break

            # 读取剩余的stderr
            stderr_output = process.stderr.read()

            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

            # 构造result对象以保持兼容性
            class SimpleResult:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            full_stdout = ''.join(output_lines)
            result = SimpleResult(process.returncode, full_stdout, stderr_output)


            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    # 返回AI原始输出，不进行格式化
                    return output
                else:
                    print(f"{Fore.RED}❌ AI返回了空结果{Style.RESET_ALL}")
                    return None
            else:
                error_msg = result.stderr.strip() if result.stderr else f"命令返回码: {result.returncode}"
                stdout_msg = result.stdout.strip() if result.stdout else "无输出"

                print(f"{Fore.RED}❌ AI调用失败: {error_msg}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}标准输出: {stdout_msg[:200]}...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}错误输出: {error_msg[:200]}...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}返回码: {result.returncode}{Style.RESET_ALL}")

                # 给出具体的解决建议
                if "not found" in error_msg.lower() or result.returncode == 2:
                    print(f"{Fore.YELLOW}💡 建议: 请确认已安装 {agent_type} 并配置到系统PATH{Style.RESET_ALL}")
                elif "proxy" in error_msg.lower() or "connection" in error_msg.lower():
                    print(f"{Fore.YELLOW}💡 建议: 检查代理设置或网络连接{Style.RESET_ALL}")
                elif result.returncode == 1:
                    print(f"{Fore.YELLOW}💡 建议: Claude可能需要登录或API密钥，请手动运行 'claude' 检查状态{Style.RESET_ALL}")

                return None

        except subprocess.TimeoutExpired:
            print(f"{Fore.RED}❌ AI调用超时（5分钟）{Style.RESET_ALL}")
            return None
        except Exception as e:
            print(f"{Fore.RED}❌ AI调用出错: {e}{Style.RESET_ALL}")
            return None

    def show_loading_animation(self, text, duration=2):
        """显示加载动画"""
        start_time = time.time()
        while time.time() - start_time < duration:
            for frame in self.animation_frames:
                print(f"\r{Fore.CYAN}{frame} {text}{Style.RESET_ALL}", end="", flush=True)
                time.sleep(0.1)
                if time.time() - start_time >= duration:
                    break
        print("\r" + " " * (len(text) + 3) + "\r", end="")

    def format_context_material(self, ai_output, commit_info, commit_details=None):
        """格式化AI输出为最终的学习材料"""
        try:
            # 解析diff变更信息
            change_summary = ""
            if commit_details:
                changes = self.parse_diff_changes(commit_details)
                summary_parts = []
                if changes['files_added']:
                    summary_parts.append(f"新增文件 {len(changes['files_added'])} 个: {', '.join([f['file'] for f in changes['files_added']])}")
                if changes['files_deleted']:
                    summary_parts.append(f"删除文件 {len(changes['files_deleted'])} 个: {', '.join([f['file'] for f in changes['files_deleted']])}")
                if changes['files_modified']:
                    summary_parts.append(f"修改文件 {len(changes['files_modified'])} 个: {', '.join([f['file'] for f in changes['files_modified']])}")
                summary_parts.append(f"总计: +{changes['total_additions']}行 -{changes['total_deletions']}行")
                change_summary = chr(10).join(summary_parts)

            # 尝试解析JSON
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                data = json.loads(json_str)
            else:
                # 如果没有JSON格式，尝试直接解析
                data = json.loads(ai_output)

            # 使用Python模板格式化
            formatted_content = f"""以下是我要学习的git提交相关语境信息：

**提交背景：**
{commit_info['short_hash']} - {commit_info['message']}

**变更摘要：**
{change_summary}

**完整代码语境：**
```
{data.get('complete_code', '未提取到完整代码')}
```

**相关依赖代码：**
```
{data.get('related_dependencies', '未找到相关依赖')}
```

**架构关系：**
{data.get('architecture', '未分析出架构关系')}

**核心技术：**
{chr(10).join('- ' + tech for tech in data.get('core_technologies', ['未识别到技术要点']))}

---
这是语境信息，我接下来将会和你讨论，你说OK，我们就开始。"""

            return formatted_content

        except Exception as e:
            print(f"{Fore.YELLOW}⚠️ JSON解析失败，使用原始输出: {e}{Style.RESET_ALL}")
            # 如果解析失败，使用简单模板
            return f"""以下是我要学习的git提交相关语境信息：

**提交背景：**
{commit_info['short_hash']} - {commit_info['message']}

**分析内容：**
{ai_output}

---
这是语境信息，我接下来将会和你讨论，你说OK，我们就开始。"""

    def copy_to_clipboard(self, content):
        """复制内容到剪贴板"""
        try:
            pyperclip.copy(content)
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ 复制到剪贴板失败: {e}{Style.RESET_ALL}")
            return False

    def print_commit_list(self, all_commits, selected_index, path):
        """打印提交列表（分页显示）"""
        self.launcher.clear_screen()

        # 计算分页
        total_pages = (len(all_commits) - 1) // self.commits_per_page + 1 if all_commits else 1

        # 确保当前页码有效
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        # 获取当前页的提交
        start_idx = self.current_page * self.commits_per_page
        end_idx = min(start_idx + self.commits_per_page, len(all_commits))
        current_commits = all_commits[start_idx:end_idx]

        # 标题（包含页码信息）
        self.launcher.print_gradient_text("\n╔" + "═" * 80 + "╗")
        if total_pages > 1:
            title = f"📊 Git提交记录整理 - {os.path.basename(path)} (第{self.current_page + 1}/{total_pages}页)"
        else:
            title = f"📊 Git提交记录整理 - {os.path.basename(path)}"
        centered_title = "║" + self.launcher.center_text(title, 80) + "║"
        self.launcher.print_gradient_text(centered_title)
        self.launcher.print_gradient_text("╚" + "═" * 80 + "╝\n")

        # 提交列表
        for i, commit in enumerate(current_commits):
            is_processed = self.is_commit_processed(path, commit['hash'])

            if i == selected_index:
                # 选中项
                arrow = self.animation_frames[self.frame_index % len(self.animation_frames)]
                status_color = Fore.GREEN if is_processed else Fore.RED
                status_icon = "✅" if is_processed else "⭕"

                print(f"  {Fore.CYAN}{Style.BRIGHT}{arrow} {Back.BLUE}{status_icon} {commit['short_hash']} - {commit['message'][:50]}...{Style.RESET_ALL}")
                print(f"     {Fore.YELLOW}{Style.DIM}作者: {commit['author']} | 时间: {commit['date']}{Style.RESET_ALL}")
                self.frame_index += 1
            else:
                # 普通项
                status_color = Fore.GREEN if is_processed else Fore.RED
                status_icon = "✅" if is_processed else "⭕"

                print(f"  {status_icon} {status_color}{commit['short_hash']}{Style.RESET_ALL} - {Fore.WHITE}{commit['message'][:50]}...{Style.RESET_ALL}")
                print(f"     {Fore.WHITE}{Style.DIM}作者: {commit['author']} | 时间: {commit['date']}{Style.RESET_ALL}")

        # 底部提示
        print(f"\n{Fore.CYAN}╭──────────────────────────────────────────────────────────────────────────────╮{Style.RESET_ALL}")
        if total_pages > 1:
            tip_content = "↑↓ 选择 Enter 处理 ←→ 翻页 🔴红色=未整理 🟢绿色=已整理 ESC 返回"
        else:
            tip_content = "↑↓ 选择 Enter 处理 🔴红色=未整理 🟢绿色=已整理 ESC 返回"
        aligned_tip = self.launcher.center_text(tip_content, 78)
        print(f"{Fore.CYAN}│{Fore.WHITE}{aligned_tip}{Fore.CYAN}│{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╰──────────────────────────────────────────────────────────────────────────────╯{Style.RESET_ALL}")

        # 显示页码信息（如果有多页）
        if total_pages > 1:
            page_info = f"第 {self.current_page + 1} 页，共 {total_pages} 页 | 总计 {len(all_commits)} 个提交"
            print(f"\n{Fore.YELLOW}{page_info}{Style.RESET_ALL}")

        return current_commits

    def get_key_input(self):
        """获取键盘输入"""
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
        return None

    def select_ai_agent(self):
        """选择AI代理"""
        options = [
            "使用 Claude 分析",
            "使用 Codex 分析",
            "取消"
        ]

        choice = self.launcher.select_from_menu(options, "🤖 选择AI代理")

        if choice == 0:
            return "claude"
        elif choice == 1:
            return "codex"
        else:
            return None

    def process_commit(self, path, commit_info):
        """处理单个提交"""
        # 获取提交详情
        print(f"{Fore.CYAN}📋 获取提交详情...{Style.RESET_ALL}")
        commit_details = self.get_commit_details(path, commit_info['hash'])

        if not commit_details:
            print(f"{Fore.RED}❌ 无法获取提交详情{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            msvcrt.getch()
            return

        # 选择AI代理
        agent_type = self.select_ai_agent()
        if not agent_type:
            return

        # 生成提示词
        prompt = self.generate_ai_prompt(commit_info, commit_details)

        # 调用AI生成语境材料
        ai_output = self.call_ai_agent(path, prompt, commit_info, commit_details, agent_type)

        if ai_output:
            # 保存AI原始输出和diff信息
            self.save_commit_context(path, commit_info['hash'], ai_output, commit_details)

            # 格式化为最终语境材料
            context_material = self.format_context_material(ai_output, commit_info, commit_details)

            # 复制到剪贴板
            if self.copy_to_clipboard(context_material):
                print(f"\n{Fore.GREEN}✅ 语境材料已生成并复制到剪贴板！{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.GREEN}✅ 语境材料已生成！{Style.RESET_ALL}")

            # 显示部分内容预览
            preview = context_material[:200] + "..." if len(context_material) > 200 else context_material
            print(f"\n{Fore.CYAN}📄 内容预览:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{preview}{Style.RESET_ALL}")

        else:
            print(f"\n{Fore.RED}❌ 语境材料生成失败{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        msvcrt.getch()

    def view_existing_context(self, path, commit_info):
        """查看已有的语境材料"""
        context_material = self.get_processed_context(path, commit_info['hash'], commit_info)

        if context_material:
            self.launcher.clear_screen()
            self.launcher.print_gradient_text("\n╔" + "═" * 80 + "╗")
            title = f"📄 查看语境材料 - {commit_info['short_hash']}"
            centered_title = "║" + self.launcher.center_text(title, 80) + "║"
            self.launcher.print_gradient_text(centered_title)
            self.launcher.print_gradient_text("╚" + "═" * 80 + "╝\n")

            print(f"{Fore.CYAN}提交信息: {Fore.WHITE}{commit_info['message']}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}提交者: {Fore.WHITE}{commit_info['author']} | {commit_info['date']}{Style.RESET_ALL}\n")

            print(f"{Fore.GREEN}语境材料:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{context_material}{Style.RESET_ALL}")

            print(f"\n{Fore.CYAN}是否复制到剪贴板? (Y/n): {Style.RESET_ALL}", end="")
            choice = input().strip().lower()
            if choice != 'n':
                if self.copy_to_clipboard(context_material):
                    print(f"{Fore.GREEN}✅ 已复制到剪贴板{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ 复制失败{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ 未找到语境材料{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        msvcrt.getch()

    def run_commit_organizer(self, path):
        """运行git提交整理器主界面"""
        # 检查是否为git仓库
        if not self.is_git_repository(path):
            self.launcher.clear_screen()
            print(f"{Fore.RED}❌ 该目录不是git仓库{Style.RESET_ALL}")
            print(f"{Fore.CYAN}路径: {path}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            msvcrt.getch()
            return

        # 获取git提交历史
        commits = self.get_git_commits(path)
        if not commits:
            self.launcher.clear_screen()
            print(f"{Fore.RED}❌ 未找到git提交记录{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}请确认该目录是git仓库且有提交记录{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            msvcrt.getch()
            return

        selected_index = 0
        total_pages = (len(commits) - 1) // self.commits_per_page + 1 if commits else 1

        while True:
            # 获取当前页的提交
            current_commits = self.print_commit_list(commits, selected_index, path)
            key = self.get_key_input()

            if key == 'UP':
                selected_index = (selected_index - 1) % len(current_commits)
            elif key == 'DOWN':
                selected_index = (selected_index + 1) % len(current_commits)
            elif key == 'LEFT':
                # 上一页
                if self.current_page > 0:
                    self.current_page -= 1
                    selected_index = 0  # 重置选择到第一项
            elif key == 'RIGHT':
                # 下一页
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                    selected_index = 0  # 重置选择到第一项
                # 重新计算页数（可能有新提交）
                total_pages = (len(commits) - 1) // self.commits_per_page + 1 if commits else 1
            elif key == 'ENTER':
                # 计算在全体提交中的实际索引
                actual_index = self.current_page * self.commits_per_page + selected_index
                if actual_index < len(commits):
                    commit_info = commits[actual_index]
                    if self.is_commit_processed(path, commit_info['hash']):
                        # 绿色行（有记录），询问是否查看或重新处理
                        options = ["📄 查看已有材料", "🔄 重新整理材料", "取消"]
                        choice = self.launcher.select_from_menu(options, f"✅ {commit_info['short_hash']} 已有学习材料")
                        if choice == 0:
                            self.view_existing_context(path, commit_info)
                        elif choice == 1:
                            self.process_commit(path, commit_info)
                    else:
                        # 红色行（无记录），直接处理
                        self.process_commit(path, commit_info)
            elif key == 'ESC':
                break


    def show_statistics(self, path):
        """显示整理统计"""
        commits = self.get_git_commits(path)
        if not commits:
            self.launcher.clear_screen()
            print(f"{Fore.RED}❌ 未找到git提交记录{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
            msvcrt.getch()
            return

        processed_count = sum(1 for commit in commits if self.is_commit_processed(path, commit['hash']))
        total_count = len(commits)

        self.launcher.clear_screen()
        self.launcher.print_gradient_text("\n╔" + "═" * 60 + "╗")
        title = f"📈 整理统计 - {os.path.basename(path)}"
        centered_title = "║" + self.launcher.center_text(title, 60) + "║"
        self.launcher.print_gradient_text(centered_title)
        self.launcher.print_gradient_text("╚" + "═" * 60 + "╝\n")

        print(f"{Fore.CYAN}📊 总提交数: {Fore.WHITE}{total_count}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✅ 已整理: {Fore.WHITE}{processed_count}{Style.RESET_ALL}")
        print(f"{Fore.RED}⭕ 未整理: {Fore.WHITE}{total_count - processed_count}{Style.RESET_ALL}")

        if total_count > 0:
            percentage = (processed_count / total_count) * 100
            print(f"{Fore.YELLOW}📈 完成度: {Fore.WHITE}{percentage:.1f}%{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}按任意键继续...{Style.RESET_ALL}")
        msvcrt.getch()