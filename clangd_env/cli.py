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
    通过向上级目录回溯，寻找标志性文件夹/文件（如 .vscode, .git, package.xml）
    """
    current_dir = Path.cwd()
    
    # 将当前目录及所有父目录作为一个列表遍历
    for folder in [current_dir] + list(current_dir.parents):
        # 常见的工作区根目录标志
        if (folder / ".vscode").is_dir() or \
           (folder / ".git").is_dir() or \
           (folder / "package.xml").exists() or \
           (folder / "CMakeLists.txt").exists():
            return folder
            
    # 如果没找到标志文件，但当前在 build 目录下，通常父目录就是根目录
    if current_dir.name == "build":
        return current_dir.parent
        
    # 如果都没找到，则降级使用当前终端所在目录
    return current_dir

def execute_build(build_cmd, build_type):
    """
    Wrap the build command, inject Build Type and Export Compile Commands flag.
    Does NOT change the default compiler (GNU gcc/g++ remains default).
    """
    cmd_str = " ".join(build_cmd)
    
    # Inject cmake flags. Works for both raw cmake and catkin_make
    flags = f"-DCMAKE_BUILD_TYPE={build_type} -DCMAKE_EXPORT_COMPILE_COMMANDS=ON"
    
    # Avoid appending multiple times if user manually typed it
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
    Find all compile_commands.json in subdirectories and merge them to the workspace root.
    """
    workspace_root = get_workspace_root()
    print_info(f"Searching and merging compile_commands.json into {workspace_root}...")
    
    merged_commands = []
    
    # 从工作区根目录开始往下找
    for path in workspace_root.rglob("compile_commands.json"):
        # 跳过根目录下的那一个，防止自我合并和无限套娃
        if path.parent == workspace_root:
            continue
            
        print_info(f"Found: {path}")
        try:
            with open(path, 'r') as f:
                commands = json.load(f)
                merged_commands.extend(commands)
        except Exception as e:
            print_warn(f"Failed to read {path}: {e}")
            
    if merged_commands:
        root_json = workspace_root / "compile_commands.json"
        with open(root_json, 'w') as f:
            json.dump(merged_commands, f, indent=4)
        print_info(f"Successfully merged {len(merged_commands)} targets into root compile_commands.json")
    else:
        print_warn("No compile_commands.json found in subdirectories.")

def add_debug_config(exe_input):
    """
    Add an LLDB debug configuration to .vscode/launch.json at workspace root
    """
    # 1. Check clangd availability
    if not shutil.which("clangd"):
        print_error("clangd is NOT found in your system PATH!")
        print_info("Please install it manually. e.g., 'sudo apt-get install clangd'")
    else:
        print_info("clangd is installed and available.")
        
    # 2. Remind user about VS Code extensions (Updated for LLDB)
    print_info("---------------------------------------------------")
    print_info("Reminder: Make sure you have these VS Code extensions installed:")
    print_info(" 1. clangd   (llvm-vs-code-extensions.vscode-clangd)")
    print_info(" 2. CodeLLDB (vadimcn.vscode-lldb) - Required for LLDB debugging")
    print_info("---------------------------------------------------")

    workspace_root = get_workspace_root()
    print_info(f"Detected Workspace Root: {workspace_root}")

    # 3. Resolve executable path
    exe_path_obj = Path(exe_input)
    exe_name = exe_path_obj.name
    
    if exe_path_obj.is_absolute():
        final_exe_path = str(exe_path_obj)
    else:
        # Check if it exists relative to cwd
        if exe_path_obj.exists():
            # 转换为相对于工作区的路径，使用 VSCode 变量
            rel_path = exe_path_obj.absolute().relative_to(workspace_root)
            final_exe_path = f"${{workspaceFolder}}/{rel_path}"
        else:
            final_exe_path = f"${{workspaceFolder}}/**/{exe_name}"
            print_warn(f"Executable not directly found at {exe_input}, using wildcard: {final_exe_path}")

    # 4. Generate or Update launch.json in Workspace Root
    vscode_dir = workspace_root / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    launch_file = vscode_dir / "launch.json"
    
    launch_data = {"version": "0.2.0", "configurations": []}
    
    # Read existing configurations if launch.json exists
    if launch_file.exists():
        try:
            with open(launch_file, 'r') as f:
                launch_data = json.load(f)
                if "configurations" not in launch_data:
                    launch_data["configurations"] = []
        except json.JSONDecodeError:
            print_warn("Existing launch.json is corrupted or contains comments. Overwriting...")
    
    config_name = f"(lldb) Debug {exe_name}"
    
    # Remove old config with the same name if it exists (update mechanism)
    launch_data["configurations"] = [
        c for c in launch_data["configurations"] if c.get("name") != config_name
    ]

    # Add the new LLDB configuration
    new_config = {
        "name": config_name,
        "type": "lldb",
        "request": "launch",
        "program": final_exe_path,
        "args": [],
        "cwd": "${workspaceFolder}",
        "stopOnEntry": False,
        "environment": [],
        "externalConsole": False
    }
    
    launch_data["configurations"].append(new_config)
    
    with open(launch_file, 'w') as f:
        json.dump(launch_data, f, indent=4)
        
    print_info(f"Debug configuration '{config_name}' added to {launch_file}!")

def main():
    parser = argparse.ArgumentParser(description="Simplified Clangd Environment & Debug Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: build
    build_parser = subparsers.add_parser("build", help="Compile in Release mode")
    build_parser.add_argument("build_args", nargs=argparse.REMAINDER, help="Build command (e.g., catkin_make)")

    # Command: debug
    debug_parser = subparsers.add_parser("debug", help="Compile in Debug mode & merge compile_commands.json")
    debug_parser.add_argument("build_args", nargs=argparse.REMAINDER, help="Build command (e.g., cmake ..)")

    # Command: add
    add_parser = subparsers.add_parser("add", help="Add a target executable to VS Code launch.json")
    add_parser.add_argument("exe_path", help="Path or name of the executable to debug")

    args = parser.parse_args()

    if args.command == "build":
        if not args.build_args:
            print_error("Please provide a build command. Usage: clangd-env build <catkin_make/cmake ...>")
            sys.exit(1)
        execute_build(args.build_args, build_type="Release")
        
    elif args.command == "debug":
        if not args.build_args:
            print_error("Please provide a build command. Usage: clangd-env debug <catkin_make/cmake ...>")
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