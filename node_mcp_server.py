"""
Enhanced Node.js MCP Server

An improved version of the Node.js MCP server with additional features:
1. TypeScript project initialization
2. Next.js integration
3. Docker support
4. ESLint and Prettier configuration
5. Test file generation
6. Performance analysis
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
import os
import asyncio
import subprocess
import re
from typing import Dict, List, Optional, Any

import httpx

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base

# Accept npm package names with optional scope and optional version range/tag.
# Crucially: must NOT start with "-" (blocks flag injection like "--prefix=/etc").
_NPM_NAME_RE = re.compile(
    r"^(@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*(@[A-Za-z0-9._\-+~^*<>=]+)?$"
)

# Valid JS identifier, used for component names that become filenames.
_JS_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_in_project(project_path: str, file_path: str) -> Optional[str]:
    """Resolve file_path relative to project_path, refusing paths that escape it."""
    resolved = os.path.realpath(os.path.join(project_path, file_path))
    root = os.path.realpath(project_path)
    if resolved == root or resolved.startswith(root + os.sep):
        return resolved
    return None

# Context class for our Node.js MCP server
@dataclass
class NodeAppContext:
    """Context for Node.js MCP server"""
    node_version: str
    npm_version: str
    project_path: Optional[str] = None
    package_json: Optional[Dict[str, Any]] = None
    dependencies: Dict[str, str] = field(default_factory=dict)
    dev_dependencies: Dict[str, str] = field(default_factory=dict)

@asynccontextmanager
async def node_app_lifespan(server: FastMCP) -> AsyncIterator[NodeAppContext]:
    """Manage application lifecycle for Node.js MCP server"""
    # Initialize on startup
    print("Node.js MCP Server starting...")
    
    # Check for Node.js and npm
    try:
        node_version = subprocess.check_output(["node", "--version"]).decode().strip()
        npm_version = subprocess.check_output(["npm", "--version"]).decode().strip()
    except Exception as e:
        node_version = "Not found"
        npm_version = "Not found"
        print(f"Warning: Node.js or npm not found: {e}")
    
    # Initialize context
    context = NodeAppContext(
        node_version=node_version,
        npm_version=npm_version,
    )
    
    try:
        # Find project root (directory with package.json)
        current_dir = os.getcwd()
        while current_dir != os.path.dirname(current_dir):  # Stop at root directory
            if os.path.exists(os.path.join(current_dir, "package.json")):
                context.project_path = current_dir
                
                # Load package.json
                try:
                    with open(os.path.join(current_dir, "package.json"), "r") as f:
                        package_json = json.load(f)

                    context.package_json = package_json
                    context.dependencies = package_json.get("dependencies", {})
                    context.dev_dependencies = package_json.get("devDependencies", {})

                    print(f"Found Node.js project at: {current_dir}")
                except Exception as e:
                    print(f"Error reading package.json: {e}")
                
                break
            
            current_dir = os.path.dirname(current_dir)
        
        yield context
    finally:
        # Cleanup on shutdown
        print("Node.js MCP Server shutting down...")

# Create MCP server
mcp = FastMCP(
    "Enhanced Node.js Assistant",
    lifespan=node_app_lifespan,
    dependencies=["httpx"],
)

# =========== RESOURCES ===========

@mcp.resource("node://info")
def get_node_info() -> str:
    """Get information about the Node.js environment"""
    ctx = mcp.request_context.lifespan_context
    
    info = {
        "node_version": ctx.node_version,
        "npm_version": ctx.npm_version,
        "project_path": ctx.project_path,
        "has_package_json": ctx.package_json is not None,
    }
    
    if ctx.package_json:
        info["project_name"] = ctx.package_json.get("name", "Unknown")
        info["project_version"] = ctx.package_json.get("version", "Unknown")
        info["dependencies_count"] = len(ctx.dependencies)
        info["dev_dependencies_count"] = len(ctx.dev_dependencies)
        
        # Detect frameworks
        frameworks = []
        all_dependencies = {**ctx.dependencies, **ctx.dev_dependencies}
        
        if "react" in all_dependencies:
            frameworks.append("React")
        if "vue" in all_dependencies:
            frameworks.append("Vue")
        if "next" in all_dependencies:
            frameworks.append("Next.js")
        if "express" in all_dependencies:
            frameworks.append("Express")
        if "koa" in all_dependencies:
            frameworks.append("Koa")
        if "nestjs" in all_dependencies or "@nestjs/core" in all_dependencies:
            frameworks.append("NestJS")
        if "typescript" in all_dependencies:
            frameworks.append("TypeScript")
        if "jest" in all_dependencies or "mocha" in all_dependencies:
            frameworks.append("Testing Framework")
        
        info["frameworks"] = frameworks
    
    return json.dumps(info, indent=2)

@mcp.resource("node://dependencies")
def get_dependencies() -> str:
    """Get project dependencies"""
    ctx = mcp.request_context.lifespan_context
    
    if not ctx.package_json:
        return json.dumps({"error": "No package.json found"})
    
    return json.dumps({
        "dependencies": ctx.dependencies,
        "devDependencies": ctx.dev_dependencies
    }, indent=2)

@mcp.resource("node://package")
def get_package_json() -> str:
    """Get project's package.json content"""
    ctx = mcp.request_context.lifespan_context
    
    if not ctx.package_json:
        return json.dumps({"error": "No package.json found"})
    
    return json.dumps(ctx.package_json, indent=2)

@mcp.resource("node://structure")
def get_project_structure() -> str:
    """Get project structure (directories and files)"""
    ctx = mcp.request_context.lifespan_context

    if not ctx.project_path:
        return json.dumps({"error": "No Node.js project found"})

    SKIP_DIRS = {"node_modules", ".git", "dist", "build", "coverage", ".next", ".venv", "__pycache__"}
    MAX_DEPTH = 3
    MAX_ENTRIES_PER_DIR = 50

    def walk(directory: str, level: int = 0) -> List[str]:
        indent = "  " * level
        lines: List[str] = []
        try:
            entries = sorted(os.listdir(directory))
        except OSError as e:
            return [f"{indent}<error: {e}>"]

        for item in entries[:MAX_ENTRIES_PER_DIR]:
            path = os.path.join(directory, item)
            is_dir = os.path.isdir(path)

            if is_dir and item in SKIP_DIRS:
                lines.append(f"{indent}├── {item}/ (not listed)")
                continue

            if is_dir:
                lines.append(f"{indent}├── {item}/")
                if level < MAX_DEPTH:
                    lines.extend(walk(path, level + 1))
                else:
                    lines.append(f"{indent}  └── ...")
            else:
                lines.append(f"{indent}├── {item}")

        if len(entries) > MAX_ENTRIES_PER_DIR:
            lines.append(f"{indent}└── ... ({len(entries) - MAX_ENTRIES_PER_DIR} more)")
        return lines

    return json.dumps({
        "project_path": ctx.project_path,
        "structure": walk(ctx.project_path),
    }, indent=2)

@mcp.resource("npm://package/{package_name}")
async def get_npm_package_info(package_name: str) -> str:
    """Get information about an npm package from the npm registry"""
    if not _NPM_NAME_RE.match(package_name):
        return json.dumps({"error": f"Invalid package name: {package_name!r}"})

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://registry.npmjs.org/{package_name}")

        if response.status_code != 200:
            return json.dumps({"error": f"Package not found: {package_name} (HTTP {response.status_code})"})

        data = response.json()
        latest_version = data.get("dist-tags", {}).get("latest", "Unknown")

        result = {
            "name": data.get("name", package_name),
            "description": data.get("description", "No description"),
            "latest_version": latest_version,
            "author": data.get("author", "Unknown"),
            "license": data.get("license", "Unknown"),
            "homepage": data.get("homepage", ""),
            "repository": data.get("repository", {}).get("url", ""),
            "keywords": data.get("keywords", []),
            "versions_count": len(data.get("versions", {})),
        }

        if latest_version != "Unknown" and latest_version in data.get("versions", {}):
            latest_data = data["versions"][latest_version]
            result["dependencies"] = latest_data.get("dependencies", {})
            result["peer_dependencies"] = latest_data.get("peerDependencies", {})
            result["engines"] = latest_data.get("engines", {})

        return json.dumps(result, indent=2)
    except httpx.TimeoutException:
        return json.dumps({"error": "Timed out querying npm registry"})
    except httpx.HTTPError as e:
        return json.dumps({"error": f"Error fetching package info: {e}"})

# =========== TOOLS ===========

