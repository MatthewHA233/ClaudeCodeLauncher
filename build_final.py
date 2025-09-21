import subprocess
import sys
import os

def install_requirements():
    """安装必要的依赖"""
    requirements = ["pyinstaller", "colorama", "psutil"]
    
    for req in requirements:
        try:
            __import__(req)
            print(f"[OK] {req} already installed")
        except ImportError:
            print(f"[INSTALL] Installing {req}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", req])

def build_launcher():
    """打包Claude Code启动器"""
    print("Building Claude Code启动器...")
    
    # 检查图标文件
    icon_path = r"C:\我创建的ICO图标\Claude.ico"
    
    # PyInstaller命令参数
    cmd = [
        "pyinstaller",
        "--onefile",                    # 单文件exe
        "--clean",                      # 清理临时文件
        "--name=Claude Code启动器",      # 应用名称
        "--distpath=dist",              # 输出目录
        "--workpath=build",             # 临时目录
        "claude_launcher.py"            # 源文件
    ]
    
    # 添加图标
    if os.path.exists(icon_path):
        cmd.insert(-1, "--icon")
        cmd.insert(-1, icon_path)
        print(f"[ICON] Using: {icon_path}")
    else:
        print("[WARNING] Icon not found, using default")
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print("[SUCCESS] Build completed!")
        
        exe_path = "dist/Claude Code启动器.exe"
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"[SIZE] {size_mb:.1f} MB")
            print(f"[PATH] {exe_path}")
        
    except subprocess.CalledProcessError as e:
        print("[ERROR] Build failed!")
        if e.stderr:
            print(f"Error details: {e.stderr}")

def cleanup_old_builds():
    """清理旧的构建文件"""
    import shutil
    
    cleanup_dirs = ["build", "dist_debug", "dist_stable", "__pycache__"]
    cleanup_files = ["*.spec"]
    
    for dirname in cleanup_dirs:
        if os.path.exists(dirname):
            try:
                shutil.rmtree(dirname)
                print(f"[CLEANUP] Removed {dirname}")
            except:
                pass

if __name__ == "__main__":
    print("=" * 50)
    print("Claude Code启动器 - 最终版本构建")
    print("=" * 50)
    
    # 清理旧文件
    cleanup_old_builds()
    
    # 安装依赖
    install_requirements()
    print()
    
    # 构建启动器
    build_launcher()
    
    print("\n" + "=" * 50)
    print("构建完成！")
    print("可执行文件: dist/Claude Code启动器.exe")
    print("=" * 50)