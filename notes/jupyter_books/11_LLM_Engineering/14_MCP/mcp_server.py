# 使用独立包 fastmcp（uv/pip: fastmcp）。
# mcp.server.fastmcp 在 mcp 2.x 下会因 LifespanContextT 导入失败。
from fastmcp import FastMCP

mcp = FastMCP("demo-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers"""
    return a + b

@mcp.resource("config://app")
def app_config() -> str:
    """The application JSON configuration"""
    return '{"env": "prod", "region":"us-east-1"}'
    
@mcp.prompt()
def code_review(language: str, code: str) -> str:
    """Review the code in the given language"""
    return f"Reviewing {language} code:\n{code}"

if __name__ == "__main__":
    mcp.run(transport="stdio")