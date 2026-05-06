# Clangd Environment & Debug Manager (clangd-env)

A lightweight, zero-configuration CLI tool designed to streamline C++/ROS development in VS Code. It wraps your existing build system (CMake/catkin_make) to automatically generate and merge `compile_commands.json` for **clangd**, and instantly creates GDB debug configurations.

**Note:** This tool does **NOT** change your default compiler. It strictly uses your system's default GCC/G++ while utilizing Clangd solely for advanced IntelliSense.

## ✨ Features

- **Release Build (`build`)**: Injects `-DCMAKE_BUILD_TYPE=Release` and generates compile commands seamlessly.
- **Debug Build & Merge (`debug`)**: Injects `-DCMAKE_BUILD_TYPE=Debug`. Automatically searches and **merges** all `compile_commands.json` from subdirectories into the workspace root (Perfect for multi-package ROS workspaces).
- **1-Click Debugging (`add`)**: Automatically resolves executable paths, checks dependencies, and appends a GDB configuration to your `.vscode/launch.json`.

## 📦 Installation

You can install this tool directly from your Git repository using `pip`:

```bash
# Replace the URL with your actual repository link
pip install git+https://github.com/HGGshiwo/clangd-env-manager.git
```

*Note: You might need to add `~/.local/bin` to your system `PATH` if the `clangd-env` command is not found.*

## 🚀 Usage

The tool provides three simple commands:

### 1. Build (Release Mode)
Wraps your build command to compile in Release mode.
```bash
clangd-env build catkin_make
# or
clangd-env build cmake .. -j4
```

### 2. Debug (Debug Mode + Merge JSON)
Compiles in Debug mode and automatically merges all generated `compile_commands.json` to the root directory for global `clangd` support.
```bash
clangd-env debug catkin_make --use-ninja
# or
clangd-env debug cmake ..
```

### 3. Add VS Code Debug Config
Adds a target to `.vscode/launch.json`. It will automatically search for the executable if a relative path or name is provided.
```bash
# Provide the executable name or path
clangd-env add my_ros_node
```
Once added, open VS Code and press **F5** to start debugging!

## 🛠 Prerequisites

For the best experience, ensure you have the following installed:
1. **clangd** (`sudo apt install clangd`)
2. **VS Code Extensions**:
   - `clangd` (llvm-vs-code-extensions.vscode-clangd)
   - `CodeLLDB` - *Required for debugger*