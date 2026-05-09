import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path


def print_info(msg):
    print(f"[INFO] {msg}")


def print_warn(msg):
    print(f"[WARN] {msg}")


def print_error(msg):
    print(f"[ERROR] {msg}")


def get_workspace_root():
    """
    智能推断 VS Code 的工作区根目录。
    通过向上级目录回溯，寻找标志性文件夹/文件
    """
    current_dir = Path.cwd()
    for folder in [current_dir] + list(current_dir.parents):
        if (
            (folder / ".vscode").is_dir()
            or (folder / ".git").is_dir()
            or (folder / "package.xml").exists()
            or (folder / "CMakeLists.txt").exists()
        ):
            return folder

    if current_dir.name == "build":
        return current_dir.parent
    return current_dir


def execute_build(build_cmd, build_type):
    cmd_str = " ".join(build_cmd)

    flags = f"-DCMAKE_BUILD_TYPE={build_type} -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
    if "CMAKE_BUILD_TYPE" not in cmd_str:
        cmd_str += f" {flags}"
    elif "CMAKE_EXPORT_COMPILE_COMMANDS" not in cmd_str:
        cmd_str += " -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"

    print_info(f"Building in {build_type} mode...")
    print_info(f"Executing: {cmd_str}")

    result = subprocess.run(cmd_str, shell=True)
    return result.returncode == 0


def merge_compile_commands():
    """
    搜索并合并所有 compile_commands.json 到工作区根目录。
    包含排重机制与文件存活性校验。
    """
    workspace_root = get_workspace_root()
    print_info(f"Searching and merging compile_commands.json into {workspace_root}...")

    # 用字典来去重，Key 为源文件的绝对路径，Value 为编译指令对象
    unique_commands = {}

    for path in workspace_root.rglob("compile_commands.json"):
        # 跳过根目录下我们自己生成的那个，防止套娃
        if path.parent == workspace_root:
            continue

        print_info(f"Found: {path}")
        try:
            with open(path, "r") as f:
                commands = json.load(f)

                for cmd in commands:
                    src_file = cmd.get("file")
                    if not src_file:
                        continue

                    # 1. 还原真实的绝对路径
                    src_path = Path(src_file)
                    if not src_path.is_absolute():
                        # compile_commands.json 中通常带有 "directory" 字段表示执行路径
                        work_dir = cmd.get("directory", str(path.parent))
                        src_path = Path(work_dir) / src_path

                    try:
                        resolved_path = src_path.resolve(strict=False)
                    except Exception:
                        resolved_path = src_path

                    # 2. 【核心修复】校验文件是否真的存在！
                    # 如果你删除了某个 .cpp，但构建目录没 clean，这里会把它过滤掉
                    if not resolved_path.exists():
                        continue

                    # 3. 【核心修复】利用字典排重
                    # 如果同一个文件有多个编译指令（比如旧的和新的），
                    # 字典的特性会自动用最新扫描到的指令覆盖旧指令
                    unique_commands[str(resolved_path)] = cmd
        except Exception as e:
            print_warn(f"Failed to read {path}: {e}")

    # 将去重后的字典转换回列表
    merged_commands = list(unique_commands.values())

    if merged_commands:
        root_json = workspace_root / "compile_commands.json"
        with open(root_json, "w") as f:
            json.dump(merged_commands, f, indent=4)
        print_info(
            f"Successfully merged & deduplicated {len(merged_commands)} valid targets into root compile_commands.json"
        )
    else:
        print_warn("No valid compile_commands.json entries found.")


def find_executable(workspace_root, target_name):
    """
    递归查找工作区内的可执行文件
    """
    print_info(f"Searching for executable '{target_name}' in {workspace_root} ...")
    matches = []

    # rglob 递归遍历
    for p in workspace_root.rglob(target_name):
        # 必须是文件，且在 Linux/macOS 下具有可执行权限 (x)
        if p.is_file() and os.access(p, os.X_OK):
            # 排除 Python 脚本，因为我们要配的是 LLDB (C++)
            if p.suffix != ".py":
                matches.append(p)

    if not matches:
        return None

    # 如果找到多个，针对 ROS 项目进行排序，优先选择 devel/lib 下的
    if len(matches) > 1:
        print_warn(f"Found multiple candidates for '{target_name}':")
        for m in matches:
            print_warn(f"  - {m}")
        # 排序：包含 'devel/lib' 的路径排在前面
        matches.sort(key=lambda x: 0 if "devel/lib" in str(x) else 1)
        print_info(f"Auto-selected the most likely one: {matches[0]}")

    return matches[0]