@mcp.tool()
async def install_package(package_name: str, ctx: Context, dev: bool = False) -> str:
    """Install a Node.js package into the project (runs `npm install --ignore-scripts`)"""
    node_ctx = ctx.request_context.lifespan_context

    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."

    if node_ctx.npm_version == "Not found":
        return "Error: npm not found. Please install Node.js and npm first."

    if not _NPM_NAME_RE.match(package_name):
        return f"Error: refusing to install — invalid package name: {package_name!r}"

    # --ignore-scripts: do NOT run arbitrary postinstall scripts from the package being installed.
    cmd = ["npm", "install", "--ignore-scripts", package_name]
    if dev:
        cmd.append("--save-dev")

    ctx.info(f"Installing package: {package_name} {'(dev)' if dev else ''}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=node_ctx.project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "Error: npm install timed out after 180s"
    except FileNotFoundError:
        return "Error: npm executable not found on PATH"

    if process.returncode != 0:
        return f"Error installing package: {stderr.decode().strip() or 'unknown error'}"

    # Reload package.json so the in-memory context reflects the new dependency.
    try:
        with open(os.path.join(node_ctx.project_path, "package.json"), "r") as f:
            node_ctx.package_json = json.load(f)
        node_ctx.dependencies = node_ctx.package_json.get("dependencies", {})
        node_ctx.dev_dependencies = node_ctx.package_json.get("devDependencies", {})
    except (OSError, json.JSONDecodeError) as e:
        ctx.info(f"Note: install succeeded but reloading package.json failed: {e}")

    return f"Successfully installed {package_name}"

@mcp.tool()
async def check_for_updates(ctx: Context) -> str:
    """Check for outdated npm packages in the project"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."
    
    # Check if we have npm
    if node_ctx.npm_version == "Not found":
        return "Error: npm not found. Please install Node.js and npm first."
    
    ctx.info("Checking for outdated packages...")
    
    try:
        # Run npm outdated
        process = await asyncio.create_subprocess_exec(
            "npm", "outdated", "--json",
            cwd=node_ctx.project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 or process.returncode == 1:  # npm outdated returns 1 if there are outdated packages
            try:
                outdated_data = json.loads(stdout.decode())
                
                if not outdated_data:
                    return "All packages are up to date!"
                
                result = {"outdated_packages": {}}
                
                for pkg_name, pkg_data in outdated_data.items():
                    result["outdated_packages"][pkg_name] = {
                        "current": pkg_data.get("current", ""),
                        "wanted": pkg_data.get("wanted", ""),
                        "latest": pkg_data.get("latest", ""),
                        "is_dev": pkg_name in node_ctx.dev_dependencies
                    }
                
                return json.dumps(result, indent=2)
            except json.JSONDecodeError:
                # If not JSON, return plain text
                return stdout.decode().strip() or "All packages are up to date!"
        else:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            return f"Error checking for updates: {error_msg}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def run_npm_script(script_name: str, ctx: Context, timeout_seconds: int = 300) -> str:
    """Run an npm script from package.json.

    Note: long-running scripts like `dev`/`watch` never exit on their own and
    will be killed when `timeout_seconds` elapses.
    """
    node_ctx = ctx.request_context.lifespan_context

    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."

    if not node_ctx.package_json:
        return "Error: package.json not found or couldn't be parsed."

    scripts = node_ctx.package_json.get("scripts", {})
    if script_name not in scripts:
        available = ", ".join(scripts.keys()) if scripts else "(none)"
        return f"Error: Script {script_name!r} not found in package.json. Available scripts: {available}"

    ctx.info(f"Running npm script: {script_name} (timeout {timeout_seconds}s)")

    try:
        process = await asyncio.create_subprocess_exec(
            "npm", "run", script_name,
            cwd=node_ctx.project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return "Error: npm executable not found on PATH"

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return f"Error: script {script_name!r} timed out after {timeout_seconds}s and was killed"

    output = stdout.decode().strip()
    error = stderr.decode().strip()

    if process.returncode == 0:
        return f"Script {script_name!r} completed successfully:\n\n{output}"
    return f"Error running script {script_name!r} (exit {process.returncode}):\n\n{error or output}"

@mcp.tool()
def create_react_component(name: str, ctx: Context, props: Optional[List[str]] = None, typescript: bool = False, functional: bool = True) -> str:
    """Generate a React component file"""
    node_ctx = ctx.request_context.lifespan_context

    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."

    if not _JS_IDENT_RE.match(name):
        return f"Error: invalid component name {name!r}. Use a valid JavaScript identifier (e.g. MyComponent)."
    
    # Format props
    formatted_props = ""
    ts_props_interface = ""
    
    if props:
        if typescript:
            # Create TypeScript interface for props
            props_lines = []
            for prop in props:
                if ":" in prop:
                    # User provided type hint
                    props_lines.append(f"  {prop};")
                else:
                    # Default to any
                    props_lines.append(f"  {prop}: any;")
            
            ts_props_interface = "interface " + name + "Props {\n" + "\n".join(props_lines) + "\n}\n\n"
            formatted_props = name + "Props"
        else:
            # Regular JS props destructuring
            formatted_props = "{ " + ", ".join(props) + " }"
    else:
        if typescript:
            ts_props_interface = "interface " + name + "Props {\n  // Define props here\n}\n\n"
            formatted_props = name + "Props"
        else:
            formatted_props = "props"
    
    # Generate component - using normal strings instead of f-strings where backslashes might be needed
    if typescript:
        extension = ".tsx"
        if functional:
            component_code = (
                "import React from 'react';\n\n" +
                ts_props_interface +
                "const " + name + ": React.FC<" + formatted_props + "> = (" + (formatted_props if props else "props") + ") => {\n" +
                "  return (\n" +
                "    <div className=\"" + name.lower() + "-container\">\n" +
                "      <h2>" + name + " Component</h2>\n" +
                "      {/* Add your component content here */}\n" +
                "    </div>\n" +
                "  );\n" +
                "};\n\n" +
                "export default " + name + ";\n"
            )
        else:
            component_code = (
                "import React, { Component } from 'react';\n\n" +
                ts_props_interface +
                "class " + name + " extends Component<" + formatted_props + "> {\n" +
                "  render() {\n" +
                "    return (\n" +
                "      <div className=\"" + name.lower() + "-container\">\n" +
                "        <h2>" + name + " Component</h2>\n" +
                "        {/* Add your component content here */}\n" +
                "      </div>\n" +
                "    );\n" +
                "  }\n" +
                "}\n\n" +
                "export default " + name + ";\n"
            )
    else:
        extension = ".jsx"
        if functional:
            component_code = (
                "import React from 'react';\n\n" +
                "const " + name + " = (" + formatted_props + ") => {\n" +
                "  return (\n" +
                "    <div className=\"" + name.lower() + "-container\">\n" +
                "      <h2>" + name + " Component</h2>\n" +
                "      {/* Add your component content here */}\n" +
                "    </div>\n" +
                "  );\n" +
                "};\n\n" +
                "export default " + name + ";\n"
            )
        else:
            props_destructure = ", ".join(props or [])
            component_code = (
                "import React, { Component } from 'react';\n\n" +
                "class " + name + " extends Component {\n" +
                "  render() {\n" +
                (f"    const {{ {props_destructure} }} = this.props;\n" if props else "") +
                "    \n" +
                "    return (\n" +
                "      <div className=\"" + name.lower() + "-container\">\n" +
                "        <h2>" + name + " Component</h2>\n" +
                "        {/* Add your component content here */}\n" +
                "      </div>\n" +
                "    );\n" +
                "  }\n" +
                "}\n\n" +
                "export default " + name + ";\n"
            )
    
    # Determine component directory
    # First check for src/components, then src, then project root
    components_dir = os.path.join(node_ctx.project_path, "src", "components")
    if not os.path.exists(components_dir):
        components_dir = os.path.join(node_ctx.project_path, "src")
        if not os.path.exists(components_dir):
            components_dir = node_ctx.project_path
    
    # Create components directory if it doesn't exist
    if not os.path.exists(components_dir):
        os.makedirs(components_dir)
    
    # Write component file
    component_path = os.path.join(components_dir, name + extension)
    
    with open(component_path, "w") as f:
        f.write(component_code)
    
    return f"Created {name} component at {component_path}"

@mcp.tool()
def analyze_package_dependencies(ctx: Context, deep: bool = False) -> str:
    """Analyze project dependencies for potential issues and improvements"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."
    
    if not node_ctx.package_json:
        return "Error: package.json not found or couldn't be parsed."
    
    issues = []
    warnings = []
    suggestions = []
    
    # Get dependencies
    dependencies = node_ctx.dependencies or {}
    dev_dependencies = node_ctx.dev_dependencies or {}
    all_dependencies = {**dependencies, **dev_dependencies}
    
    # Check for empty dependencies
    if not all_dependencies:
        return "No dependencies found in package.json."
    
    ctx.info(f"Analyzing {len(all_dependencies)} dependencies...")
    
    # Check for version pinning
    unpinned_deps = []
    outdated_syntax = []
    
    for dep_name, version in all_dependencies.items():
        if version.startswith("^") or version.startswith("~"):
            unpinned_deps.append(dep_name)
        
        # Check for outdated syntax
        if version.startswith(">=") or version == "*" or version == "latest":
            outdated_syntax.append(dep_name)
    
    if unpinned_deps:
        warnings.append(f"Found {len(unpinned_deps)} unpinned dependencies that may cause version inconsistencies: {', '.join(unpinned_deps[:5])}{', ...' if len(unpinned_deps) > 5 else ''}")
        suggestions.append("Consider pinning critical dependencies to exact versions to ensure reproducible builds.")
    
    if outdated_syntax:
        warnings.append(f"Found {len(outdated_syntax)} dependencies with outdated version syntax: {', '.join(outdated_syntax[:5])}{', ...' if len(outdated_syntax) > 5 else ''}")
    
    # Check for duplicate dependencies in both regular and dev dependencies
    duplicates = []
    
    for dep_name in dependencies:
        if dep_name in dev_dependencies:
            duplicates.append(dep_name)
    
    if duplicates:
        issues.append(f"Found {len(duplicates)} dependencies that appear in both dependencies and devDependencies: {', '.join(duplicates)}")
        suggestions.append("Remove duplicate dependencies from either dependencies or devDependencies.")
    
    # Check for missing peer dependencies
    if "peerDependencies" in node_ctx.package_json:
        peer_deps = node_ctx.package_json["peerDependencies"]
        missing_peers = []
        
        for peer_name in peer_deps:
            if peer_name not in dependencies and peer_name not in dev_dependencies:
                missing_peers.append(peer_name)
        
        if missing_peers:
            issues.append(f"Missing peer dependencies: {', '.join(missing_peers)}")
            suggestions.append("Install missing peer dependencies.")
    
    # Detect common framework dependencies
    frameworks = []
    
    if "react" in all_dependencies:
        frameworks.append("React")
    if "vue" in all_dependencies:
        frameworks.append("Vue")
    if "angular" in all_dependencies or "@angular/core" in all_dependencies:
        frameworks.append("Angular")
    if "next" in all_dependencies:
        frameworks.append("Next.js")
    if "express" in all_dependencies:
        frameworks.append("Express")
    if "koa" in all_dependencies:
        frameworks.append("Koa")
    if "typescript" in all_dependencies or "typescript" in dev_dependencies:
        frameworks.append("TypeScript")
    
    # Make suggestions based on frameworks
    if "React" in frameworks:
        if "react-dom" not in all_dependencies:
            warnings.append("React is installed but react-dom is missing.")
        
        if "TypeScript" in frameworks and "@types/react" not in all_dependencies:
            suggestions.append("TypeScript is being used but @types/react is not installed. Consider adding it as a dev dependency.")
        
        if "eslint" in all_dependencies and "eslint-plugin-react" not in all_dependencies:
            suggestions.append("ESLint is installed but eslint-plugin-react is missing. Consider adding it for React-specific linting.")
    
    if "TypeScript" in frameworks:
        if "ts-node" not in all_dependencies:
            suggestions.append("Consider adding ts-node for running TypeScript directly without compilation.")
    
    # Check for potential security issues
    if node_ctx.npm_version != "Not found" and deep:
        try:
            ctx.info("Running npm audit for security issues...")
            
            audit_process = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=node_ctx.project_path,
                capture_output=True,
                text=True
            )
            
            if audit_process.returncode <= 1:  # npm audit returns 1 if issues found
                try:
                    audit_data = json.loads(audit_process.stdout)
                    
                    if "vulnerabilities" in audit_data:
                        vulns = audit_data["vulnerabilities"]
                        total_vulns = sum(vulns.get(level, 0) for level in ["info", "low", "moderate", "high", "critical"])
                        
                        if total_vulns > 0:
                            issues.append(f"Found {total_vulns} security vulnerabilities: " + 
                                        ", ".join([f"{count} {level}" for level, count in vulns.items() if count > 0 and level != "total"]))
                            suggestions.append("Run 'npm audit fix' to automatically fix these issues when possible.")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            warnings.append(f"Could not run security audit: {str(e)}")
    
    # Final analysis result
    result = {
        "project_name": node_ctx.package_json.get("name", "Unknown"),
        "dependencies_count": len(dependencies),
        "dev_dependencies_count": len(dev_dependencies),
        "frameworks_detected": frameworks,
        "issues": issues,
        "warnings": warnings,
        "suggestions": suggestions
    }
    
    return json.dumps(result, indent=2)

