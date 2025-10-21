import os
import json
from pathlib import Path
from datetime import datetime, timedelta
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

    def parse_timestamp(self, timestamp_str):
        """解析时间戳并转换为中国时区（UTC+8）"""
        if not timestamp_str:
            return datetime.min
        try:
            # ISO 8601 格式: 2025-09-30T02:42:47.598Z (UTC时间)
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # 转换为UTC+8（中国时区）
            china_dt = dt + timedelta(hours=8)
            # 转换为naive datetime（移除时区信息）以便比较
            return china_dt.replace(tzinfo=None)
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