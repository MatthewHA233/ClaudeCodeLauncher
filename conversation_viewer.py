import os
import json
import re
from pathlib import Path
from datetime import datetime
from conversation_web_v2 import show_conversation_web

class ConversationViewer:
    def __init__(self, launcher):
        self.launcher = launcher
        self.claude_projects_dir = Path.home() / ".claude" / "projects"

    def get_project_hash(self, project_path):
        """根据项目路径生成对应的目录名（使用模糊匹配）"""
        # Claude Code 命名规则：
        # Windows: 盘符-路径（非ASCII字符变横杠）
        #   例如：E:\人工智能\激励播放器 → E------------------
        #        D:\my_pro\项目 → D--my-pro-------
        # macOS/Linux: -路径（非ASCII字符变横杠，路径分隔符变横杠）
        #   例如：/Users/maxwellchen → -Users-maxwellchen
        #        /Users/maxwellchen/Projects/Github/ClaudeCodeLauncher → -Users-maxwellchen-Projects-Github-ClaudeCodeLauncher

        if not self.claude_projects_dir.exists():
            return None

        # 优先精确匹配：目录名规则就是把路径中所有非字母数字字符替换为横杠
        exact_name = re.sub(r'[^A-Za-z0-9]', '-', project_path)
        if (self.claude_projects_dir / exact_name).is_dir():
            return exact_name

        # 规范化路径
        norm_path = project_path.replace("\\", "/")

        # 检测操作系统
        is_windows = os.name == 'nt'

        if is_windows:
            # Windows路径处理
            parts = norm_path.split("/")
            if not parts:
                return None

            # 提取盘符（如 C:, D:, E:）
            drive = parts[0].upper().rstrip(":")
            path_depth = len(parts) - 1  # 减去盘符

            # 提取ASCII关键词（用于精确匹配）
            ascii_keywords = []
            for part in parts[1:]:  # 跳过盘符
                part_normalized = part.replace(' ', '-')
                ascii_part = ''.join(c for c in part_normalized if 32 <= ord(c) < 127 and (c.isalnum() or c in ('_', '-')))
                if ascii_part:
                    ascii_keywords.append(ascii_part.replace('_', '-').lower())
        else:
            # macOS/Linux路径处理
            # 去掉开头的 /，然后将所有 / 替换为 -
            if norm_path.startswith("/"):
                norm_path = norm_path[1:]  # 去掉开头的 /

            parts = norm_path.split("/")
            if not parts:
                return None

            # 生成期望的目录名格式：-Users-maxwellchen-Projects-...
            expected_prefix = "-" + "-".join(parts)

            # 提取ASCII关键词（用于精确匹配）
            ascii_keywords = []
            for part in parts:
                part_normalized = part.replace(' ', '-')
                ascii_part = ''.join(c for c in part_normalized if 32 <= ord(c) < 127 and (c.isalnum() or c in ('_', '-')))
                if ascii_part:
                    ascii_keywords.append(ascii_part.replace('_', '-').lower())

            path_depth = len(parts)
            drive = None  # macOS没有盘符

        # 查找最佳匹配的目录
        best_match = None
        best_score = 0

        for dir_name in os.listdir(self.claude_projects_dir):
            dir_path = self.claude_projects_dir / dir_name
            if not dir_path.is_dir():
                continue

            if is_windows:
                # Windows: 必须匹配盘符
                if not dir_name.startswith(drive + "--"):
                    continue
            else:
                # macOS/Linux: 必须以 - 开头
                if not dir_name.startswith("-"):
                    continue

            dir_lower = dir_name.lower()

            # 计算该目录的横杠段数（路径深度）
            if is_windows:
                dir_depth = dir_name.count("-") - 1  # 减去盘符后的双横杠
            else:
                dir_depth = dir_name.count("-")

            # 如果有ASCII关键词，必须全部匹配
            if ascii_keywords:
                all_matched = True
                score = 0
                for keyword in ascii_keywords:
                    if keyword in dir_lower:
                        score += len(keyword)
                    else:
                        all_matched = False
                        break

                if all_matched and score > best_score:
                    best_score = score
                    best_match = dir_name
            else:
                # 纯中文路径：匹配路径深度最接近的
                if is_windows:
                    depth_diff = abs(dir_depth - path_depth * 2)  # 每层约2个横杠
                else:
                    depth_diff = abs(dir_depth - path_depth)  # macOS每层1个横杠

                score = 1000 - depth_diff  # 深度越接近分数越高

                if score > best_score:
                    best_score = score
                    best_match = dir_name

        return best_match

    def list_sessions(self, project_path):
        """列出项目的所有会话"""
        project_hash = self.get_project_hash(project_path)
        if not project_hash:
            return []

        session_dir = self.claude_projects_dir / project_hash
        if not session_dir.exists():
            return []

        sessions = []
        for file_name in os.listdir(session_dir):
            if file_name.endswith(".jsonl"):
                file_path = session_dir / file_name
                session_id = file_name.replace(".jsonl", "")

                # 读取第一条和最后一条消息获取时间
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if lines:
                            first_line = json.loads(lines[0])
                            last_line = json.loads(lines[-1])

                            first_time = self.parse_timestamp(first_line.get('timestamp', ''))
                            last_time = self.parse_timestamp(last_line.get('timestamp', ''))

                            # 统计消息数量
                            message_count = len([l for l in lines if '"type":"user"' in l or '"type":"assistant"' in l])

                            sessions.append({
                                'id': session_id,
                                'file_path': str(file_path),
                                'first_time': first_time,
                                'last_time': last_time,
                                'message_count': message_count,
                                'file_size': os.path.getsize(file_path)
                            })
                except Exception as e:
                    continue

        # 按最后修改时间排序
        sessions.sort(key=lambda x: x['last_time'], reverse=True)
        return sessions

    def _read_file_tail(self, file_path, size=65536):
        """读取文件末尾指定字节数，返回完整行列表（跳过可能被截断的首行）"""
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                f.seek(max(0, file_size - size))
                data = f.read().decode('utf-8', errors='replace')
            lines = data.splitlines()
            # 如果不是从文件头读起，第一行可能不完整，丢弃
            if file_size > size and lines:
                lines = lines[1:]
            return lines
        except Exception:
            return []

    def _read_file_head(self, file_path, size=32768):
        """读取文件开头指定字节数，返回完整行列表"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read(size).decode('utf-8', errors='replace')
            lines = data.splitlines()
            return lines
        except Exception:
            return []

    def _json_typed_field(self, line, type_name, field_name):
        """若该 JSON 行的 type == type_name，返回 field_name 字段（去空后非空），否则 None。

        注意 Claude Code 的命名陷阱：type 是 kebab（custom-title / ai-title），
        字段却是 camel（customTitle / aiTitle）；且 agent-name 的 agentName 值常与
        customTitle 相同，但它不是标题——用精确 type 判断避免误拿。
        """
        if f'"{type_name}"' not in line:
            return None
        try:
            obj = json.loads(line)
        except Exception:
            return None
        if obj.get('type') != type_name:
            return None
        v = obj.get(field_name)
        return v.strip() if isinstance(v, str) and v.strip() else None

    def _user_first_line(self, line):
        """若该行是主人真实发言，返回其文本首行；工具结果/命令/系统注入返回 None"""
        if '"type":"user"' not in line:
            return None
        try:
            obj = json.loads(line)
        except Exception:
            return None
        if obj.get('type') != 'user' or obj.get('isSidechain'):
            return None
        content = obj.get('message', {}).get('content')
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = '\n'.join(c.get('text', '') for c in content
                             if isinstance(c, dict) and c.get('type') == 'text')
        else:
            return None
        text = (text or '').strip()
        if not text or text.startswith('<') or text.startswith('Caveat:'):
            return None
        return text.splitlines()[0].strip()

    def _extract_first_user_prompt(self, file_path):
        """从文件头提取第一条真实用户消息作为标题回退"""
        for line in self._read_file_head(file_path):
            v = self._user_first_line(line)
            if v:
                return v
        return None

    def get_session_info(self, file_path):
        """高效提取单个会话的展示信息（标题/分支/时间/大小），只读文件头尾"""
        try:
            file_size = os.path.getsize(file_path)
        except Exception:
            return None

        session_id = Path(file_path).stem
        custom_title = None     # 用户 /rename，取最新一条（尾部先遇到）
        ai_title = None         # 自动生成，取最早一条（头部）
        ai_title_latest = None  # ai-title 尾部兜底（头部没读到时用）
        first_prompt = None
        git_branch = None
        last_timestamp = None

        # 尾部反向：custom-title 最新 + ai-title 最新(兜底) + 分支 + 最新时间戳
        for line in reversed(self._read_file_tail(file_path)):
            if custom_title is None:
                custom_title = self._json_typed_field(line, 'custom-title', 'customTitle')
            if ai_title_latest is None:
                ai_title_latest = self._json_typed_field(line, 'ai-title', 'aiTitle')
            if git_branch is None and '"gitBranch":"' in line:
                m = re.search(r'"gitBranch":"([^"]*)"', line)
                if m and m.group(1):
                    git_branch = m.group(1)
            if last_timestamp is None and '"timestamp":"' in line:
                m = re.search(r'"timestamp":"([^"]*)"', line)
                if m:
                    last_timestamp = self.parse_timestamp(m.group(1))
            if custom_title and ai_title_latest and git_branch and last_timestamp:
                break

        # 头部正向：ai-title 最早(优先) + 首条发言 + custom-title 头部兜底
        for line in self._read_file_head(file_path):
            if ai_title is None:
                ai_title = self._json_typed_field(line, 'ai-title', 'aiTitle')
            if custom_title is None:
                custom_title = self._json_typed_field(line, 'custom-title', 'customTitle')
            if first_prompt is None:
                first_prompt = self._user_first_line(line)
            if ai_title and first_prompt:
                break

        # 优先级：custom-title(最新) → ai-title(最早) → ai-title(尾部兜底) → 首条发言 → id
        title = custom_title or ai_title or ai_title_latest or first_prompt or session_id[:8]

        if last_timestamp is None or last_timestamp == datetime.min:
            try:
                last_timestamp = datetime.fromtimestamp(os.path.getmtime(file_path))
            except Exception:
                last_timestamp = datetime.min

        return {
            'id': session_id,
            'file_path': str(file_path),
            'title': title,
            'git_branch': git_branch or '',
            'last_time': last_timestamp,
            'file_size': file_size
        }

    def get_sessions_info(self, project_path, limit=None):
        """获取项目会话的展示信息列表（按最近修改排序，limit=None 返回全部）"""
        project_hash = self.get_project_hash(project_path)
        if not project_hash:
            return []

        session_dir = self.claude_projects_dir / project_hash
        if not session_dir.exists():
            return []

        jsonl_files = []
        for file_name in os.listdir(session_dir):
            if file_name.endswith('.jsonl'):
                fp = session_dir / file_name
                try:
                    jsonl_files.append((os.path.getmtime(fp), fp))
                except Exception:
                    continue

        jsonl_files.sort(key=lambda x: x[0], reverse=True)
        if limit is not None:
            jsonl_files = jsonl_files[:limit]

        sessions = []
        for _, fp in jsonl_files:
            info = self.get_session_info(fp)
            if info:
                sessions.append(info)
        return sessions

    def get_latest_session_info(self, project_path):
        """获取项目最近一次会话的展示信息，没有则返回 None"""
        sessions = self.get_sessions_info(project_path, limit=1)
        return sessions[0] if sessions else None

    def find_session_by_id(self, project_path, session_id):
        """按会话 ID 查找会话文件并返回展示信息，找不到返回 None"""
        project_hash = self.get_project_hash(project_path)
        if not project_hash:
            return None
        fp = self.claude_projects_dir / project_hash / f"{session_id}.jsonl"
        if not fp.exists():
            return None
        return self.get_session_info(fp)

    def format_relative_time(self, dt):
        """格式化为相对时间（如 6秒前、13小时前、3周前）"""
        if dt == datetime.min:
            return "未知时间"
        delta = datetime.now() - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            seconds = 0
        if seconds < 60:
            return f"{seconds}秒前"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}分钟前"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}小时前"
        days = hours // 24
        if days < 7:
            return f"{days}天前"
        weeks = days // 7
        if weeks < 5:
            return f"{weeks}周前"
        return dt.strftime("%Y-%m-%d")

    def parse_timestamp(self, timestamp_str):
        """解析时间戳并转换为系统本地时区"""
        if not timestamp_str:
            return datetime.min
        try:
            # ISO 8601 格式: 2025-09-30T02:42:47.598Z (UTC时间)
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # 转换为naive datetime（移除时区信息）以便比较
            return dt.astimezone().replace(tzinfo=None)
        except:
            return datetime.min

    def format_timestamp(self, dt):
        """格式化时间戳为可读格式"""
        if dt == datetime.min:
            return "未知时间"
        # 直接格式化（已经是naive datetime）
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def show_sessions_with_resume(self, project_path):
        """显示Web会话选择界面，支持继续对话"""
        show_conversation_web(project_path, self)

    def show_sessions_menu(self, project_path):
        """显示会话列表Web界面"""
        show_conversation_web(project_path, self)