# NEW TOOLS

@mcp.tool()
def create_test_file(file_path: str, ctx: Context, framework: str = "jest") -> str:
    """Generate a test file for a JavaScript/TypeScript file"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."

    # Validate file path (must stay inside the project root)
    full_file_path = _resolve_in_project(node_ctx.project_path, file_path)
    if full_file_path is None:
        return f"Error: {file_path} is outside the project directory."
    if not os.path.exists(full_file_path):
        return f"Error: File {file_path} not found."

    # Determine file type (js, jsx, ts, tsx)
    _, ext = os.path.splitext(file_path)
    is_typescript = ext.lower() in ['.ts', '.tsx']
    is_react = ext.lower() in ['.jsx', '.tsx']
    
    # Create test file path
    file_name = os.path.basename(file_path)
    base_name, _ = os.path.splitext(file_name)
    
    # Check if tests directory exists, if not create one
    tests_dir = os.path.join(node_ctx.project_path, '__tests__')
    if not os.path.exists(tests_dir):
        os.makedirs(tests_dir)
    
    # Determine test framework
    framework = framework.lower()
    if framework not in ['jest', 'mocha', 'vitest']:
        return f"Error: Unsupported test framework {framework}. Supported frameworks: jest, mocha, vitest."
    
    # Create test file content based on framework
    if framework == 'jest':
        test_file_name = f"{base_name}.test{ext}"
        test_file_path = os.path.join(tests_dir, test_file_name)
        
        # Generate import statement
        import_path = os.path.splitext(os.path.join('..', file_path))[0]
        if import_path.startswith('../'):
            import_path = import_path[3:]
        
        # Handle React components
        if is_react:
            test_content = (
                f"import React from 'react';\n" +
                f"import {{ render, screen }} from '@testing-library/react';\n" +
                f"import '@testing-library/jest-dom';\n" +
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', () => {{\n" +
                f"  test('renders without crashing', () => {{\n" +
                f"    render(<{base_name} />);\n" +
                f"    // Add your assertions here\n" +
                f"  }});\n" +
                f"}});\n"
            )
        else:
            # Handle regular JS/TS modules
            test_content = (
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', () => {{\n" +
                f"  test('should work correctly', () => {{\n" +
                f"    // Add your test implementation here\n" +
                f"    expect(true).toBe(true);\n" +
                f"  }});\n" +
                f"}});\n"
            )
    
    elif framework == 'mocha':
        test_file_name = f"{base_name}.spec{ext}"
        test_file_path = os.path.join(tests_dir, test_file_name)
        
        # Generate import statement
        import_path = os.path.splitext(os.path.join('..', file_path))[0]
        if import_path.startswith('../'):
            import_path = import_path[3:]
        
        chai_import = "const expect = require('chai').expect;" if not is_typescript else "import { expect } from 'chai';"
        
        # Handle React components or regular modules
        if is_react:
            test_content = (
                f"{chai_import}\n" +
                f"import React from 'react';\n" +
                f"import {{ render }} from '@testing-library/react';\n" +
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', function() {{\n" +
                f"  it('renders without crashing', function() {{\n" +
                f"    const {{ container }} = render(<{base_name} />);\n" +
                f"    // Add your assertions here\n" +
                f"    expect(container).to.exist;\n" +
                f"  }});\n" +
                f"}});\n"
            )
        else:
            test_content = (
                f"{chai_import}\n" +
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', function() {{\n" +
                f"  it('should work correctly', function() {{\n" +
                f"    // Add your test implementation here\n" +
                f"    expect(true).to.equal(true);\n" +
                f"  }});\n" +
                f"}});\n"
            )
    
    else:  # vitest — framework already validated against the supported list above
        test_file_name = f"{base_name}.test{ext}"
        test_file_path = os.path.join(tests_dir, test_file_name)
        
        # Generate import statement
        import_path = os.path.splitext(os.path.join('..', file_path))[0]
        if import_path.startswith('../'):
            import_path = import_path[3:]
        
        # Handle React components
        if is_react:
            test_content = (
                f"import {{ describe, it, expect }} from 'vitest';\n" +
                f"import React from 'react';\n" +
                f"import {{ render, screen }} from '@testing-library/react';\n" +
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', () => {{\n" +
                f"  it('renders without crashing', () => {{\n" +
                f"    render(<{base_name} />);\n" +
                f"    // Add your assertions here\n" +
                f"  }});\n" +
                f"}});\n"
            )
        else:
            # Handle regular JS/TS modules
            test_content = (
                f"import {{ describe, it, expect }} from 'vitest';\n" +
                f"import {base_name} from '{import_path}';\n\n" +
                f"describe('{base_name}', () => {{\n" +
                f"  it('should work correctly', () => {{\n" +
                f"    // Add your test implementation here\n" +
                f"    expect(true).toBe(true);\n" +
                f"  }});\n" +
                f"}});\n"
            )
    
    # Write test file
    with open(test_file_path, 'w') as f:
        f.write(test_content)
    
    # Check if testing library is installed
    all_dependencies = {**node_ctx.dependencies, **node_ctx.dev_dependencies}
    missing_deps = []
    
    if framework == 'jest' and 'jest' not in all_dependencies:
        missing_deps.append('jest')
    elif framework == 'mocha' and 'mocha' not in all_dependencies:
        missing_deps.append('mocha')
        if 'chai' not in all_dependencies:
            missing_deps.append('chai')
    elif framework == 'vitest' and 'vitest' not in all_dependencies:
        missing_deps.append('vitest')
    
    if is_react and '@testing-library/react' not in all_dependencies:
        missing_deps.append('@testing-library/react')
    
    result = f"Created test file: {test_file_path}"
    
    if missing_deps:
        result += f"\n\nNote: You may need to install these packages: {', '.join(missing_deps)}"
        result += f"\nRun: npm install --save-dev {' '.join(missing_deps)}"
    
    return result

@mcp.tool()
def setup_eslint_prettier(ctx: Context, typescript: bool = False, react: bool = False) -> str:
    """Set up ESLint and Prettier for a Node.js project"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."
    
    # Check if we have npm
    if node_ctx.npm_version == "Not found":
        return "Error: npm not found. Please install Node.js and npm first."
    
    # Determine what packages to install based on project type
    packages = ["eslint", "prettier", "eslint-config-prettier", "eslint-plugin-prettier"]
    
    if typescript:
        packages.extend(["@typescript-eslint/eslint-plugin", "@typescript-eslint/parser"])
    
    if react:
        packages.append("eslint-plugin-react")
        if typescript:
            packages.append("eslint-plugin-react-hooks")
    
    # Create basic ESLint config
    eslint_config = {
        "env": {
            "browser": True,
            "es2021": True,
            "node": True
        },
        "extends": [
            "eslint:recommended",
            "plugin:prettier/recommended"
        ],
        "parserOptions": {
            "ecmaVersion": "latest",
            "sourceType": "module"
        },
        "rules": {
            "indent": ["error", 2],
            "linebreak-style": ["error", "unix"],
            "quotes": ["error", "single"],
            "semi": ["error", "always"]
        }
    }
    
    # Modify config for TypeScript
    if typescript:
        eslint_config["parser"] = "@typescript-eslint/parser"
        eslint_config["extends"].append("plugin:@typescript-eslint/recommended")
        eslint_config["plugins"] = ["@typescript-eslint"]
    
    # Modify config for React
    if react:
        eslint_config["extends"].append("plugin:react/recommended")
        if typescript:
            eslint_config["extends"].append("plugin:react-hooks/recommended")
        eslint_config["parserOptions"]["ecmaFeatures"] = {"jsx": True}
        if "plugins" not in eslint_config:
            eslint_config["plugins"] = []
        eslint_config["plugins"].append("react")
        eslint_config["settings"] = {"react": {"version": "detect"}}
    
    # Create Prettier config
    prettier_config = {
        "semi": True,
        "singleQuote": True,
        "tabWidth": 2,
        "trailingComma": "es5",
        "printWidth": 100,
        "bracketSpacing": True
    }
    
    # Write ESLint config file
    eslint_path = os.path.join(node_ctx.project_path, '.eslintrc.json')
    with open(eslint_path, 'w') as f:
        json.dump(eslint_config, f, indent=2)
    
    # Write Prettier config file
    prettier_path = os.path.join(node_ctx.project_path, '.prettierrc.json')
    with open(prettier_path, 'w') as f:
        json.dump(prettier_config, f, indent=2)
    
    # Create .eslintignore file
    eslintignore_path = os.path.join(node_ctx.project_path, '.eslintignore')
    with open(eslintignore_path, 'w') as f:
        f.write("node_modules/\ndist/\nbuild/\n.next/\n")
    
    # Create .prettierignore file
    prettierignore_path = os.path.join(node_ctx.project_path, '.prettierignore')
    with open(prettierignore_path, 'w') as f:
        f.write("node_modules/\ndist/\nbuild/\n.next/\n")
    
    # Update package.json with lint and format scripts
    if node_ctx.package_json:
        scripts = node_ctx.package_json.get("scripts", {})
        
        # Add lint and format scripts
        scripts["lint"] = "eslint ."
        scripts["format"] = "prettier --write ."
        
        # Update scripts in package.json
        node_ctx.package_json["scripts"] = scripts
        
        # Write updated package.json
        package_path = os.path.join(node_ctx.project_path, 'package.json')
        with open(package_path, 'w') as f:
            json.dump(node_ctx.package_json, f, indent=2)
    
    # Return confirmation with list of packages to install
    return f"""ESLint and Prettier configuration set up!

Files created:
- {eslint_path}
- {prettier_path}
- {eslintignore_path}
- {prettierignore_path}

Scripts added to package.json:
- npm run lint
- npm run format

You may need to install the following packages:
{', '.join(packages)}

Run:
npm install --save-dev {' '.join(packages)}"""