def add_debug_config(exe_input):
    workspace_root = get_workspace_root()
    target_name = Path(exe_input).name

    # 1. 强制在本地查找二进制文件是否真实存在
    found_exe_path = find_executable(workspace_root, target_name)

    if not found_exe_path:
        print_error(f"Executable '{target_name}' NOT FOUND in workspace!")
        print_error("Please make sure you have built the project successfully first.")
        sys.exit(1)

    # 2. 计算相对路径
    rel_path = found_exe_path.relative_to(workspace_root)
    final_exe_path = f"${{workspaceFolder}}/{rel_path}"

    # 3. 读取现有的 launch.json
    vscode_dir = workspace_root / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    launch_file = vscode_dir / "launch.json"

    launch_data = {"version": "0.2.0", "configurations": []}
    if launch_file.exists():
        try:
            with open(launch_file, "r") as f:
                launch_data = json.load(f)
                if "configurations" not in launch_data:
                    launch_data["configurations"] = []
        except json.JSONDecodeError:
            print_warn(
                "Existing launch.json is corrupted or contains comments. Overwriting..."
            )

    config_name = f"(lldb) Debug {target_name}"

    # 4. 【核心修复】严格清理旧配置：如果名字一样，或者程序路径一样，统统删掉
    cleaned_configs = []
    for c in launch_data.get("configurations", []):
        if c.get("name") == config_name:
            print_info(f"Removing old config with same name: '{config_name}'")
            continue
        if c.get("program") == final_exe_path:
            print_info(f"Removing old config pointing to same path: '{final_exe_path}'")
            continue
        cleaned_configs.append(c)

    launch_data["configurations"] = cleaned_configs

    # 5. 注入新的配置
    new_config = {
        "name": config_name,
        "type": "lldb",
        "request": "launch",
        "program": final_exe_path,
        "args": [],
        "cwd": "${workspaceFolder}",
        "stopOnEntry": False,
        "environment": [],
        "externalConsole": False,
    }

    launch_data["configurations"].append(new_config)

    with open(launch_file, "w") as f:
        json.dump(launch_data, f, indent=4)

    print_info(f"Success! Debug configuration added to {launch_file}")
    print_info(f"Target program: {final_exe_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Simplified Clangd Environment & Debug Manager"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    build_parser = subparsers.add_parser("build", help="Compile in Release mode")
    build_parser.add_argument(
        "build_args", nargs=argparse.REMAINDER, help="Build command (e.g., catkin_make)"
    )

    debug_parser = subparsers.add_parser(
        "debug", help="Compile in Debug mode & merge compile_commands.json"
    )
    debug_parser.add_argument(
        "build_args", nargs=argparse.REMAINDER, help="Build command (e.g., cmake ..)"
    )

    add_parser = subparsers.add_parser(
        "add", help="Add a target executable to VS Code launch.json"
    )
    add_parser.add_argument(
        "exe_path", help="Name of the executable to debug (e.g., my_node)"
    )

    args = parser.parse_args()

    if args.command == "build":
        if not args.build_args:
            print_error(
                "Please provide a build command. Usage: tool.py build <catkin_make/cmake ...>"
            )
            sys.exit(1)
        execute_build(args.build_args, build_type="Release")

    elif args.command == "debug":
        if not args.build_args:
            print_error(
                "Please provide a build command. Usage: tool.py debug <catkin_make/cmake ...>"
            )
            sys.exit(1)
        success = execute_build(args.build_args, build_type="Debug")
        if success:
            merge_compile_commands()

    elif args.command == "add":
        add_debug_config(args.exe_path)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
