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
    Find all compile_commands.json in subdirectories and merge them to the root.
    """
    print_info("Searching and merging compile_commands.json...")
    root_dir = Path.cwd()
    merged_commands = []
    
    for path in root_dir.rglob("compile_commands.json"):
        # Skip the one in the root directory to avoid self-merging
        if path.parent == root_dir:
            continue
            
        print_info(f"Found: {path}")
        try:
            with open(path, 'r') as f:
                commands = json.load(f)
                merged_commands.extend(commands)
        except Exception as e:
            print_warn(f"Failed to read {path}: {e}")
            
    if merged_commands:
        root_json = root_dir / "compile_commands.json"
        with open(root_json, 'w') as f:
            json.dump(merged_commands, f, indent=4)
        print_info(f"Successfully merged {len(merged_commands)} targets into root compile_commands.json")
    else:
        print_warn("No compile_commands.json found in subdirectories.")

def add_debug_config(exe_input):
    """
    Add a debug configuration to .vscode/launch.json
    """
    # 1. Check clangd availability
    if not shutil.which("clangd"):
        print_error("clangd is NOT found in your system PATH!")
        print_info("Please install it manually. e.g., 'sudo apt-get install clangd'")
    else:
        print_info("clangd is installed and available.")
        
    # 2. Remind user about VS Code extensions
    print_info("---------------------------------------------------")
    print_info("Reminder: Make sure you have these VS Code extensions installed:")
    print_info(" 1. clangd (llvm-vs-code-extensions.vscode-clangd)")
    print_info(" 2. C/C++  (ms-vscode.cpptools) - Required for GDB debugging")
    print_info("---------------------------------------------------")

    # 3. Resolve executable path
    exe_path_obj = Path(exe_input)
    exe_name = exe_path_obj.name
    
    if exe_path_obj.is_absolute():
        final_exe_path = str(exe_path_obj)
    else:
        # If user just gave a name or relative path, let's try to locate it or use workspaceFolder
        if exe_path_obj.exists():
            final_exe_path = f"${{workspaceFolder}}/{exe_input}"
        else:
            final_exe_path = f"${{workspaceFolder}}/**/{exe_name}"
            print_warn(f"Executable not directly found at {exe_input}, using wildcard: {final_exe_path}")

    # 4. Generate or Update launch.json
    vscode_dir = Path(".vscode")
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
    
    config_name = f"(gdb) Debug {exe_name}"
    
    # Remove old config with the same name if it exists (update mechanism)
    launch_data["configurations"] = [
        c for c in launch_data["configurations"] if c.get("name") != config_name
    ]

    # Add the new configuration
    new_config = {
        "name": config_name,
        "type": "cppdbg",
        "request": "launch",
        "program": final_exe_path,
        "args": [],
        "stopAtEntry": False,
        "cwd": "${workspaceFolder}",
        "environment": [],
        "externalConsole": False,
        "MIMode": "gdb",
        "setupCommands": [
            {
                "description": "Enable pretty-printing for gdb",
                "text": "-enable-pretty-printing",
                "ignoreFailures": True
            }
        ]
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
        # Optional: you can also merge json here if you want IntelliSense in release mode.
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