@mcp.tool()
def create_docker_setup(ctx: Context, app_type: str = "node") -> str:
    """Generate Docker and docker-compose files for a Node.js project"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."
    
    # Determine node version
    node_version = "18" # Default version
    if node_ctx.node_version != "Not found":
        # Extract major version from version string (e.g., "v18.15.0" -> "18")
        match = re.match(r'v?(\d+)', node_ctx.node_version)
        if match:
            node_version = match.group(1)
    
    # Setup defaults
    dockerfile_content = ""
    dockerignore_content = """
node_modules
npm-debug.log
Dockerfile
.dockerignore
.git
.gitignore
README.md
.env
"""
    
    docker_compose_content = ""
    
    # Create appropriate Dockerfile based on app type
    if app_type.lower() == "node":
        # Basic Node.js application
        dockerfile_content = f"""FROM node:{node_version}-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["node", "index.js"]
"""
        
        docker_compose_content = """version: '3'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
"""
    
    elif app_type.lower() == "express":
        # Express.js application
        dockerfile_content = f"""FROM node:{node_version}-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["node", "index.js"]
"""
        
        docker_compose_content = """version: '3'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
"""
    
    elif app_type.lower() == "next" or app_type.lower() == "nextjs":
        # Next.js application
        dockerfile_content = f"""FROM node:{node_version}-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:{node_version}-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/package*.json ./
RUN npm ci --only=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./

EXPOSE 3000

CMD ["npm", "start"]
"""
        
        docker_compose_content = """version: '3'

services:
  nextjs:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
"""
    
    elif app_type.lower() in ["fullstack", "mern", "mean"]:
        # Fullstack application with MongoDB
        dockerfile_content = f"""FROM node:{node_version}-alpine

WORKDIR /app

COPY package*.json ./

RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["npm", "start"]
"""
        
        docker_compose_content = """version: '3'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - MONGO_URI=mongodb://mongo:27017/app
    depends_on:
      - mongo

  mongo:
    image: mongo:latest
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

volumes:
  mongodb_data:
"""
    
    else:
        return f"Error: Unsupported app type '{app_type}'. Supported types: node, express, next, nextjs, fullstack, mern, mean."
    
    # Write files
    dockerfile_path = os.path.join(node_ctx.project_path, 'Dockerfile')
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile_content)
    
    dockerignore_path = os.path.join(node_ctx.project_path, '.dockerignore')
    with open(dockerignore_path, 'w') as f:
        f.write(dockerignore_content)
    
    docker_compose_path = os.path.join(node_ctx.project_path, 'docker-compose.yml')
    with open(docker_compose_path, 'w') as f:
        f.write(docker_compose_content)
    
    # Return success message
    return f"""Docker configuration created for {app_type} application!

Files created:
- {dockerfile_path}
- {dockerignore_path}
- {docker_compose_path}

To build and run with Docker:
```
docker build -t {node_ctx.package_json.get('name', 'my-app') if node_ctx.package_json else 'my-app'} .
docker run -p 3000:3000 {node_ctx.package_json.get('name', 'my-app') if node_ctx.package_json else 'my-app'}
```

