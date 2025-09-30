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
        # Claude Code 使用特殊的目录命名方式，规则复杂
        # 使用模糊匹配：提取路径中的ASCII部分进行匹配

        if not self.claude_projects_dir.exists():
            return None

        # 提取路径中的ASCII关键词（去除中文和特殊字符）
        ascii_keywords = []
        for part in project_path.replace("\\", "/").split("/"):
            # 提取每个部分的ASCII字符（保留下划线，因为会被转成横杠）
            ascii_part = ''.join(c for c in part if 32 <= ord(c) < 127 and (c.isalnum() or c == '_'))
            if ascii_part:
                # 将下划线替换为横杠，以匹配目录名
                ascii_keywords.append(ascii_part.replace('_', '-').lower())

        if not ascii_keywords:
            return None

        # 查找最佳匹配的目录
        best_match = None
        best_score = 0

        for dir_name in os.listdir(self.claude_projects_dir):
            dir_path = self.claude_projects_dir / dir_name
            if dir_path.is_dir():
                dir_lower = dir_name.lower()

                # 计算匹配分数：所有关键词都必须出现
                score = 0
                all_matched = True

                for keyword in ascii_keywords:
                    if keyword in dir_lower:
                        score += len(keyword)
                    else:
                        all_matched = False
                        break

                # 只有所有关键词都匹配时才考虑
                if all_matched and score > best_score:
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

        # 等待用户选择会话并关闭服务器
        resume_file = Path.home() / '.claude_launcher_resume.json'

        # 等待文件出现（最多等待60秒）
        import time
        for _ in range(60):
            if resume_file.exists():
                try:
                    with open(resume_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    session_id = data.get('session_id')
                    project_path = data.get('project_path')

                    # 删除临时文件
                    resume_file.unlink()

                    if session_id and project_path:
                        # 启动对话
                        os.chdir(project_path)
                        self.launcher.execute_claude_command(project_path, f"claude --session-id {session_id}")
                    break
                except Exception as e:
                    print(f"读取会话ID失败: {e}")
                    break
            time.sleep(1)

    def show_sessions_menu(self, project_path):
        """显示会话列表Web界面"""
        show_conversation_web(project_path, self)