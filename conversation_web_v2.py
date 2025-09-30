#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import webbrowser
from pathlib import Path
import difflib
import base64

class ConversationWebServerV2:
    def __init__(self, project_path, conversation_viewer):
        self.project_path = project_path
        self.conversation_viewer = conversation_viewer
        self.sessions = []

    def generate_html(self):
        """生成HTML页面"""
        self.sessions = self.conversation_viewer.list_sessions(self.project_path)

        html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude 对话历史</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary-blue: #00d4ff;
            --primary-orange: #ff6b35;
            --bg-dark: #0a0e27;
            --bg-dark-secondary: #111525;
            --bg-card: #1a1f3a;
            --bg-card-hover: #252b47;
            --text-primary: #e4e7eb;
            --text-secondary: #9ca3af;
            --text-dim: #6b7280;
            --border-color: rgba(255, 255, 255, 0.1);
            --shadow-sm: 0 2px 8px rgba(0,0,0,0.3);
            --shadow-md: 0 4px 16px rgba(0,0,0,0.4);
            --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
            --shadow-glow: 0 0 20px rgba(0, 212, 255, 0.3);
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #0a0e27 0%, #111525 50%, #1a1f3a 100%);
            min-height: 100vh;
            padding: 20px;
            overflow-x: hidden;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: var(--bg-card);
            border-radius: 24px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
            display: flex;
            height: calc(100vh - 40px);
            transition: var(--transition);
            border: 1px solid var(--border-color);
        }

        /* 侧边栏 */
        .sidebar {
            width: 320px;
            min-width: 320px;
            max-width: 320px;
            flex-shrink: 0;
            background: var(--bg-dark-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            transition: var(--transition);
        }

        .sidebar-header {
            padding: 28px 24px;
            background: linear-gradient(135deg, #0a0e27 0%, var(--bg-card) 100%);
            color: var(--text-primary);
            position: relative;
            overflow: hidden;
            border-bottom: 2px solid var(--primary-blue);
        }

        .sidebar-header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(0, 212, 255, 0.15) 0%, transparent 70%);
            animation: pulse 8s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 0.5; }
            50% { transform: scale(1.1); opacity: 0.3; }
        }

        .sidebar-header h1 {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 8px;
            position: relative;
            z-index: 1;
        }

        .sidebar-header p {
            font-size: 13px;
            opacity: 0.95;
            position: relative;
            z-index: 1;
        }

        .session-list {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }

        .session-item {
            background: var(--bg-card);
            border-radius: var(--radius-md);
            padding: 16px;
            margin-bottom: 12px;
            cursor: pointer;
            transition: var(--transition);
            border: 1px solid var(--border-color);
            box-shadow: var(--shadow-sm);
            position: relative;
            overflow: hidden;
        }

        .session-item::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 3px;
            height: 100%;
            background: linear-gradient(180deg, var(--primary-blue) 0%, var(--primary-orange) 100%);
            transform: scaleY(0);
            transition: transform 0.3s ease;
        }

        .session-item:hover {
            transform: translateX(4px);
            box-shadow: var(--shadow-glow);
            border-color: var(--primary-blue);
            background: var(--bg-card-hover);
        }

        .session-item:hover::before {
            transform: scaleY(1);
        }

        .session-item.active {
            border-color: var(--primary-blue);
            background: var(--bg-card-hover);
            transform: translateX(4px);
            box-shadow: var(--shadow-glow);
        }

        .session-item.active::before {
            transform: scaleY(1);
        }

        .session-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .session-badge {
            display: inline-block;
            padding: 2px 8px;
            background: linear-gradient(135deg, var(--primary-blue) 0%, #0099cc 100%);
            color: var(--bg-dark);
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            box-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
        }

        .session-meta {
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.8;
        }

        .session-meta-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        /* 主内容区 */
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-dark);
        }

        .content-header {
            padding: 24px 32px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: var(--shadow-sm);
            z-index: 10;
        }

        .content-header h2 {
            font-size: 20px;
            color: var(--text-primary);
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary-blue) 0%, var(--primary-orange) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .btn-group {
            display: flex;
            gap: 12px;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: var(--transition);
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: var(--shadow-sm);
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary-blue) 0%, #0099cc 100%);
            color: var(--bg-dark);
            font-weight: 600;
            box-shadow: 0 0 15px rgba(0, 212, 255, 0.4);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.6);
        }

        .btn-primary:active {
            transform: translateY(0);
        }

        .btn-secondary {
            background: var(--bg-card-hover);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: var(--bg-card);
            border-color: var(--primary-orange);
            transform: translateY(-2px);
            box-shadow: 0 0 15px rgba(255, 107, 53, 0.3);
        }

        /* 对话视图 */
        .conversation-view {
            flex: 1;
            overflow-y: auto;
            padding: 32px;
            scroll-behavior: smooth;
        }

        .message-group {
            margin-bottom: 32px;
            animation: messageSlideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @keyframes messageSlideIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* 用户消息在右侧 */
        .message-group.user {
            display: flex;
            justify-content: flex-end;
        }

        .message-group.user .message-wrapper {
            flex-direction: row-reverse;
        }

        /* Claude消息在左侧 */
        .message-group.assistant {
            display: flex;
            justify-content: flex-start;
        }

        .message-wrapper {
            display: flex;
            gap: 14px;
            max-width: 75%;
            min-width: 0;
            align-items: flex-start;
        }

        .message-content-wrapper {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
            min-width: 0;
            overflow-wrap: break-word;
            word-wrap: break-word;
        }

        .message-avatar {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            box-shadow: var(--shadow-md);
            transition: var(--transition);
        }

        .message-group:hover .message-avatar {
            transform: scale(1.1);
        }

        .user .message-avatar {
            background: var(--primary-gradient);
            color: white;
            font-size: 22px;
        }

        .assistant .message-avatar {
            background: white;
            padding: 8px;
        }

        .message-content-wrapper {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 0 4px;
        }

        .user .message-header {
            justify-content: flex-end;
        }

        .message-role {
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
        }

        .message-time {
            font-size: 11px;
            color: var(--text-dim);
        }

        .message-bubble {
            border-radius: var(--radius-lg);
            padding: 16px 20px;
            box-shadow: var(--shadow-md);
            position: relative;
            transition: var(--transition);
            backdrop-filter: blur(10px);
            min-width: 0;
            overflow-wrap: break-word;
            word-break: break-word;
        }

        .message-bubble:hover {
            box-shadow: var(--shadow-lg);
            transform: translateY(-2px);
        }

        .user .message-bubble {
            background: linear-gradient(135deg, var(--primary-blue) 0%, #0099cc 100%);
            color: var(--bg-dark);
            border-bottom-right-radius: 6px;
            box-shadow: 0 4px 16px rgba(0, 212, 255, 0.3);
            font-weight: 500;
        }

        .user .message-bubble:hover {
            box-shadow: 0 6px 24px rgba(0, 212, 255, 0.4);
        }

        .user .message-role,
        .user .message-time {
            color: rgba(10, 14, 39, 0.8);
        }

        .assistant .message-bubble {
            background: var(--bg-card);
            color: var(--text-primary);
            border-bottom-left-radius: 6px;
            border: 1px solid var(--border-color);
        }

        .message-text {
            white-space: pre-wrap;
            word-wrap: break-word;
            word-break: break-word;
            overflow-wrap: break-word;
            line-height: 1.7;
            font-size: 14px;
            max-width: 100%;
        }

        .tool-section {
            margin-top: 14px;
            padding-top: 14px;
            border-top: 1px dashed var(--border-color);
        }

        .user .tool-section {
            border-top-color: rgba(10, 14, 39, 0.3);
        }

        .tool-item {
            background: rgba(255, 107, 53, 0.08);
            border-left: 3px solid var(--primary-orange);
            border-radius: 4px;
            margin: 6px 0;
            overflow: hidden;
            transition: var(--transition);
        }

        .tool-item:hover {
            border-color: var(--primary-orange);
            box-shadow: 0 0 12px rgba(255, 107, 53, 0.2);
        }

        .tool-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            cursor: pointer;
            user-select: none;
            transition: var(--transition);
            background: rgba(255, 107, 53, 0.05);
        }

        .tool-header:hover {
            background: rgba(255, 107, 53, 0.12);
        }

        .tool-header-left {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
        }

        .tool-icon {
            font-size: 16px;
        }

        .tool-name {
            font-weight: 600;
            font-size: 12px;
            color: var(--primary-orange);
        }

        .tool-expand-icon {
            font-size: 10px;
            color: var(--text-dim);
            transition: transform 0.3s ease;
        }

        .tool-item.expanded .tool-expand-icon {
            transform: rotate(180deg);
        }

        .tool-details {
            max-height: 600px;
            overflow: auto;
            transition: var(--transition);
        }

        .tool-item.collapsed .tool-details {
            max-height: 0;
            overflow: hidden;
        }

        .tool-details-content {
            padding: 12px 14px;
            border-top: 1px dashed rgba(255, 107, 53, 0.2);
            background: rgba(0, 0, 0, 0.15);
            font-size: 12px;
            font-family: 'Consolas', 'Monaco', monospace;
        }

        .tool-param {
            margin: 6px 0;
            display: flex;
            gap: 8px;
        }

        .tool-param-key {
            color: var(--primary-blue);
            font-weight: 600;
            min-width: 100px;
        }

        .tool-param-value {
            color: var(--text-secondary);
            word-break: break-all;
            flex: 1;
        }

        .user .tool-item {
            background: rgba(10, 14, 39, 0.15);
            border-color: rgba(10, 14, 39, 0.3);
        }

        .user .tool-name {
            color: var(--bg-dark);
            font-weight: 700;
        }

        .user .tool-details-content {
            background: rgba(10, 14, 39, 0.25);
        }

        .user .tool-param-key {
            color: rgba(10, 14, 39, 0.9);
        }

        .user .tool-param-value {
            color: rgba(10, 14, 39, 0.7);
        }

        .copy-btn {
            position: absolute;
            top: 12px;
            right: 12px;
            background: rgba(0, 212, 255, 0.15);
            border: 1px solid rgba(0, 212, 255, 0.3);
            border-radius: var(--radius-sm);
            padding: 6px 12px;
            font-size: 12px;
            cursor: pointer;
            opacity: 0;
            transition: var(--transition);
            color: var(--primary-blue);
            font-weight: 600;
        }

        .message-bubble:hover .copy-btn {
            opacity: 1;
        }

        .copy-btn:hover {
            background: rgba(0, 212, 255, 0.25);
            transform: scale(1.05);
            box-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
        }

        .user .copy-btn {
            background: rgba(10, 14, 39, 0.2);
            border-color: rgba(10, 14, 39, 0.3);
            color: var(--bg-dark);
        }

        .user .copy-btn:hover {
            background: rgba(10, 14, 39, 0.3);
        }

        /* Diff视图样式 */
        .diff-view {
            margin-top: 12px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            border-radius: var(--radius-sm);
            overflow: hidden;
            background: rgba(0, 0, 0, 0.25);
        }

        .diff-line {
            padding: 2px 8px;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .diff-line-add {
            background: rgba(34, 197, 94, 0.15);
            color: #6ee7b7;
            border-left: 3px solid #22c55e;
        }

        .diff-line-add::before {
            content: '+ ';
            color: #22c55e;
            font-weight: bold;
        }

        .diff-line-remove {
            background: rgba(239, 68, 68, 0.15);
            color: #fca5a5;
            border-left: 3px solid #ef4444;
        }

        .diff-line-remove::before {
            content: '- ';
            color: #ef4444;
            font-weight: bold;
        }

        .diff-line-context {
            background: transparent;
            color: rgba(228, 231, 235, 0.6);
            padding-left: 11px;
        }

        .tool-result {
            margin-top: 12px;
            padding: 10px;
            background: rgba(0, 0, 0, 0.25);
            border-radius: var(--radius-sm);
            border-left: 3px solid var(--primary-blue);
        }

        .tool-result-header {
            font-size: 11px;
            color: var(--primary-blue);
            font-weight: 700;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .tool-result-content {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            color: var(--text-primary);
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 300px;
            overflow-y: auto;
        }

        .tool-result-error {
            border-left-color: #ef4444;
        }

        .tool-result-error .tool-result-header {
            color: #ef4444;
        }

        .tool-result-error .tool-result-content {
            color: #fca5a5;
        }

        /* 空状态 */
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-dim);
            animation: fadeIn 0.6s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .empty-state-icon {
            font-size: 72px;
            margin-bottom: 24px;
            opacity: 0.4;
            animation: float 3s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }

        .empty-state-text {
            font-size: 16px;
            font-weight: 500;
            color: var(--text-secondary);
        }

        /* 通知 */
        .notification {
            position: fixed;
            top: 24px;
            right: 24px;
            background: var(--bg-card);
            padding: 16px 24px;
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-lg), 0 0 20px rgba(0, 212, 255, 0.3);
            display: none;
            animation: slideInRight 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 1000;
            border: 1px solid var(--border-color);
            border-left: 3px solid var(--primary-blue);
        }

        @keyframes slideInRight {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        .notification.show {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .notification-icon {
            font-size: 20px;
            color: var(--primary-blue);
        }

        .notification-text {
            font-size: 14px;
            color: var(--text-primary);
        }

        /* 滚动条 */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-dark-secondary);
            border-radius: 10px;
        }

        ::-webkit-scrollbar-thumb {
            background: linear-gradient(135deg, var(--primary-blue) 0%, #0099cc 100%);
            border-radius: 10px;
            border: 2px solid var(--bg-dark-secondary);
        }

        ::-webkit-scrollbar-thumb:hover {
            background: linear-gradient(135deg, #00b8e6 0%, #00c6ff 100%);
            box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
        }

        /* 响应式 */
        @media (max-width: 968px) {
            .sidebar {
                width: 280px;
            }

            .message-wrapper {
                max-width: 85%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <div class="sidebar-header">
                <h1>💬 对话历史</h1>
                <p id="project-name"></p>
            </div>
            <div class="session-list" id="session-list">
                <!-- Sessions will be loaded here -->
            </div>
        </div>

        <div class="main-content">
            <div class="content-header">
                <h2>✨ 对话内容</h2>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="copyAllConversation()">
                        📋 复制全部
                    </button>
                    <button class="btn btn-secondary" onclick="window.close()">
                        ✕ 关闭
                    </button>
                </div>
            </div>
            <div class="conversation-view" id="conversation-view">
                <div class="empty-state">
                    <div class="empty-state-icon">💭</div>
                    <div class="empty-state-text">请从左侧选择一个会话</div>
                </div>
            </div>
        </div>
    </div>

    <div class="notification" id="notification">
        <span class="notification-icon">✓</span>
        <span class="notification-text" id="notification-text"></span>
    </div>

    <script>
        const sessionsDataB64 = '""" + base64.b64encode(json.dumps(self.get_sessions_data(), ensure_ascii=True).encode('utf-8')).decode('ascii') + """';
        const sessions = JSON.parse(atob(sessionsDataB64));
        const projectName = """ + json.dumps(os.path.basename(self.project_path), ensure_ascii=True) + """;

        document.getElementById('project-name').textContent = projectName;
        loadSessionList();

        function loadSessionList() {
            const listEl = document.getElementById('session-list');
            listEl.innerHTML = '';

            sessions.forEach((session, index) => {
                const item = document.createElement('div');
                item.className = 'session-item';
                item.innerHTML = `
                    <div class="session-title">
                        <span class="session-badge">${index + 1}</span>
                        <span>会话记录</span>
                    </div>
                    <div class="session-meta">
                        <div class="session-meta-item">
                            <span>🕒</span>
                            <span>${session.last_time}</span>
                        </div>
                        <div class="session-meta-item">
                            <span>💬</span>
                            <span>${session.message_count} 条对话</span>
                        </div>
                        <div class="session-meta-item">
                            <span>📦</span>
                            <span>${session.file_size}</span>
                        </div>
                    </div>
                `;
                item.onclick = () => loadConversation(index, item);
                listEl.appendChild(item);
            });

            // 自动选择第一个
            if (sessions.length > 0) {
                const firstItem = listEl.querySelector('.session-item');
                if (firstItem) {
                    firstItem.click();
                }
            }
        }

        function loadConversation(sessionIndex, itemEl) {
            document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
            itemEl.classList.add('active');

            const session = sessions[sessionIndex];
            const viewEl = document.getElementById('conversation-view');

            if (!session.messages || session.messages.length === 0) {
                viewEl.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <div class="empty-state-text">此会话没有消息</div>
                    </div>
                `;
                return;
            }

            const claudeSvg = `<svg height="26" width="26" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z" fill="#D97757" fill-rule="nonzero"/>
            </svg>`;

            let html = '';
            session.messages.forEach((msg, index) => {
                const roleClass = msg.role === 'user' ? 'user' : 'assistant';
                const roleIcon = msg.role === 'user' ? '👤' : claudeSvg;
                const roleText = msg.role === 'user' ? '你' : 'Claude';

                let content = escapeHtml(msg.text);
                let toolsHtml = '';

                if (msg.tools && msg.tools.length > 0) {
                    toolsHtml = '<div class="tool-section">';
                    msg.tools.forEach((tool, toolIndex) => {
                        const toolId = `tool-${index}-${toolIndex}`;
                        const toolIcon = getToolIcon(tool.name);

                        // 构建参数列表 (对于Edit工具，跳过old_string和new_string)
                        let paramsHtml = '';
                        if (tool.input && typeof tool.input === 'object') {
                            for (const [key, value] of Object.entries(tool.input)) {
                                // 对于Edit工具，old_string和new_string会在diff中显示
                                if (tool.name === 'Edit' && (key === 'old_string' || key === 'new_string')) {
                                    continue;
                                }

                                let displayValue = value;
                                if (typeof value === 'string' && value.length > 100) {
                                    displayValue = value.substring(0, 100) + '...';
                                } else if (typeof value === 'object') {
                                    displayValue = JSON.stringify(value, null, 2);
                                    if (displayValue.length > 200) {
                                        displayValue = displayValue.substring(0, 200) + '...';
                                    }
                                }
                                paramsHtml += `
                                    <div class="tool-param">
                                        <span class="tool-param-key">${escapeHtml(key)}:</span>
                                        <span class="tool-param-value">${escapeHtml(String(displayValue))}</span>
                                    </div>
                                `;
                            }
                        }

                        // 构建diff视图 (仅Edit工具)
                        let diffHtml = '';
                        if (tool.diff && Array.isArray(tool.diff)) {
                            diffHtml = '<div class="diff-view">';
                            tool.diff.forEach(line => {
                                let lineClass = 'diff-line';
                                if (line.type === 'add') {
                                    lineClass += ' diff-line-add';
                                } else if (line.type === 'remove') {
                                    lineClass += ' diff-line-remove';
                                } else {
                                    lineClass += ' diff-line-context';
                                }
                                diffHtml += `<div class="${lineClass}">${escapeHtml(line.content)}</div>`;
                            });
                            diffHtml += '</div>';
                        }

                        // 构建结果视图
                        let resultHtml = '';
                        if (tool.result) {
                            const isError = tool.result.is_error;
                            const resultContent = String(tool.result.content);
                            const displayContent = resultContent.length > 500 ? resultContent.substring(0, 500) + '\\n\\n... (内容过长，已截断)' : resultContent;

                            resultHtml = `
                                <div class="tool-result ${isError ? 'tool-result-error' : ''}">
                                    <div class="tool-result-header">
                                        ${isError ? '❌ 执行失败' : '✅ 执行结果'}
                                    </div>
                                    <div class="tool-result-content">${escapeHtml(displayContent)}</div>
                                </div>
                            `;
                        }

                        toolsHtml += `
                            <div class="tool-item expanded" id="${toolId}">
                                <div class="tool-header" onclick="toggleTool('${toolId}')">
                                    <div class="tool-header-left">
                                        <span class="tool-icon">${toolIcon}</span>
                                        <span class="tool-name">${escapeHtml(tool.name)}</span>
                                    </div>
                                    <span class="tool-expand-icon">▲</span>
                                </div>
                                <div class="tool-details">
                                    <div class="tool-details-content">
                                        ${paramsHtml || '<div class="tool-param-value">无参数</div>'}
                                        ${diffHtml}
                                        ${resultHtml}
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    toolsHtml += '</div>';
                }

                html += `
                    <div class="message-group ${roleClass}">
                        <div class="message-wrapper">
                            <div class="message-avatar">${roleIcon}</div>
                            <div class="message-content-wrapper">
                                <div class="message-header">
                                    <span class="message-role">${roleText}</span>
                                    <span class="message-time">${msg.timestamp}</span>
                                </div>
                                <div class="message-bubble">
                                    <button class="copy-btn" onclick="copyMessage(this, event)">📋 复制</button>
                                    ${content ? `<div class="message-text">${content}</div>` : ''}
                                    ${toolsHtml}
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });

            viewEl.innerHTML = html;
            viewEl.scrollTop = 0;
        }

        function getToolIcon(toolName) {
            const icons = {
                'Bash': '⚡',
                'Read': '📖',
                'Write': '✍️',
                'Edit': '✏️',
                'Glob': '🔍',
                'Grep': '🔎',
                'TodoWrite': '📝',
                'Task': '🎯',
                'WebFetch': '🌐',
                'WebSearch': '🔍',
            };
            return icons[toolName] || '🔧';
        }

        function toggleTool(toolId) {
            const toolItem = document.getElementById(toolId);
            if (toolItem) {
                const isExpanded = toolItem.classList.contains('expanded');
                const icon = toolItem.querySelector('.tool-expand-icon');

                if (isExpanded) {
                    toolItem.classList.remove('expanded');
                    toolItem.classList.add('collapsed');
                    if (icon) icon.textContent = '▼';
                } else {
                    toolItem.classList.remove('collapsed');
                    toolItem.classList.add('expanded');
                    if (icon) icon.textContent = '▲';
                }
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function copyMessage(btn, event) {
            event.stopPropagation();
            const bubble = btn.closest('.message-bubble');
            const text = bubble.querySelector('.message-text').textContent;
            copyToClipboard(text);
            showNotification('已复制消息内容');
        }

        function copyAllConversation() {
            const viewEl = document.getElementById('conversation-view');
            const text = viewEl.innerText;
            copyToClipboard(text);
            showNotification('已复制全部对话内容');
        }

        function copyToClipboard(text) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }

        function showNotification(message) {
            const notification = document.getElementById('notification');
            const text = document.getElementById('notification-text');
            text.textContent = message;
            notification.classList.add('show');
            setTimeout(() => {
                notification.classList.remove('show');
            }, 2500);
        }
    </script>
</body>
</html>
"""
        return html

    def get_sessions_data(self):
        """获取会话数据"""
        sessions_data = []

        for session in self.sessions:
            messages = self.parse_conversation_properly(session['file_path'])

            sessions_data.append({
                'last_time': self.conversation_viewer.format_timestamp(session['last_time']),
                'message_count': len(messages),
                'file_size': self.conversation_viewer.format_file_size(session['file_size']),
                'messages': messages
            })

        return sessions_data

    def parse_conversation_properly(self, session_file_path):
        """正确解析对话流"""
        all_records = []

        try:
            with open(session_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        all_records.append(data)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        # 按时间排序
        all_records.sort(key=lambda x: x.get('timestamp', ''))

        # 第一步：建立工具调用ID到结果的映射
        tool_results_map = {}
        for record in all_records:
            if record.get('type') == 'user':
                msg_data = record.get('message', {})
                content = msg_data.get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'tool_result':
                            tool_use_id = item.get('tool_use_id')
                            if tool_use_id:
                                tool_results_map[tool_use_id] = {
                                    'content': item.get('content', ''),
                                    'is_error': item.get('is_error', False)
                                }

        # 第二步：构建对话消息
        messages = []
        current_assistant_msg = None
        current_assistant_tools = []
        current_timestamp = ''

        for record in all_records:
            record_type = record.get('type')
            msg_data = record.get('message', {})
            timestamp = record.get('timestamp', '')

            if record_type == 'user':
                # 如果有未完成的assistant消息，先添加
                if current_assistant_msg or current_assistant_tools:
                    messages.append({
                        'role': 'assistant',
                        'text': current_assistant_msg or '',
                        'tools': current_assistant_tools,
                        'timestamp': self.conversation_viewer.format_timestamp(
                            self.conversation_viewer.parse_timestamp(current_timestamp)
                        )
                    })
                    current_assistant_msg = None
                    current_assistant_tools = []
                    current_timestamp = ''

                # 提取用户消息
                content = self.extract_text_only(msg_data)
                if content and not self.is_system_message(content):
                    messages.append({
                        'role': 'user',
                        'text': content,
                        'tools': [],
                        'timestamp': self.conversation_viewer.format_timestamp(
                            self.conversation_viewer.parse_timestamp(timestamp)
                        )
                    })

            elif record_type == 'assistant':
                content = msg_data.get('content', [])
                if not current_timestamp:
                    current_timestamp = timestamp

                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get('type') == 'text':
                                text = item.get('text', '').strip()
                                if text:
                                    if current_assistant_msg:
                                        current_assistant_msg += '\n\n' + text
                                    else:
                                        current_assistant_msg = text
                            elif item.get('type') == 'tool_use':
                                # 提取工具详细信息
                                tool_id = item.get('id', '')
                                tool_name = item.get('name', 'unknown')
                                tool_input = item.get('input', {})
                                tool_result = tool_results_map.get(tool_id)

                                # 对于Edit工具，生成diff
                                diff_data = None
                                if tool_name == 'Edit' and tool_input:
                                    old_string = tool_input.get('old_string', '')
                                    new_string = tool_input.get('new_string', '')
                                    if old_string and new_string:
                                        diff_data = self.generate_diff_html(old_string, new_string)

                                tool_info = {
                                    'name': tool_name,
                                    'id': tool_id,
                                    'input': tool_input,
                                    'result': tool_result,
                                    'diff': diff_data
                                }
                                current_assistant_tools.append(tool_info)

        # 添加最后一条assistant消息
        if current_assistant_msg or current_assistant_tools:
            messages.append({
                'role': 'assistant',
                'text': current_assistant_msg or '',
                'tools': current_assistant_tools,
                'timestamp': self.conversation_viewer.format_timestamp(
                    self.conversation_viewer.parse_timestamp(current_timestamp)
                ) if current_timestamp else ''
            })

        return messages

    def extract_text_only(self, message_data):
        """只提取文本内容"""
        content = message_data.get('content', '')

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    parts.append(item.get('text', ''))
                elif isinstance(item, str):
                    parts.append(item)
            return '\n'.join(parts)

        return str(content)

    def is_system_message(self, content):
        """判断是否为系统消息"""
        system_patterns = [
            'Caveat: The messages below',
            '<command-name>',
            '<command-message>',
            '<local-command-',
            '[Request interrupted',
        ]

        for pattern in system_patterns:
            if pattern in content:
                return True

        if content.strip().startswith('<') and content.strip().endswith('>') and len(content.strip()) < 100:
            return True

        return False

    def generate_diff_html(self, old_text, new_text):
        """生成diff数据用于前端渲染"""
        if not old_text or not new_text:
            return None

        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff_lines = []
        differ = difflib.Differ()
        diff = list(differ.compare(old_lines, new_lines))

        for line in diff:
            if line.startswith('- '):
                # 删除的行
                diff_lines.append({
                    'type': 'remove',
                    'content': line[2:].rstrip('\n\r')
                })
            elif line.startswith('+ '):
                # 添加的行
                diff_lines.append({
                    'type': 'add',
                    'content': line[2:].rstrip('\n\r')
                })
            elif line.startswith('  '):
                # 未改变的行
                diff_lines.append({
                    'type': 'context',
                    'content': line[2:].rstrip('\n\r')
                })

        return diff_lines

    def start(self):
        """启动Web服务器"""
        html_content = self.generate_html()
        html_file = Path(__file__).parent / "conversation_view.html"

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        webbrowser.open(f'file:///{html_file.absolute()}')


def show_conversation_web(project_path, conversation_viewer):
    """显示Web版对话查看器"""
    server = ConversationWebServerV2(project_path, conversation_viewer)
    server.start()