Or with Docker Compose:
```
docker-compose up -d
```"""

@mcp.tool()
def create_performance_test(ctx: Context, endpoint: str, method: str = "GET", requests_per_second: int = 10, duration: int = 10) -> str:
    """Generate a performance test script for a Node.js API endpoint"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."
    
    # Validate inputs
    if not endpoint or not endpoint.startswith('/'):
        endpoint = '/' + (endpoint or '')
    
    method = method.upper()
    if method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        return f"Error: Unsupported HTTP method '{method}'. Supported methods: GET, POST, PUT, DELETE, PATCH."
    
    if requests_per_second < 1:
        requests_per_second = 1
    
    if duration < 1:
        duration = 1
    
    # Create k6 performance test script
    k6_script = f"""import http from 'k6/http';
import {{ sleep, check }} from 'k6';

export const options = {{
  scenarios: {{
    constant_request_rate: {{
      executor: 'constant-arrival-rate',
      rate: {requests_per_second},
      timeUnit: '1s',
      duration: '{duration}s',
      preAllocatedVUs: 20,
      maxVUs: 100,
    }},
  }},
  thresholds: {{
    http_req_failed: ['rate<0.01'], // Less than 1% failures
    http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
  }},
}};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';

export default function () {{
  const url = `${{BASE_URL}}{endpoint}`;
  
  const params = {{
    headers: {{
      'Content-Type': 'application/json',
    }},
  }};
  
  let response;
  
  // Send request based on method
  switch ('{method}') {{
    case 'POST':
      // Add your request body here
      const payload = JSON.stringify({{
        // Example payload - customize for your API
        key: 'value'
      }});
      response = http.post(url, payload, params);
      break;
    case 'PUT':
      response = http.put(url, JSON.stringify({{ key: 'updated' }}), params);
      break;
    case 'DELETE':
      response = http.del(url, null, params);
      break;
    case 'PATCH':
      response = http.patch(url, JSON.stringify({{ key: 'patched' }}), params);
      break;
    default:
      // GET request
      response = http.get(url, params);
  }}
  
  check(response, {{
    'status is 200': (r) => r.status === 200,
    'response time < 200ms': (r) => r.timings.duration < 200,
  }});
  
  // Add a slight pause between requests
  sleep(1 / {requests_per_second});
}}
"""
    
    # Create shell script to run the test
    shell_script = f"""#!/bin/bash
# To run this test, you'll need k6 installed: https://k6.io/docs/getting-started/installation/

# Run the performance test
k6 run performance-test.js
"""

    # Write files
    test_dir = os.path.join(node_ctx.project_path, 'tests', 'performance')
    os.makedirs(test_dir, exist_ok=True)
    
    script_path = os.path.join(test_dir, 'performance-test.js')
    with open(script_path, 'w') as f:
        f.write(k6_script)
    
    runner_path = os.path.join(test_dir, 'run-test.sh')
    with open(runner_path, 'w') as f:
        f.write(shell_script)
    
    # Make shell script executable
    os.chmod(runner_path, 0o755)
    
    return f"""Performance test created for {method} {endpoint}!

Files created:
- {script_path}
- {runner_path}

To run the test, you need to install k6:
https://k6.io/docs/getting-started/installation/

Then run:
```
cd {os.path.relpath(test_dir, node_ctx.project_path)}
./run-test.sh
```

Test configuration:
- Requests per second: {requests_per_second}
- Duration: {duration} seconds
- HTTP method: {method}
- Endpoint: {endpoint}

You can change the target server by setting the BASE_URL environment variable:
```
BASE_URL=https://your-api-server.com k6 run performance-test.js
```"""
@mcp.tool()
async def generate_node_project_template(ctx: Context, project_name: str, project_type: str = "basic", typescript: bool = False, git_init: bool = True) -> str:
    """Generate scaffolding *instructions* and file contents for a new Node.js project.

    Returns a markdown document with package.json, tsconfig, .gitignore, etc.
    Nothing is written to disk — copy/paste or have the caller materialize the files.
    """
    if not project_name:
        return "Error: Project name is required."
    
    # Validate project type
    valid_types = ["basic", "express", "react", "next", "nest"]
    if project_type.lower() not in valid_types:
        return f"Error: Invalid project type. Valid options are: {', '.join(valid_types)}"
    
    # Rather than actually creating files, generate the structure and contents
    structure = {}
    files = {}
    
    if project_type.lower() == "basic":
        if typescript:
            # TypeScript basic Node.js project
            structure = {
                "project_dir": project_name,
                "directories": [
                    "src",
                    "dist",
                    "tests"
                ]
            }
            
            # Add package.json
            package_json = {
                "name": project_name,
                "version": "1.0.0",
                "description": "A TypeScript Node.js application",
                "main": "dist/index.js",
                "scripts": {
                    "build": "tsc",
                    "start": "node dist/index.js",
                    "dev": "ts-node-dev --respawn --transpile-only src/index.ts",
                    "lint": "eslint . --ext .ts",
                    "test": "jest",
                    "clean": "rimraf dist"
                },
                "keywords": ["typescript", "node"],
                "author": "",
                "license": "ISC",
                "dependencies": {
                    "dotenv": "^16.0.3"
                },
                "devDependencies": {
                    "@types/jest": "^29.5.0",
                    "@types/node": "^18.15.11",
                    "@typescript-eslint/eslint-plugin": "^5.58.0",
                    "@typescript-eslint/parser": "^5.58.0",
                    "eslint": "^8.38.0",
                    "jest": "^29.5.0",
                    "rimraf": "^4.4.1",
                    "ts-jest": "^29.1.0",
                    "ts-node-dev": "^2.0.0",
                    "typescript": "^5.0.4"
                }
            }
            
            files["package.json"] = json.dumps(package_json, indent=2)
            
            # Add tsconfig.json
            tsconfig = {
                "compilerOptions": {
                    "target": "es2017",
                    "module": "commonjs",
                    "outDir": "./dist",
                    "rootDir": "./src",
                    "strict": True,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "forceConsistentCasingInFileNames": True
                },
                "include": ["src/**/*"],
                "exclude": ["node_modules", "**/*.test.ts"]
            }
            
            files["tsconfig.json"] = json.dumps(tsconfig, indent=2)
            
            # Add index.ts
            index_ts = '''
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

function main(): void {
  console.log("Hello from TypeScript Node.js!");
  console.log("Project initialized successfully");
}

main();
'''
            files["src/index.ts"] = index_ts.strip()
            
            # Add README.md
            readme = f'''
# {project_name}

A TypeScript Node.js application.

## Installation

```bash
# Install dependencies
npm install
```

## Development

```bash
# Run in development mode with hot reloading
npm run dev
```

## Building for Production

```bash
# Build the project
npm run build

# Start the production server
npm start
```

## Testing

```bash
# Run tests
npm test
```
'''
            files["README.md"] = readme.strip()
            
            # Add .gitignore
            gitignore = '''
# Dependencies
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Build outputs
dist/
coverage/

# Environment variables
.env

# Logs
logs/
*.log

# OS files
.DS_Store
Thumbs.db

# Editor directories and files
.idea/
.vscode/*
*.swp
*.swo
'''
            files[".gitignore"] = gitignore.strip()
            
        else:
            # JavaScript basic Node.js project
            structure = {
                "project_dir": project_name,
                "directories": [
                    "test"
                ]
            }
            
            # Add package.json
            package_json = {
                "name": project_name,
                "version": "1.0.0",
                "description": "A basic Node.js application",
                "main": "index.js",
                "scripts": {
                    "start": "node index.js",
                    "dev": "nodemon index.js",
                    "test": "jest"
                },
                "keywords": ["node"],
                "author": "",
                "license": "ISC",
                "dependencies": {},
                "devDependencies": {
                    "nodemon": "^2.0.22",
                    "jest": "^29.5.0"
                }
            }
            
            files["package.json"] = json.dumps(package_json, indent=2)
            
            # Add index.js
            index_js = '''
// Main application entry point

function main() {
  console.log("Hello from my-node-app!");
  console.log("Application initialized successfully");
}

main();

// Export for testing purposes
module.exports = { main };
'''
            files["index.js"] = index_js.strip()
            
            # Add README.md
            readme = f'''
# {project_name}

A basic Node.js application.

## Installation

```bash
# Install dependencies
npm install
```

## Usage

```bash
# Run the application
npm start

# Run the application with automatic restarts on file changes
npm run dev
```

## Testing

```bash
# Run tests
npm test
```
'''
            files["README.md"] = readme.strip()
            
            # Add .gitignore
            gitignore = '''
# Dependencies
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Environment variables
.env

# Testing
coverage/

# OS files
.DS_Store
Thumbs.db

# Editor directories and files
.idea/
.vscode/
*.swp
*.swo
'''
            files[".gitignore"] = gitignore.strip()
    
    elif project_type.lower() == "express":
        # Express.js project
        if typescript:
            # TypeScript Express.js project
            structure = {
                "project_dir": project_name,
                "directories": [
                    "src",
                    "src/controllers",
                    "src/routes",
                    "src/middleware",
                    "src/models",
                    "src/utils",
                    "dist",
                    "tests"
                ]
            }
            
            # Add package.json
            package_json = {
                "name": project_name,
                "version": "1.0.0",
                "description": "An Express.js application with TypeScript",
                "main": "dist/index.js",
                "scripts": {
                    "build": "tsc",
                    "start": "node dist/index.js",
                    "dev": "ts-node-dev --respawn --transpile-only src/index.ts",
                    "lint": "eslint . --ext .ts",
                    "test": "jest"
                },
                "keywords": ["express", "typescript", "node"],
                "author": "",
                "license": "ISC",
                "dependencies": {
                    "cors": "^2.8.5",
                    "dotenv": "^16.0.3",
                    "express": "^4.18.2",
                    "helmet": "^6.1.5",
                    "morgan": "^1.10.0"
                },
                "devDependencies": {
                    "@types/cors": "^2.8.13",
                    "@types/express": "^4.17.17",
                    "@types/jest": "^29.5.0",
                    "@types/morgan": "^1.9.4",
                    "@types/node": "^18.15.11",
                    "@typescript-eslint/eslint-plugin": "^5.58.0",
                    "@typescript-eslint/parser": "^5.58.0",
                    "eslint": "^8.38.0",
                    "jest": "^29.5.0",
                    "ts-jest": "^29.1.0",
                    "ts-node-dev": "^2.0.0",
                    "typescript": "^5.0.4"
                }
            }
            
            files["package.json"] = json.dumps(package_json, indent=2)
            
            # Add tsconfig.json
            tsconfig = {
                "compilerOptions": {
                    "target": "es2017",
                    "module": "commonjs",
                    "outDir": "./dist",
                    "rootDir": "./src",
                    "strict": True,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "forceConsistentCasingInFileNames": True
                },
                "include": ["src/**/*"],
                "exclude": ["node_modules", "**/*.test.ts"]
            }
            
            files["tsconfig.json"] = json.dumps(tsconfig, indent=2)
            
            # Add index.ts
            index_ts = '''
import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import dotenv from 'dotenv';
import { router } from './routes';

// Load environment variables
dotenv.config();

// Initialize express app
const app: Express = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(helmet()); // Security headers
app.use(cors()); // Enable CORS
app.use(morgan('dev')); // Request logging
app.use(express.json()); // Parse JSON bodies
app.use(express.urlencoded({ extended: true })); // Parse URL-encoded bodies

// Routes
app.use('/api', router);

// Basic route
app.get('/', (req: Request, res: Response) => {
  res.json({ message: 'Welcome to the Express API' });
});

// Error handling middleware
app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  console.error(err.stack);
  res.status(500).json({
    message: 'Something went wrong!',
    error: process.env.NODE_ENV === 'production' ? {} : err
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

export default app; // For testing
'''
            files["src/index.ts"] = index_ts.strip()
            
            # Add routes/index.ts
            routes_ts = '''
import { Router } from 'express';
import * as controller from '../controllers';

export const router = Router();

// Define routes
router.get('/items', controller.getAllItems);
router.get('/items/:id', controller.getItemById);
router.post('/items', controller.createItem);
router.put('/items/:id', controller.updateItem);
router.delete('/items/:id', controller.deleteItem);
'''
            files["src/routes/index.ts"] = routes_ts.strip()
            
            # Add controllers/index.ts
            controllers_ts = '''
import { Request, Response } from 'express';

// Get all items
export const getAllItems = (req: Request, res: Response): void => {
  // In a real app, fetch from database
  const items = [
    { id: 1, name: 'Item 1' },
    { id: 2, name: 'Item 2' }
  ];
  
  res.json(items);
};

// Get item by ID
export const getItemById = (req: Request, res: Response): void => {
  const id = parseInt(req.params.id);
  
  // In a real app, fetch from database
  const item = { id, name: `Item ${id}` };
  
  res.json(item);
};

// Create new item
export const createItem = (req: Request, res: Response): void => {
  const { name } = req.body;
  
  if (!name) {
    res.status(400).json({ message: 'Name is required' });
    return;
  }
  
  // In a real app, save to database
  const newItem = {
    id: Date.now(),
    name
  };
  
  res.status(201).json(newItem);
};

// Update item
export const updateItem = (req: Request, res: Response): void => {
  const id = parseInt(req.params.id);
  const { name } = req.body;
  
  if (!name) {
    res.status(400).json({ message: 'Name is required' });
    return;
  }
  
  // In a real app, update in database
  const updatedItem = {
    id,
    name
  };
  
  res.json(updatedItem);
};

// Delete item
export const deleteItem = (req: Request, res: Response): void => {
  const id = parseInt(req.params.id);
  
  // In a real app, delete from database
  
  res.status(204).end();
};
'''
            files["src/controllers/index.ts"] = controllers_ts.strip()
            
            # Add README.md
            readme = f'''
# {project_name}

An Express.js application with TypeScript.

## Installation

```bash
# Install dependencies
npm install
```

## Development

```bash
# Run in development mode with hot reloading
npm run dev
```

## Building for Production

```bash
# Build the project
npm run build

# Start the production server
npm start
```

## API Endpoints

| Method | Endpoint      | Description        |
|--------|---------------|--------------------|
| GET    | /api/items    | Get all items      |
| GET    | /api/items/:id| Get an item by ID  |
| POST   | /api/items    | Create a new item  |
| PUT    | /api/items/:id| Update an item     |
| DELETE | /api/items/:id| Delete an item     |

## Testing

```bash
# Run tests
npm test
```
'''
            files["README.md"] = readme.strip()
            
            # Add .env.example
            dotenv = '''
# Server configuration
PORT=3000
NODE_ENV=development

# Add your environment variables here
# DATABASE_URL=...
# API_KEY=...
'''
            files[".env.example"] = dotenv.strip()
            
            # Add .gitignore
            gitignore = '''
# Dependencies
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Build outputs
dist/
coverage/

# Environment variables
.env

# Logs
logs/
*.log

# OS files
.DS_Store
Thumbs.db

# Editor directories and files
.idea/
.vscode/*
*.swp
*.swo
'''
            files[".gitignore"] = gitignore.strip()
            
        else:
            # JavaScript Express.js project
            structure = {
                "project_dir": project_name,
                "directories": [
                    "controllers",
                    "routes",
                    "middleware",
                    "models",
                    "utils",
                    "tests"
                ]
            }
            
            # Add package.json
            package_json = {
                "name": project_name,
                "version": "1.0.0",
                "description": "An Express.js application",
                "main": "index.js",
                "scripts": {
                    "start": "node index.js",
                    "dev": "nodemon index.js",
                    "test": "jest"
                },
                "keywords": ["express", "node", "api"],
                "author": "",
                "license": "ISC",
                "dependencies": {
                    "cors": "^2.8.5",
                    "dotenv": "^16.0.3",
                    "express": "^4.18.2",
                    "helmet": "^6.1.5",
                    "morgan": "^1.10.0"
                },
                "devDependencies": {
                    "jest": "^29.5.0",
                    "nodemon": "^2.0.22",
                    "supertest": "^6.3.3"
                }
            }
            
            files["package.json"] = json.dumps(package_json, indent=2)
            
            # Add index.js
            index_js = '''
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const dotenv = require('dotenv');

// Load environment variables
dotenv.config();

// Import routes
const apiRoutes = require('./routes/api');

// Initialize express app
const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(helmet()); // Security headers
app.use(cors()); // Enable CORS
app.use(morgan('dev')); // Request logging
app.use(express.json()); // Parse JSON bodies
app.use(express.urlencoded({ extended: true })); // Parse URL-encoded bodies

// Routes
app.use('/api', apiRoutes);

// Basic route
app.get('/', (req, res) => {
  res.json({ message: 'Welcome to the Express API' });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    message: 'Something went wrong!',
    error: process.env.NODE_ENV === 'production' ? {} : err
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app; // For testing
'''
            files["index.js"] = index_js.strip()
            
            # Add routes/api.js
            routes_js = '''
const express = require('express');
const router = express.Router();
const controller = require('../controllers');

// Get all items
router.get('/items', controller.getAllItems);

// Get single item by ID
router.get('/items/:id', controller.getItemById);

// Create new item
router.post('/items', controller.createItem);

// Update item
router.put('/items/:id', controller.updateItem);

// Delete item
router.delete('/items/:id', controller.deleteItem);

module.exports = router;
'''
            files["routes/api.js"] = routes_js.strip()
            
            # Add controllers/index.js
            controllers_js = '''
// Sample controller for demonstration

// Get all items
exports.getAllItems = (req, res) => {
  // In a real app, fetch from database
  const items = [
    { id: 1, name: 'Item 1' },
    { id: 2, name: 'Item 2' }
  ];
  
  res.json(items);
};

// Get item by ID
exports.getItemById = (req, res) => {
  const id = parseInt(req.params.id);
  
  // In a real app, fetch from database
  const item = { id, name: `Item ${id}` };
  
  res.json(item);
};

// Create new item
exports.createItem = (req, res) => {
  const { name } = req.body;
  
  if (!name) {
    return res.status(400).json({ message: 'Name is required' });
  }
  
  // In a real app, save to database
  const newItem = {
    id: Date.now(),
    name
  };
  
  res.status(201).json(newItem);
};

// Update item
exports.updateItem = (req, res) => {
  const id = parseInt(req.params.id);
  const { name } = req.body;
  
  if (!name) {
    return res.status(400).json({ message: 'Name is required' });
  }
  
  // In a real app, update in database
  const updatedItem = {
    id,
    name
  };
  
  res.json(updatedItem);
};

// Delete item
exports.deleteItem = (req, res) => {
  const id = parseInt(req.params.id);
  
  // In a real app, delete from database
  
  res.status(204).end();
};
'''
            files["controllers/index.js"] = controllers_js.strip()
            
            # Add README.md
            readme = f'''
# {project_name}

An Express.js application.

## Installation

```bash
# Install dependencies
npm install
```

## Usage

```bash
# Run the application
npm start

# Run the application with automatic restarts on file changes
npm run dev
```

## API Endpoints

| Method | Endpoint      | Description        |
|--------|---------------|--------------------|
| GET    | /api/items    | Get all items      |
| GET    | /api/items/:id| Get an item by ID  |
| POST   | /api/items    | Create a new item  |
| PUT    | /api/items/:id| Update an item     |
| DELETE | /api/items/:id| Delete an item     |

## Testing

```bash
# Run tests
npm test
```
'''
            files["README.md"] = readme.strip()
            
            # Add .env.example
            dotenv = '''
# Server configuration
PORT=3000
NODE_ENV=development

# Add your environment variables here
# DATABASE_URL=...
# API_KEY=...
'''
            files[".env.example"] = dotenv.strip()
            
            # Add .gitignore
            gitignore = '''
# Dependencies
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Environment variables
.env

# Testing
coverage/

# Logs
logs/
*.log

# OS files
.DS_Store
Thumbs.db

# Editor directories and files
.idea/
.vscode/
*.swp
*.swo
'''
            files[".gitignore"] = gitignore.strip()
    
    # For other project types, you can add similar structured outputs
    # For React, Next.js, etc.
    
    # Put everything together for the response
    response = f"# {project_name}\n\n"
    
    # Start with the quickest way to create the project with real commands
    response += "## Quick Setup with CLI Commands\n\n"
    
    if project_type.lower() == "react":
        # For React projects, use Create React App
        cmd = f"npx create-react-app {project_name}"
        if typescript:
            cmd += " --template typescript"
        response += f"```bash\n{cmd}\n\n# After creation\ncd {project_name}\nnpm start\n```\n\n"
        
    elif project_type.lower() == "next":
        # For Next.js projects, use Create Next App
        cmd = f"npx create-next-app@latest {project_name}"
        if typescript:
            cmd += " --typescript"
        response += f"```bash\n{cmd}\n\n# After creation\ncd {project_name}\nnpm run dev\n```\n\n"
        
    elif project_type.lower() == "nest":
        # For NestJS projects, use the Nest CLI
        cmd = f"npx @nestjs/cli new {project_name}"
        response += f"```bash\n{cmd}\n\n# After creation\ncd {project_name}\nnpm run start:dev\n```\n\n"
        
    elif project_type.lower() == "express":
        # For Express projects, use express-generator or manual setup
        if typescript:
            cmd = f"# First, create a directory and initialize\nmkdir {project_name}\ncd {project_name}\nnpm init -y\n\n# Install necessary dependencies\nnpm install express cors dotenv helmet morgan\nnpm install --save-dev typescript ts-node-dev @types/node @types/express @types/cors @types/morgan\n\n# Initialize TypeScript configuration\nnpx tsc --init\n\n# Create src directory for TypeScript files\nmkdir -p src/routes src/controllers src/middleware"
        else:
            cmd = f"# Option 1: Use express-generator\nnpx express-generator {project_name}\ncd {project_name}\nnpm install\n\n# Option 2: Manual setup\nmkdir {project_name}\ncd {project_name}\nnpm init -y\nnpm install express cors dotenv helmet morgan\nnpm install --save-dev nodemon\nmkdir -p routes controllers middleware"
        response += f"```bash\n{cmd}\n```\n\n"
        
    else:  # Basic Node.js project
        if typescript:
            cmd = f"# Create a basic TypeScript Node.js project\nmkdir {project_name}\ncd {project_name}\nnpm init -y\n\n# Install TypeScript and dependencies\nnpm install --save-dev typescript ts-node-dev @types/node\nnpm install dotenv\n\n# Initialize TypeScript configuration\nnpx tsc --init\n\n# Create source directory\nmkdir -p src\n"
        else:
            cmd = f"# Create a basic Node.js project\nmkdir {project_name}\ncd {project_name}\nnpm init -y\n\n# Install development dependencies\nnpm install --save-dev nodemon jest\n\n# Create basic structure\ntouch index.js\nmkdir test\n"
        response += f"```bash\n{cmd}\n```\n\n"
    
    # Add information about newer build tools
    response += "### Modern Alternatives\n\n"
    response += "You can also use these modern build tools for better developer experience:\n\n"
    
    response += "**Using Vite for frontend projects:**\n"
    response += "```bash\n"
    response += f"# For React\nnpm create vite@latest {project_name} -- --template "
    response += f"{'react-ts' if typescript else 'react'}\n\n"
    response += "# For Vue, Svelte, Lit, etc. (same command, different template)\n"
    response += "```\n\n"
    
    response += "**Using npm init for various project types:**\n"
    response += "```bash\n"
    response += "# For creating a new package\n"
    response += f"npm init {project_type if project_type in ['node', 'react', 'nest'] else ''}\n"
    response += "```\n\n"
    
    # Show directory structure
    response += "## Project Structure\n\n"
    response += "```\n"
    response += f"{project_name}/\n"
    
    if "directories" in structure:
        for directory in structure["directories"]:
            response += f"├── {directory}/\n"
    
    for filename in files.keys():
        if "/" not in filename:  # Show only top-level files in the structure
            response += f"├── {filename}\n"
    
    response += "```\n\n"
    
    # Show file contents
    response += "## File Contents\n\n"
    
    for filename, content in files.items():
        response += f"### {filename}\n"
        
        if filename.endswith(".json"):
            response += "```json\n"
        elif filename.endswith(".js"):
            response += "```javascript\n"
        elif filename.endswith(".ts"):
            response += "```typescript\n"
        elif filename.endswith(".md"):
            response += "```markdown\n"
        else:
            response += "```\n"
        
        response += f"{content}\n```\n\n"
    
    # Setup instructions for manual creation
    response += "## Manual Setup Instructions\n\n"
    response += "If you prefer to create the project structure manually:\n\n"
    
    response += "1. Create the project directory:\n"
    response += f"```bash\nmkdir -p {project_name}\ncd {project_name}\n```\n\n"
    
    response += "2. Create the file structure:\n"
    response += "```bash\n"
    
    if "directories" in structure:
        for directory in structure["directories"]:
            response += f"mkdir -p {directory}\n"
    
    response += "```\n\n"
    
    response += "3. Create each file with the contents shown above\n\n"
    
    response += "4. Initialize the project:\n"
    response += "```bash\n"
    response += "npm init -y  # Create package.json (or copy the one above)\n"
    response += "npm install  # Install dependencies\n"
    if git_init:
        response += "git init  # Initialize git repository\n"
    response += "```\n\n"
    
    # Add common next steps
    response += "## Next Steps\n\n"
    
    if project_type.lower() == "basic":
        response += "- Add more dependencies as needed with `npm install <package-name>`\n"
        response += "- Create unit tests in the `test/` directory\n"
        response += "- Consider adding ESLint and Prettier for code quality\n"
    
    elif project_type.lower() == "express":
        response += "- Define more routes and controllers\n"
        response += "- Connect to a database (MongoDB, PostgreSQL, etc.)\n"
        response += "- Add authentication middleware\n"
        response += "- Consider adding Swagger/OpenAPI for API documentation\n"
    
    elif project_type.lower() in ["react", "next"]:
        response += "- Add component libraries like Material UI, Chakra UI, or Tailwind CSS\n"
        response += "- Set up state management (Redux, Zustand, React Context)\n"
        response += "- Configure routing (already set up in Next.js)\n"
        response += "- Add form handling libraries like Formik or React Hook Form\n"
    
    # Return the structured output instead of creating files
    return response

