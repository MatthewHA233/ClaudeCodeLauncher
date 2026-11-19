#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install_macos_relay as installer


class FakeLaunchctl:
    """记录 launchctl 调用；bootstrap 前 fail_bootstraps 次返回 5，模拟旧服务还在注销。"""

    def __init__(self, fail_bootstraps=0):
        self.calls = []
        self.fail_bootstraps = fail_bootstraps

    def __call__(self, *args, check=False):
        self.calls.append(args[0])
        rc = 0
        if args[0] == "bootstrap" and self.fail_bootstraps:
            self.fail_bootstraps -= 1
            rc = 5
        if check and rc:
            raise subprocess.CalledProcessError(rc, ["launchctl", *args])
        return subprocess.CompletedProcess(["launchctl", *args], rc)


class InstallRestartTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.plist = self.home / "Library" / "LaunchAgents" / f"{installer.LABEL}.plist"
        self.port_open = True
        self.loaded = [True]  # 依次返回，最后一个值一直保持
        for name, value in {
            "_domain": lambda: "gui/501",
            "_shutdown_old": lambda port: None,
            "_is_port_open": lambda port: self.port_open,
            "_is_loaded": lambda: self.loaded.pop(0) if len(self.loaded) > 1 else self.loaded[0],
            "_wait_until": lambda predicate, timeout: any(predicate() for _ in range(5)),
        }.items():
            patcher = mock.patch.object(installer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, value in (("platform.system", "Darwin"), ("pathlib.Path.home", self.home)):
            patcher = mock.patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(installer.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_install(self, launchctl):
        with mock.patch.object(installer, "_run_launchctl", launchctl):
            return installer.install(47800, restart=True)

    def test_unchanged_config_restarts_without_reloading_service(self):
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(installer._plist_bytes(47800))
        launchctl = FakeLaunchctl()
        self.run_install(launchctl)
        self.assertEqual(launchctl.calls, ["kickstart"])

    def test_bootstrap_waits_for_old_service_to_unload(self):
        self.loaded = [True, True, True, False]  # 首次检查已加载，bootout 后还要一会儿才注销
        launchctl = FakeLaunchctl(fail_bootstraps=2)
        self.run_install(launchctl)
        self.assertEqual(launchctl.calls, ["bootout", "bootstrap", "bootstrap", "bootstrap", "kickstart"])

    def test_restart_fails_loudly_when_relay_is_not_listening(self):
        self.port_open = False
        with self.assertRaises(RuntimeError):
            self.run_install(FakeLaunchctl())


if __name__ == "__main__":
    unittest.main()
