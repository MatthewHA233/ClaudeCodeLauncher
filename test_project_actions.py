# -*- coding: utf-8 -*-
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import pyperclip

import claude_launcher
import codex_launcher
import grok_launcher
import project_actions

COPY_OPTION = "复制项目路径并打开文件夹"
DELETE_OPTION = "删除此项目记录"
BACK_OPTION = "返回主菜单"


class OpenFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="中文 目录")
        self.addCleanup(self.tmp.cleanup)

    def test_missing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            project_actions.open_folder(os.path.join(self.tmp.name, "不存在"))

    def test_windows_uses_startfile(self):
        with mock.patch.object(project_actions.os, "name", "nt"), \
                mock.patch.object(project_actions.os, "startfile", create=True) as startfile:
            project_actions.open_folder(self.tmp.name)
        startfile.assert_called_once_with(self.tmp.name)

    def test_unix_platforms_use_system_command(self):
        for platform, command in (("darwin", "open"), ("linux", "xdg-open")):
            with self.subTest(platform=platform), \
                    mock.patch.object(project_actions.os, "name", "posix"), \
                    mock.patch.object(project_actions.sys, "platform", platform), \
                    mock.patch.object(project_actions.subprocess, "run") as run:
                project_actions.open_folder(self.tmp.name)
                run.assert_called_once_with([command, self.tmp.name], check=True)


class CopyPathAndOpenTest(unittest.TestCase):
    def run_action(self, path, copy_error=None, open_error=None):
        wait_for_key = mock.Mock()
        output = io.StringIO()
        with mock.patch.object(project_actions.pyperclip, "copy", side_effect=copy_error) as copy, \
                mock.patch.object(project_actions, "open_folder", side_effect=open_error) as opener, \
                mock.patch.object(project_actions.term_input, "clear_screen"), \
                mock.patch.object(project_actions.time, "sleep"), \
                contextlib.redirect_stdout(output):
            project_actions.copy_path_and_open(path, wait_for_key)
        return copy, opener, wait_for_key, output.getvalue()

    def test_success_does_not_block_on_keypress(self):
        copy, opener, wait_for_key, output = self.run_action("D:/项目")
        copy.assert_called_once_with("D:/项目")
        opener.assert_called_once_with("D:/项目")
        wait_for_key.assert_not_called()
        self.assertIn("D:/项目", output)

    def test_open_failure_keeps_copied_path_and_waits(self):
        copy, _, wait_for_key, output = self.run_action(
            "D:/已删除", open_error=FileNotFoundError("文件夹不存在"))
        copy.assert_called_once_with("D:/已删除")
        wait_for_key.assert_called_once_with()
        self.assertIn("文件夹不存在", output)

    def test_copy_failure_still_opens_folder_and_waits(self):
        _, opener, wait_for_key, output = self.run_action(
            "D:/项目", copy_error=pyperclip.PyperclipException("没有剪贴板"))
        opener.assert_called_once_with("D:/项目")
        wait_for_key.assert_called_once_with()
        self.assertIn("没有剪贴板", output)

    def test_failed_open_command_is_reported_not_raised(self):
        _, _, wait_for_key, output = self.run_action(
            "D:/项目", open_error=subprocess.CalledProcessError(1, "xdg-open"))
        wait_for_key.assert_called_once_with()
        self.assertIn("xdg-open", output)


def make_launcher(launcher_class):
    """跳过 __init__，避免测试读写用户真实配置"""
    launcher = launcher_class.__new__(launcher_class)
    launcher.config = {}
    launcher.git_organizer = mock.Mock()
    launcher.conversation_viewer = mock.Mock()
    launcher.conversation_viewer.get_latest_session_info.return_value = None
    launcher.execute_claude_command = mock.Mock()
    launcher.execute_codex_command = mock.Mock()
    launcher.execute_grok_command = mock.Mock()
    launcher.grok_executable = mock.Mock(return_value="grok")
    launcher.get_grok_sessions = mock.Mock(return_value=[])
    launcher.delete_project_record = mock.Mock(return_value=True)
    launcher._wait_for_key = mock.Mock()
    return launcher


class ProjectMenuTest(unittest.TestCase):
    LAUNCHERS = (
        (claude_launcher.ClaudeLauncher, DELETE_OPTION),
        (grok_launcher.GrokLauncher, DELETE_OPTION),
        (codex_launcher.CodexLauncher, BACK_OPTION),  # Codex 没有删除记录选项
    )

    def choose(self, launcher, *labels):
        """依次选择 labels，最后返回主菜单；返回每轮菜单显示的选项"""
        menus = []
        remaining = iter((*labels, BACK_OPTION))

        def select(options, title):
            menus.append(options)
            return options.index(next(remaining))

        launcher.select_from_menu = select
        with mock.patch.object(project_actions, "copy_path_and_open") as action:
            launcher.handle_path_selection("D:/项目")
        return menus, action

    def test_copy_option_sits_right_before_next_entry(self):
        for launcher_class, next_option in self.LAUNCHERS:
            with self.subTest(launcher=launcher_class.__name__):
                menus, _ = self.choose(make_launcher(launcher_class))
                options = menus[0]
                self.assertEqual(options[options.index(COPY_OPTION) + 1], next_option)

    def test_copy_option_runs_action_and_stays_in_project_menu(self):
        for launcher_class, _ in self.LAUNCHERS:
            with self.subTest(launcher=launcher_class.__name__):
                launcher = make_launcher(launcher_class)
                menus, action = self.choose(launcher, COPY_OPTION)
                action.assert_called_once_with("D:/项目", launcher._wait_for_key)
                self.assertEqual(len(menus), 2)

    def test_back_option_does_not_run_action(self):
        for launcher_class, _ in self.LAUNCHERS:
            with self.subTest(launcher=launcher_class.__name__):
                _, action = self.choose(make_launcher(launcher_class))
                action.assert_not_called()

    def test_delete_option_still_reaches_delete(self):
        for launcher_class in (claude_launcher.ClaudeLauncher, grok_launcher.GrokLauncher):
            with self.subTest(launcher=launcher_class.__name__):
                launcher = make_launcher(launcher_class)
                menus = []

                def select(options, title):
                    menus.append(options)
                    return options.index(DELETE_OPTION)

                launcher.select_from_menu = select
                with mock.patch.object(project_actions, "copy_path_and_open") as action:
                    launcher.handle_path_selection("D:/项目")
                launcher.delete_project_record.assert_called_once_with("D:/项目")
                action.assert_not_called()

    def test_git_option_still_reaches_git_organizer(self):
        for launcher_class, _ in self.LAUNCHERS:
            with self.subTest(launcher=launcher_class.__name__):
                launcher = make_launcher(launcher_class)
                self.choose(launcher, "整理git提交作为学习材料")
                launcher.git_organizer.run_commit_organizer.assert_called_once_with("D:/项目")

    def test_claude_pinned_sessions_keep_indexes_aligned(self):
        launcher = make_launcher(claude_launcher.ClaudeLauncher)
        info = {"id": "abc", "title": "t", "last_time": 0, "git_branch": ""}
        launcher._get_valid_pinned_sessions = mock.Mock(return_value=[({"name": "常驻"}, info)])
        launcher.conversation_viewer.format_relative_time.return_value = "刚刚"
        _, action = self.choose(launcher, COPY_OPTION)
        action.assert_called_once_with("D:/项目", launcher._wait_for_key)


if __name__ == "__main__":
    unittest.main()