@mcp.tool()
def convert_to_typescript(file_path: str, ctx: Context) -> str:
    """Convert a JavaScript file to TypeScript with basic types"""
    node_ctx = ctx.request_context.lifespan_context
    
    if not node_ctx.project_path:
        return "Error: No Node.js project found. Please run this in a directory with a package.json file."

    # Validate file path (must stay inside the project root)
    full_file_path = _resolve_in_project(node_ctx.project_path, file_path)
    if full_file_path is None:
        return f"Error: {file_path} is outside the project directory."
    if not os.path.exists(full_file_path):
        return f"Error: File {file_path} not found."

    # Check if it's a JavaScript file
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in ['.js', '.jsx']:
        return f"Error: Can only convert JavaScript files (.js, .jsx) to TypeScript. Got: {ext}"
    
    # Determine the output extension (.ts or .tsx)
    is_react = ext.lower() == '.jsx'
    output_ext = '.tsx' if is_react else '.ts'
    
    # Create output file path
    output_path = os.path.splitext(full_file_path)[0] + output_ext
    
    # Read input file
    with open(full_file_path, 'r') as f:
        js_code = f.read()
    
    # Basic conversion of JS to TS
    ts_code = js_code
    
    # 1. Add 'type' to imports/requires that appear to be types
    type_related_imports = ['interface', 'type', 'enum']
    for type_name in type_related_imports:
        ts_code = re.sub(
            rf'import\s+{{\s*([^}}]*{type_name}[^}}]*)\s*}}\s+from\s+',
            r'import type { \1 } from ',
            ts_code
        )
    
    # 2. Type React functional components. This must run BEFORE the generic
    #    annotations below — those rewrite the very signatures these patterns
    #    match (e.g. "(props) =>" becomes "(props): any =>").
    if is_react:
        component_match = re.search(
            r'export\s+default\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\('
            r'|const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\([^)]*\)\s*=>',
            ts_code
        )
        if component_match and re.search(r'return\s*[(<]', ts_code):
            component_name = component_match.group(1) or component_match.group(2)

            if 'import React' not in ts_code:
                ts_code = "import React from 'react';\n" + ts_code

            # Insert a Props interface after the last import line
            lines = ts_code.split('\n')
            insert_at = 0
            for i, line in enumerate(lines):
                if line.startswith('import'):
                    insert_at = i + 1
            lines.insert(insert_at, f"\ninterface {component_name}Props {{\n  // TODO: Define props types here\n}}")
            ts_code = '\n'.join(lines)

            # const Name = (props) => {  ->  const Name: React.FC<NameProps> = (props) => {
            ts_code = re.sub(
                rf'const\s+{component_name}\s*=\s*\(\s*([^)]*?)\s*\)\s*=>\s*{{',
                rf'const {component_name}: React.FC<{component_name}Props> = (\1) => {{',
                ts_code
            )

            # export default function Name(props) {  ->  ...(props: NameProps): JSX.Element {
            def _annotate_component_fn(match: "re.Match[str]") -> str:
                params = match.group(2).strip()
                typed = f"{params}: {component_name}Props" if params else ""
                return f"{match.group(1)}({typed}): JSX.Element {{"

            ts_code = re.sub(
                rf'(export\s+default\s+function\s+{component_name})\s*\(\s*([^)]*)\s*\)\s*{{',
                _annotate_component_fn,
                ts_code
            )

    # 3. Add basic function type annotations (skips signatures already typed above)
    ts_code = re.sub(
        r'function\s+([a-zA-Z0-9_]+)\s*\(\s*([^)]*)\s*\)\s*{',
        r'function \1(\2): any {',
        ts_code
    )

    # 4. Add basic types for arrow functions
    ts_code = re.sub(
        r'const\s+([a-zA-Z0-9_]+)\s*=\s*\(\s*([^)]*)\s*\)\s*=>\s*{',
        r'const \1 = (\2): any => {',
        ts_code
    )
    
    # Write the TypeScript code to the output file
    with open(output_path, 'w') as f:
        f.write(ts_code)
    
    # Check if TypeScript is installed
    all_dependencies = {**node_ctx.dependencies, **node_ctx.dev_dependencies}
    missing_deps = []
    
    if 'typescript' not in all_dependencies:
        missing_deps.append('typescript')
    
    if is_react and '@types/react' not in all_dependencies:
        missing_deps.append('@types/react')
    
    # Check if we need to create tsconfig.json
    tsconfig_path = os.path.join(node_ctx.project_path, 'tsconfig.json')
    tsconfig_created = False
    
    if not os.path.exists(tsconfig_path):
        # Create basic tsconfig.json
        tsconfig = {
            "compilerOptions": {
                "target": "es5",
                "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": True,
                "skipLibCheck": True,
                "esModuleInterop": True,
                "allowSyntheticDefaultImports": True,
                "strict": True,
                "forceConsistentCasingInFileNames": True,
                "noFallthroughCasesInSwitch": True,
                "module": "esnext",
                "moduleResolution": "node",
                "resolveJsonModule": True,
                "isolatedModules": True,
                "noEmit": True,
                "jsx": "react-jsx",
                "outDir": "./dist"
            },
            "include": ["src/**/*"],
            "exclude": ["node_modules", "**/*.spec.ts"]
        }
        
        with open(tsconfig_path, 'w') as f:
            json.dump(tsconfig, f, indent=2)
        
        tsconfig_created = True
    
    # Prepare result message
    result = f"Converted {file_path} to TypeScript: {os.path.relpath(output_path, node_ctx.project_path)}"
    
    if tsconfig_created:
        result += f"\nCreated tsconfig.json at {tsconfig_path}"
    
    if missing_deps:
        result += f"\n\nNote: You may need to install these packages: {', '.join(missing_deps)}"
        result += f"\nRun: npm install --save-dev {' '.join(missing_deps)}"
    
    result += "\n\nNOTE: The type conversion is basic. You'll likely need to manually add proper types, especially for:"
    result += "\n- Function parameters and return types"
    result += "\n- Component props"
    result += "\n- Variable declarations"
    result += "\n- API responses"
    
    return result

# =========== PROMPTS ===========

@mcp.prompt()
def nodejs_project_setup(project_type: str) -> str:
    """Prompt for Node.js project setup guidance"""
    return "I want to set up a new Node.js project for " + project_type + """. 

Please guide me through:
1. The initial project structure
2. Essential dependencies I should install
3. Basic configuration files
4. Best practices for this type of project

I'd like step-by-step instructions that I can follow to get started."""

@mcp.prompt()
def react_component_design(component_description: str) -> str:
    """Prompt for designing a React component"""
    return "I need to create a React component that " + component_description + """.

Please help me design this component by considering:
- What props it should accept
- State management requirements
- Component structure and hierarchy
- Any performance considerations
- Potential reusability options

I'd appreciate a detailed discussion followed by actual component code I can use in my project."""

@mcp.prompt()
def npm_package_evaluation(package_name: str) -> str:
    """Prompt for evaluating an npm package"""
    return "I'm considering using the " + package_name + """ npm package in my project. 

Could you help me evaluate it by:
1. Explaining what it does and its main features
2. Discussing its popularity, maintenance status, and community support
3. Comparing it with alternatives if available
4. Highlighting any potential drawbacks or limitations
5. Providing a simple example of how to use it

This will help me decide if it's the right package for my needs."""

@mcp.prompt()
def debug_nodejs_issue(error_message: str) -> list[base.Message]:
    """Interactive prompt to debug a Node.js error"""
    return [
        base.UserMessage("I'm getting this error in my Node.js application:"),
        base.UserMessage(error_message),
        base.AssistantMessage("I'll help you debug this error. To better understand the issue, could you tell me more about:"),
        base.AssistantMessage("1. What were you trying to do when this error occurred?\n2. What version of Node.js are you using?\n3. Can you share the relevant code snippet that's causing this error?")
    ]

@mcp.prompt()
def performance_optimization(performance_issue: str) -> str:
    """Prompt for Node.js performance optimization advice"""
    return "I'm experiencing performance issues with my Node.js application. Specifically: " + performance_issue + """

Could you provide me with:

1. Potential causes of this performance issue
2. Ways to diagnose and profile the problem
3. Recommended optimization strategies
4. Best practices for Node.js performance in this scenario

I'm looking for practical solutions I can implement to improve my application's performance."""

@mcp.prompt()
def security_review(app_description: str) -> str:
    """Prompt for Node.js security review"""
    return "I'd like a security review for my Node.js application. Here's a description of what it does: " + app_description + """

Please help me identify:

1. Common security vulnerabilities I should be aware of
2. Security best practices for this type of application
3. Specific packages or tools I should use to improve security
4. Methods to test and validate my application's security

I want to ensure my application is following current security best practices."""

# Run the server if executed directly
if __name__ == "__main__":
    mcp.run()